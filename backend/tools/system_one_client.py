"""HTTP client for a System One server.

System One answers closed questions about a text with probabilities (no text generation).
One ``evaluate`` call sends ALL the questions of an agent in a single ``POST /v1/systemone``.

Two providers speak different wire formats (``PROVIDERS``): ``system_one`` (Nimble, Jev: ``/v1/systemone``) and
``openai_decisions`` (``/v1/decisions``). The OpenAI answer is normalized to the System One shape right here, so
everything downstream (decisions, evaluator, metrics) is provider-agnostic. Only providers in ``IMAGE_PROVIDERS``
accept images.

Server limits that shape this module: 4 concurrent requests by default (HTTP 529 plus
``Retry-After`` above that), 64 questions per call and 8192 tokens per question prompt.
Errors come in two shapes: ``{"error": {"message": ...}}`` and FastAPI's ``{"detail": [...]}``.
"""
from __future__ import annotations

import asyncio
import math
import re
import weakref
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

import httpx

from tools.system_one_limiter import SlotWaitTimeout, global_slot
from schemas.system_one_schemas import ChoiceQuestion, NoulQuestion, Question
from utils.logger import get_logger

logger = get_logger(__name__)

PROVIDER_SYSTEM_ONE = "system_one"
PROVIDER_OPENAI = "openai_decisions"
PROVIDERS = (PROVIDER_SYSTEM_ONE, PROVIDER_OPENAI)
IMAGE_PROVIDERS = frozenset({PROVIDER_OPENAI})
IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})   # the formats OpenAI documents for the Decisions API
OPENAI_MODELS = ["gpt-6-luna"]   # ponytail: the only model of the Decisions API today; it has no model listing

ErrorKind = Literal["unavailable", "overloaded", "timeout", "unauthorized", "quota", "invalid_request", "invalid_response"]

_TIMEOUT_S = 30.0       # per httpx phase (connect/read/write/pool)
_DEADLINE_S = 120.0     # the whole call: waiting for a slot + every attempt + the pauses between them
_PROBE_TIMEOUT_S = 10.0
_ATTEMPTS = 3
_RETRY_STATUSES = {429, 502, 503, 529}  # overloaded or briefly unavailable; 4xx are our bug
_RETRY_AFTER_CAP_S = 10.0
_BACKOFF_S = 0.5

_sleep = asyncio.sleep  # indirection so tests can run retries without waiting


class SystemOneError(Exception):
    """A failed System One call, with a stable ``kind`` the callers map to a user message."""

    def __init__(self, kind: ErrorKind, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    model: str
    max_concurrency: int
    service_id: int
    api_key: Optional[str] = field(default=None, repr=False)
    provider: str = PROVIDER_SYSTEM_ONE


# Models that take images next to the text, by name (a gateway may prefix the id: "openai/gpt-6-luna-decisions").
# ponytail: kept by hand, like model_catalog's vision patterns, because the providers' model lists do not say it.
IMAGE_MODELS = re.compile(r"(?:^|/)gpt-6-luna")


def supports_images(provider: str, model: str) -> bool:
    return provider in IMAGE_PROVIDERS and bool(IMAGE_MODELS.search((model or "").lower()))


def default_max_concurrency(server_limit: Optional[int]) -> int:
    """The cap of a service is the whole server's limit: it is shared by every backend process (see the limiter)."""
    return max(1, server_limit or 1)


# ------------------------------------------------------------------ request

def build_request_body(model: str, state: str, questions: List[Question],
                       provider: str = PROVIDER_SYSTEM_ONE, images: Optional[List[str]] = None) -> Dict[str, Any]:
    if provider == PROVIDER_OPENAI:
        return _build_openai_body(model, state, questions, images)
    body_questions: Dict[str, Any] = {}
    for q in questions:
        item: Dict[str, Any] = {"type": q.type, "instructions": q.instructions}
        if isinstance(q, NoulQuestion):
            meanings = {k: v for k, v in (("true", q.criteria.true), ("false", q.criteria.false)) if v} if q.criteria else {}
            if meanings:
                item["criteria"] = meanings
        elif isinstance(q, ChoiceQuestion):
            item["criteria"] = {o.key: o.description for o in q.criteria}
        else:
            item["criteria"] = list(q.criteria)
        body_questions[q.key] = item
    return {"model": model, "state": state, "questions": body_questions}


def _build_openai_body(model: str, state: str, questions: List[Question], images: Optional[List[str]]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for q in questions:
        item: Dict[str, Any] = {"type": "predicate", "name": q.key, "instructions": q.instructions}
        if isinstance(q, NoulQuestion):
            # A predicate has no per-answer meanings: they go into the instructions.
            meanings = [f"{k} means: {v}." for k, v in (("true", q.criteria.true), ("false", q.criteria.false)) if v] if q.criteria else []
            item["instructions"] = " ".join([q.instructions, *meanings])
        elif isinstance(q, ChoiceQuestion):
            item["type"] = "choice"
            item["choices"] = [{"value": o.key, "description": o.description or o.key} for o in q.criteria]
        else:
            item["type"] = "score"
            item["levels"] = [{"label": level, "description": level} for level in q.criteria]
        items.append(item)
    if images:
        content: List[Dict[str, Any]] = ([{"type": "input_text", "text": state}] if state.strip() else [])
        content += [{"type": "input_image", "image_url": url} for url in images]
        input_: Any = [{"role": "user", "content": content}]
    else:
        input_ = state
    return {"model": model, "input": input_, "questions": items}


def _normalize_openai(data: Any, questions: List[Question]) -> Dict[str, Any]:
    """OpenAI's ``{"answers": [..]}`` -> the System One shape (``answers`` keyed by question, probability maps)."""
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, list):
        return {}
    out: Dict[str, Any] = {}
    for a in answers:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str):
            continue
        t, probs = a.get("type"), a.get("probabilities")
        if t == "predicate":
            out[a["name"]] = {"type": "noul", "noul": a.get("probability")}
        elif t in ("choice", "score") and isinstance(probs, list):
            pmap = {str(p.get("value")): p.get("probability") for p in probs if isinstance(p, dict)}
            item = {"type": t, "probabilities": pmap, "confidence": a.get("confidence")}
            if t == "choice":
                item["choice"] = a.get("choice")
            else:
                item["score"] = a.get("score")
                item["legend"] = {str(p.get("value")): str(p.get("label")) for p in probs if isinstance(p, dict)}
            out[a["name"]] = item
        elif t == "refusal":
            out[a["name"]] = {"type": "refusal"}
    return {"answers": out, "model": data.get("model"), "usage": data.get("usage")}


# -------------------------------------------------------------- concurrency

_slots_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[int, Tuple[int, asyncio.Semaphore]]]" = (
    weakref.WeakKeyDictionary()
)


def _slot(endpoint: Endpoint) -> asyncio.Semaphore:
    """One semaphore per service and event loop (a semaphore binds to its loop).

    A changed ``max_concurrency`` replaces it, so the new cap applies to the next call without a
    restart; calls still in flight keep the old semaphore and finish under the old cap.
    """
    per_loop = _slots_by_loop.setdefault(asyncio.get_running_loop(), {})
    cap = max(1, endpoint.max_concurrency)
    held = per_loop.get(endpoint.service_id)
    if held is None or held[0] != cap:
        held = per_loop[endpoint.service_id] = (cap, asyncio.Semaphore(cap))
    return held[1]


# ------------------------------------------------------------------- errors

def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return (response.text or "").strip()[:200] or f"HTTP {response.status_code}"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        detail = data.get("detail")
        if isinstance(detail, list):
            msgs = [str(d.get("msg")) for d in detail if isinstance(d, dict) and d.get("msg")]
            if msgs:
                return "; ".join(msgs)
        if isinstance(detail, str):
            return detail
    return f"HTTP {response.status_code}"


def _error_for(response: httpx.Response) -> SystemOneError:
    status, message = response.status_code, _error_message(response)
    if status in (401, 403):   # servers differ: some answer 403 for a missing or wrong key
        kind: ErrorKind = "unauthorized"
    elif status == 402:       # a hosted API whose prepaid credit ran out
        kind = "quota"
    elif status in (429, 529):
        kind = "overloaded"
    elif status == 504:
        kind = "timeout"
    elif status >= 500:
        kind = "unavailable"
    elif 400 <= status < 500:
        kind = "invalid_request"
    else:
        kind = "invalid_response"
    return SystemOneError(kind, message, status)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait: the server's Retry-After when it is a usable number (capped), else a growing backoff.

    ``float()`` also accepts "nan" and "inf", and ``asyncio.sleep(nan)`` never returns: the slot would stay held forever.
    """
    try:
        value = float(response.headers.get("Retry-After", ""))
    except ValueError:
        value = math.nan
    if math.isfinite(value) and value >= 0:
        return min(value, _RETRY_AFTER_CAP_S)
    return _BACKOFF_S * attempt


# ----------------------------------------------------------------- response

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_prob_map(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(_is_number(v) for v in value.values())


def _validate(response: httpx.Response, questions: List[Question], provider: str = PROVIDER_SYSTEM_ONE) -> Dict[str, Any]:
    def invalid(why: str) -> SystemOneError:
        return SystemOneError("invalid_response", f"Unexpected System One response: {why}", response.status_code)

    try:
        data = response.json()
    except ValueError:
        raise invalid("not JSON")
    if provider == PROVIDER_OPENAI:
        data = _normalize_openai(data, questions)
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict):
        raise invalid("no 'answers'")
    for q in questions:
        a = answers.get(q.key)
        if not isinstance(a, dict):
            raise invalid(f"missing answer for '{q.key}'")
        if a.get("type") == "refusal":
            raise SystemOneError("invalid_request", f"The model refused to answer '{q.key}'", response.status_code)
        if a.get("type", q.type) != q.type:
            raise invalid(f"'{q.key}' answered as {a.get('type')} instead of {q.type}")
        if q.type == "noul":
            ok = _is_number(a.get("noul"))
        elif q.type == "choice":
            ok = isinstance(a.get("choice"), str) and _is_prob_map(a.get("probabilities")) and _is_number(a.get("confidence"))
        else:
            ok = (_is_number(a.get("score")) and isinstance(a.get("legend"), dict)
                  and _is_prob_map(a.get("probabilities")) and _is_number(a.get("confidence")))
        if not ok:
            raise invalid(f"malformed answer for '{q.key}'")
    return data


# ---------------------------------------------------------------------- API

async def evaluate(endpoint: Endpoint, state: str, questions: List[Question],
                   *, images: Optional[List[str]] = None,
                   transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    """Send ``state`` (and ``images`` as data URLs, only for providers that take them) with all ``questions``.

    Returns the validated server JSON in the System One shape.

    ``transport`` exists for tests (``httpx.MockTransport``). Never logs the state or the token.
    """
    if images and not supports_images(endpoint.provider, endpoint.model):
        raise SystemOneError("invalid_request", "This provider evaluates text only")
    path = "/v1/decisions" if endpoint.provider == PROVIDER_OPENAI else "/v1/systemone"
    url = endpoint.base_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}
    body = build_request_body(endpoint.model, state, questions, endpoint.provider, images)

    async def attempts() -> Dict[str, Any]:
        # Held across retries: under overload the others wait too. The process-local semaphore first, so that a
        # burst waits in memory and not with one database connection each; then the slot shared by all processes.
        async with _slot(endpoint), global_slot(endpoint.service_id, endpoint.max_concurrency):
            async with httpx.AsyncClient(timeout=_TIMEOUT_S, transport=transport) as http:
                for attempt in range(1, _ATTEMPTS + 1):
                    try:
                        response = await http.post(url, json=body, headers=headers)
                    except httpx.TimeoutException:
                        raise SystemOneError("timeout", "System One did not answer in time")
                    except httpx.TransportError:
                        raise SystemOneError("unavailable", "Cannot connect to the System One server")
                    if response.status_code == 200:
                        return _validate(response, questions, endpoint.provider)
                    if response.status_code in _RETRY_STATUSES and attempt < _ATTEMPTS:
                        logger.info("[system_one] HTTP %s, retry %d/%d", response.status_code, attempt, _ATTEMPTS - 1)
                        await _sleep(_retry_delay(response, attempt))
                        continue
                    raise _error_for(response)
        raise AssertionError("unreachable")

    try:
        return await asyncio.wait_for(attempts(), timeout=_DEADLINE_S)
    except asyncio.TimeoutError:
        raise SystemOneError("timeout", "System One did not answer in time") from None
    except SlotWaitTimeout:
        raise SystemOneError("overloaded", "System One is busy: every slot of this service stayed taken") from None


def check_base_url(base_url: str) -> str:
    parsed = urlparse(base_url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("The URL must start with http:// or https:// and include a host")
    return base_url.rstrip("/")


async def probe_openai(root: str, api_key: Optional[str], transport: Optional[httpx.AsyncBaseTransport]) -> Dict[str, Any]:
    """OpenAI has no health or limits endpoint: ``GET /v1/models`` proves the key; the model list is fixed."""
    result: Dict[str, Any] = {"ok": False, "message": "", "models": [], "limits": None, "verifiable": True}
    if not api_key:
        result["message"] = "OpenAI needs an API key"
        return result
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S, transport=transport,
                                     headers={"Authorization": f"Bearer {api_key}"}) as http:
            response = await http.get(root + "/v1/models")
    except httpx.TimeoutException:
        result["message"] = "The server did not answer in time"
        return result
    except httpx.TransportError:
        result["message"] = "Cannot connect to the server"
        return result
    if response.status_code != 200:
        result["message"] = (f"The server rejected the API key ({response.status_code})"
                             if response.status_code in (401, 403) else f"The server answered {_error_message(response)}")
        return result
    return {**result, "ok": True, "models": OPENAI_MODELS, "message": "Connection successful"}


async def probe(base_url: str, api_key: Optional[str], provider: str = PROVIDER_SYSTEM_ONE,
                *, transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    """Check ``/health``, list ``/v1/models`` and read ``/v1/limits``. Never raises for server problems."""
    root = check_base_url(base_url)
    if provider == PROVIDER_OPENAI:
        return await probe_openai(root, api_key, transport)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    result: Dict[str, Any] = {"ok": False, "message": "", "models": [], "limits": None, "verifiable": False}

    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S, transport=transport, headers=headers) as http:
        async def get(path: str) -> httpx.Response:
            return await http.get(root + path)

        try:
            health = await get("/health")
        except httpx.TimeoutException:
            result["message"] = "The server did not answer in time"
            return result
        except httpx.TransportError:
            result["message"] = "Cannot connect to the System One server"
            return result
        if health.status_code in (401, 403):
            result["message"] = f"The server rejected the token ({health.status_code})"
            return result
        has_health = health.status_code not in (404, 405)   # not every server has a health endpoint
        if has_health:
            try:
                healthy = health.status_code == 200 and health.json().get("status") == "ok"
            except (ValueError, AttributeError):
                healthy = False
            if not healthy:
                result["message"] = f"The server is not ready ({_error_message(health)})"
                return result

        try:
            models = await get("/v1/models")
            if models.status_code in (401, 403):
                result["message"] = f"The server rejected the token ({models.status_code})"
                return result
            if models.status_code == 200:
                result["models"] = [m["id"] for m in models.json().get("data", []) if isinstance(m, dict) and "id" in m]
            limits = await get("/v1/limits")
            if limits.status_code == 200:
                result["limits"] = limits.json()
        except (httpx.TransportError, ValueError):
            result["message"] = "The server answered /health but not /v1/models or /v1/limits"
            return result

    # Verifiable = the server gave something to check the connection against (health or a model list); a bare
    # /v1/systemone server can only be proven by a real call.
    result["verifiable"] = has_health or bool(result["models"])
    result["ok"] = True
    result["message"] = (
        "Connection successful" if result["verifiable"]
        else "The server answered, but it has no health or model endpoints: the token and the model are only "
             "checked by a real call"
    )
    return result


_CHECK_QUESTION = [NoulQuestion(key="ping", type="noul", instructions="Is the text a greeting?")]


async def check_model(endpoint: Endpoint, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> Dict[str, Any]:
    """Verify URL, token and model with one real, tiny call (one question, a few tokens).

    For servers that offer no way to list models or to check the token, this is the only proof. Never raises
    for a server problem: ``{"ok": bool, "message": str}``.
    """
    try:
        await evaluate(endpoint, "hello", _CHECK_QUESTION, transport=transport)
    except SystemOneError as exc:
        return {"ok": False, "message": _check_failure(exc)}
    return {"ok": True, "message": "Connection verified with a real test call (one question, a few tokens)"}


def _check_failure(exc: SystemOneError) -> str:
    if exc.kind == "unauthorized":
        return f"The server rejected the token (HTTP {exc.status})"
    if exc.kind == "quota":
        return "The account has no credit left"
    if exc.kind == "invalid_request":
        if exc.status == 404:
            return "The server answered 404: check the URL (some servers carry the model name in it)"
        return f"The server rejected the test question: {exc.message[:200]}"
    if exc.kind == "invalid_response":
        return "The server answered, but not in the format System One uses"
    return exc.message
