import asyncio
import json

import httpx
import pytest
from pydantic import TypeAdapter

from schemas.system_one_schemas import Question
from tools import system_one_client as client
from tools.system_one_client import Endpoint, SystemOneError

QA = TypeAdapter(Question).validate_python
NOUL = QA({"key": "urgent", "type": "noul", "instructions": "Is it urgent?"})
NOUL_CRIT = QA({"key": "reply", "type": "noul", "instructions": "Needs reply?",
                "criteria": {"true": "Today", "false": "Later"}})
CHOICE = QA({"key": "area", "type": "choice", "instructions": "Which area?",
             "criteria": [{"key": "billing", "description": "Invoices"}, {"key": "tech"}]})
SCORE = QA({"key": "anger", "type": "score", "instructions": "How angry?",
            "criteria": ["Calm", "Angry"]})
ALL = [NOUL, CHOICE, SCORE]


def endpoint(**kw):
    base = dict(base_url="http://so.test", model="nimble-latest", api_key=None, max_concurrency=4, service_id=1)
    return Endpoint(**{**base, **kw})


def ok_json(questions):
    answers = {}
    for q in questions:
        if q.type == "noul":
            answers[q.key] = {"type": "noul", "noul": 0.9}
        elif q.type == "choice":
            keys = [o.key for o in q.criteria]
            answers[q.key] = {"type": "choice", "choice": keys[0], "confidence": 0.4,
                              "probabilities": {k: 1 / len(keys) for k in keys}}
        else:
            answers[q.key] = {"type": "score", "score": 0.7, "confidence": 0.2,
                              "legend": {str(i): t for i, t in enumerate(q.criteria)},
                              "probabilities": {str(i): 1 / len(q.criteria) for i in range(len(q.criteria))}}
    return {"model": "nimble-latest", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 4}}


def transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []

    async def fake_sleep(seconds):
        recorded.append(seconds)

    monkeypatch.setattr(client, "_sleep", fake_sleep)
    return recorded


# ---------------------------------------------------------------- request body

def test_body_for_three_types():
    body = client.build_request_body("nimble-latest", "some text", [NOUL, NOUL_CRIT, CHOICE, SCORE])
    assert body["model"] == "nimble-latest" and body["state"] == "some text"
    qs = body["questions"]
    assert qs["urgent"] == {"type": "noul", "instructions": "Is it urgent?"}
    assert qs["reply"]["criteria"] == {"true": "Today", "false": "Later"}
    assert qs["area"]["criteria"] == {"billing": "Invoices", "tech": None}
    assert list(qs["area"]["criteria"]) == ["billing", "tech"]
    assert qs["anger"]["criteria"] == ["Calm", "Angry"]
    assert list(qs) == ["urgent", "reply", "area", "anger"]


async def test_posts_to_systemone_with_bearer_only_when_token():
    seen = []

    def handler(request):
        seen.append((request.url.path, request.headers.get("authorization")))
        return httpx.Response(200, json=ok_json(ALL))

    await client.evaluate(endpoint(api_key="tok"), "t", ALL, transport=transport(handler))
    await client.evaluate(endpoint(api_key=None), "t", ALL, transport=transport(handler))
    assert seen == [("/v1/systemone", "Bearer tok"), ("/v1/systemone", None)]


async def test_base_url_trailing_slash_is_tolerated():
    def handler(request):
        assert request.url.path == "/v1/systemone"
        return httpx.Response(200, json=ok_json([NOUL]))

    await client.evaluate(endpoint(base_url="http://so.test/"), "t", [NOUL], transport=transport(handler))


# ------------------------------------------------------------------- retries

async def test_retries_529_with_retry_after_then_succeeds(sleeps):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(529, headers={"Retry-After": "2"}, json={"error": {"message": "busy"}})
        return httpx.Response(200, json=ok_json([NOUL]))

    raw = await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert len(calls) == 3 and sleeps == [2.0, 2.0] and raw["answers"]["urgent"]["noul"] == 0.9


async def test_retry_after_is_capped(sleeps):
    def handler(request):
        return httpx.Response(529, headers={"Retry-After": "9999"}, json={"error": {"message": "busy"}})

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == "overloaded"
    assert sleeps and max(sleeps) <= 10


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "-5", "soon", ""])
async def test_a_retry_after_that_is_not_a_usable_number_falls_back_to_the_backoff(sleeps, value):
    """asyncio.sleep(nan) never returns: one such header would hold the service's slot forever."""
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(529, headers={"Retry-After": value}, json={"error": {"message": "busy"}})

    with pytest.raises(SystemOneError):
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert len(calls) == 3 and len(sleeps) == 2
    assert all(0 <= x <= 10 and x == x for x in sleeps)          # finite (x == x is false for nan), within the cap
    assert sleeps == [0.5, 1.0]


async def test_529_without_retry_after_backs_off_growing_then_gives_up(sleeps):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(529, json={"error": {"message": "busy"}})

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == "overloaded" and len(calls) == 3
    assert len(sleeps) == 2 and sleeps[0] < sleeps[1]


@pytest.mark.parametrize("status,kind", [(503, "unavailable"), (502, "unavailable")])
async def test_502_and_503_retry_then_unavailable(sleeps, status, kind):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "down"}})

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == kind and len(calls) == 3


@pytest.mark.parametrize("status,kind", [(422, "invalid_request"), (401, "unauthorized"), (403, "unauthorized"),
                                         (413, "invalid_request"), (400, "invalid_request")])
async def test_client_errors_never_retry(sleeps, status, kind):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == kind and e.value.status == status and len(calls) == 1 and sleeps == []


# --------------------------------------------------------------- error formats

async def test_error_message_formats():
    def custom(request):
        return httpx.Response(422, json={"error": {"message": "Context must be a nonempty string."}})

    def fastapi(request):
        return httpx.Response(422, json={"detail": [
            {"loc": ["body", "questions", "a", "choice", "criteria"],
             "msg": "Dictionary should have at least 2 items after validation, not 1"}]})

    with pytest.raises(SystemOneError) as e1:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(custom))
    with pytest.raises(SystemOneError) as e2:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(fastapi))
    assert "nonempty string" in e1.value.message
    assert "at least 2 items" in e2.value.message


async def test_non_json_error_body_still_gives_a_message():
    def handler(request):
        return httpx.Response(422, text="<html>bad</html>")

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == "invalid_request" and e.value.message


# ---------------------------------------------------------- invalid responses

def _mutate(fn):
    def handler(request):
        body = ok_json(ALL)
        fn(body)
        return httpx.Response(200, json=body)
    return handler


@pytest.mark.parametrize("mutation", [
    lambda b: b["answers"].pop("area"),                       # missing key
    lambda b: b.pop("answers"),                               # no answers
    lambda b: b["answers"].__setitem__("urgent", {"type": "noul"}),          # no noul value
    lambda b: b["answers"]["area"].pop("probabilities"),
    lambda b: b["answers"]["anger"].pop("legend"),
    lambda b: b["answers"].__setitem__("urgent", {"type": "mystery", "x": 1}),
    lambda b: b["answers"].__setitem__("urgent", {"type": "noul", "noul": "high"}),
])
async def test_malformed_server_answers_are_invalid_response(mutation):
    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", ALL, transport=transport(_mutate(mutation)))
    assert e.value.kind == "invalid_response"


async def test_non_json_200_is_invalid_response():
    def handler(request):
        return httpx.Response(200, text="not json")

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == "invalid_response"


# --------------------------------------------------------- transport failures

@pytest.mark.parametrize("exc,kind", [
    (httpx.ConnectError("refused"), "unavailable"),
    (httpx.ReadTimeout("slow"), "timeout"),
    (httpx.ConnectTimeout("slow"), "timeout"),
])
async def test_transport_errors_map_to_kinds(exc, kind):
    def handler(request):
        raise exc

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == kind


async def test_504_is_timeout():
    def handler(request):
        return httpx.Response(504, json={"error": {"message": "deadline"}})

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(), "t", [NOUL], transport=transport(handler))
    assert e.value.kind == "timeout"


# ---------------------------------------------------------------- concurrency

def _tracking_handler():
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.02)
        state["now"] -= 1
        return httpx.Response(200, json=ok_json([NOUL]))

    return state, handler


async def test_concurrency_cap():
    state, handler = _tracking_handler()
    ep = endpoint(max_concurrency=3, service_id=11)
    await asyncio.gather(*[client.evaluate(ep, "t", [NOUL], transport=transport(handler)) for _ in range(10)])
    assert state["peak"] == 3


async def test_concurrency_change_applies_without_restart():
    state, handler = _tracking_handler()
    await asyncio.gather(*[client.evaluate(endpoint(max_concurrency=1, service_id=12), "t", [NOUL],
                                           transport=transport(handler)) for _ in range(6)])
    assert state["peak"] == 1
    state["peak"] = 0
    await asyncio.gather(*[client.evaluate(endpoint(max_concurrency=4, service_id=12), "t", [NOUL],
                                           transport=transport(handler)) for _ in range(8)])
    assert state["peak"] == 4


async def test_services_do_not_share_slots():
    state, handler = _tracking_handler()
    a, b = endpoint(max_concurrency=1, service_id=21), endpoint(max_concurrency=1, service_id=22)
    await asyncio.gather(*[client.evaluate(e, "t", [NOUL], transport=transport(handler)) for e in (a, b)])
    assert state["peak"] == 2


# ---------------------------------------------------------------------- probe

async def test_probe_ok_returns_models_and_limits():
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": "nimble-latest"}, {"id": "bespokelabs/Bespoke-Nimble-9B"}]})
        if request.url.path == "/v1/limits":
            return httpx.Response(200, json={"max_questions": 64, "max_concurrent_requests": 4})
        return httpx.Response(404)

    out = await client.probe("http://so.test", "tok", transport=transport(handler))
    assert out["ok"] is True
    assert out["models"] == ["nimble-latest", "bespokelabs/Bespoke-Nimble-9B"]
    assert out["limits"]["max_concurrent_requests"] == 4


async def test_probe_server_down_is_a_result_not_an_exception():
    def handler(request):
        raise httpx.ConnectError("refused")

    out = await client.probe("http://so.test", None, transport=transport(handler))
    assert out["ok"] is False and out["models"] == [] and out["limits"] is None and out["message"]


async def test_probe_unauthorized_and_unhealthy():
    out = await client.probe("http://so.test", "bad", transport=transport(lambda r: httpx.Response(401, json={"error": {"message": "no"}})))
    assert out["ok"] is False and "401" in out["message"] or "token" in out["message"].lower()
    out = await client.probe("http://so.test", None, transport=transport(lambda r: httpx.Response(503, json={"status": "unavailable"})))
    assert out["ok"] is False


@pytest.mark.parametrize("url", ["ftp://x", "file:///etc/passwd", "no-scheme", "http://", ""])
async def test_probe_rejects_bad_urls(url):
    with pytest.raises(ValueError):
        await client.probe(url, None)


def test_default_max_concurrency():
    assert client.default_max_concurrency(4, 8) == 1
    assert client.default_max_concurrency(16, 4) == 4
    assert client.default_max_concurrency(None, 8) == 1
    assert client.default_max_concurrency(4, 1) == 4
    assert client.default_max_concurrency(4, 0) == 4


def test_endpoint_is_hashable_and_hides_token_in_repr():
    ep = endpoint(api_key="super-secret")
    assert "super-secret" not in repr(ep)
    assert json.dumps(client.build_request_body("m", "s", [NOUL]))


# ------------------------------------- one overall deadline, and no semaphores left behind

async def test_the_whole_call_has_a_deadline_not_just_each_http_phase(monkeypatch):
    monkeypatch.setattr(client, "_DEADLINE_S", 0.05)

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=ok_json(ALL))

    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(service_id=71), "text", ALL, transport=httpx.MockTransport(slow))
    assert e.value.kind == "timeout" and e.value.status is None


async def test_waiting_for_a_slot_counts_against_the_deadline(monkeypatch):
    monkeypatch.setattr(client, "_DEADLINE_S", 0.2)
    release = asyncio.Event()

    async def held(request):
        await release.wait()
        return httpx.Response(200, json=ok_json(ALL))

    ep = endpoint(service_id=72, max_concurrency=1)
    first = asyncio.create_task(client.evaluate(ep, "a", ALL, transport=httpx.MockTransport(held)))
    await asyncio.sleep(0.02)  # the first call owns the only slot
    monkeypatch.setattr(client, "_DEADLINE_S", 0.05)
    with pytest.raises(SystemOneError) as e:
        await client.evaluate(ep, "b", ALL, transport=httpx.MockTransport(held))
    assert e.value.kind == "timeout"
    release.set()
    first.cancel()


async def test_a_changed_cap_drops_the_previous_semaphore_of_that_service():
    loop = asyncio.get_running_loop()
    client._slot(endpoint(service_id=73, max_concurrency=2))
    client._slot(endpoint(service_id=74, max_concurrency=2))
    client._slot(endpoint(service_id=73, max_concurrency=5))
    held = client._slots_by_loop[loop]
    assert held[73][0] == 5 and held[74][0] == 2 and len(held) == 2


async def test_probe_treats_a_403_on_the_models_listing_as_a_rejected_token():
    # The hosted API answers 403 (authentication_error) when the key is missing: that is not a successful connection.
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(403, json={"detail": {"error_type": "authentication_error", "message": "Must supply an API key!"}})

    out = await client.probe("http://so.test", None, transport=transport(handler))
    assert out["ok"] is False and "token" in out["message"].lower()


async def test_probe_is_fine_without_a_limits_endpoint():
    # Not every server has /v1/limits: the connection works, nothing is known about its limits.
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "some-model"}]})
        return httpx.Response(404, json={"detail": "Not Found"})

    out = await client.probe("http://so.test", "tok", transport=transport(handler))
    assert out["ok"] is True and out["models"] == ["some-model"] and out["limits"] is None


def test_only_the_meanings_that_were_given_are_sent():
    only_yes = QA({"key": "u", "type": "noul", "instructions": "Urgent?", "criteria": {"true": "Today"}})
    both = QA({"key": "v", "type": "noul", "instructions": "Reply?", "criteria": {"true": "Today", "false": "Later"}})
    body = client.build_request_body("m", "text", [only_yes, both])["questions"]
    assert body["u"]["criteria"] == {"true": "Today"}
    assert body["v"]["criteria"] == {"true": "Today", "false": "Later"}


# ------------------------- servers without health / model endpoints (e.g. a hosted API with only /v1/systemone)

def _bare_server(request):
    return httpx.Response(404, json={"error": {"message": "This endpoint is not part of the serving API", "code": "not_found"}})


async def test_a_missing_health_endpoint_is_not_a_failure():
    out = await client.probe("http://so.test", "tok", transport=transport(_bare_server))
    assert out["ok"] is True and out["models"] == [] and out["limits"] is None
    assert out["can_list_models"] is False


async def test_a_server_that_lists_models_says_so():
    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "some-model"}]})
        return httpx.Response(404)

    out = await client.probe("http://so.test", "tok", transport=transport(handler))
    assert out["ok"] is True and out["models"] == ["some-model"] and out["can_list_models"] is True


async def test_an_empty_model_list_is_no_way_to_choose():
    def handler(request):
        return httpx.Response(200, json={"data": []}) if request.url.path == "/v1/models" else httpx.Response(404)

    out = await client.probe("http://so.test", "tok", transport=transport(handler))
    assert out["ok"] is True and out["can_list_models"] is False


async def test_a_health_endpoint_that_fails_is_still_a_failure():
    out = await client.probe("http://so.test", "tok", transport=transport(lambda r: httpx.Response(500, json={"detail": "boom"})))
    assert out["ok"] is False


# ---------------------------------------------------------------- the real check call

def _ok_handler(captured):
    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(200, json={"answers": {key: {"type": "noul", "noul": 0.9} for key in body["questions"]}})
    return handler


async def test_check_model_sends_one_tiny_question_with_the_chosen_model():
    sent = []
    out = await client.check_model(endpoint(model="the-model", service_id=81), transport=transport(_ok_handler(sent)))
    assert out["ok"] is True
    (body,) = sent
    assert body["model"] == "the-model" and len(body["questions"]) == 1 and len(body["state"]) < 50
    (question,) = body["questions"].values()
    assert question["type"] == "noul"


@pytest.mark.parametrize("status,body,fragment", [
    (401, {"error": {"message": "Invalid or missing API key."}}, "token"),
    (403, {"detail": "forbidden"}, "token"),
    (402, {"error": {"message": "no credit", "code": "insufficient_quota"}}, "credit"),
    (404, {"error": {"message": "not part of the serving API"}}, "URL"),
    (422, {"detail": [{"msg": "Unknown model: nope"}]}, "Unknown model"),
])
async def test_check_model_tells_which_part_is_wrong(status, body, fragment):
    out = await client.check_model(endpoint(service_id=82), transport=transport(lambda r: httpx.Response(status, json=body)))
    assert out["ok"] is False and fragment.lower() in out["message"].lower()


async def test_check_model_reports_a_server_that_is_down():
    def handler(request):
        raise httpx.ConnectError("refused")

    out = await client.check_model(endpoint(service_id=83), transport=transport(handler))
    assert out["ok"] is False and "connect" in out["message"].lower()


async def test_a_402_is_its_own_kind_not_a_rejected_request():
    with pytest.raises(SystemOneError) as e:
        await client.evaluate(endpoint(service_id=84), "t", [NOUL], transport=transport(lambda r: httpx.Response(402, json={"error": {"message": "no credit"}})))
    assert e.value.kind == "quota"


def test_the_color_preference_is_ours_and_never_sent_to_the_server():
    scored = QA({"key": "anger", "type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"], "color_start": "red"})
    body = client.build_request_body("m", "text", [scored])["questions"]["anger"]
    assert body == {"type": "score", "instructions": "How angry?", "criteria": ["Calm", "Angry"]}
