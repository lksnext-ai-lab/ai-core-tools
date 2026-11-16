"""Model switch between turns of one Chat conversation (app-flexible-chat step_012: FR-7, AC-4, R-3, R-4).

The user may pick another AI service, possibly of another provider, on every turn of the same conversation; the history
lives in one LangGraph checkpoint thread and the next turn's model receives what the previous provider produced. The Chat
runs a per-call ``HistoryNormalizerMiddleware``: a foreign-family AIMessage reaches the model as plain text + the same tool
calls, the checkpoint keeps the original, an unanswered tool call gets a synthetic ToolMessage in the view only; the
summary input is bounded by the summary model's window threshold and a lower target (``summary_trim_limits``).

Everything runs for real (router, ``InternalChatService``, execution/streaming services, real LangGraph checkpointer,
real ``SummarizationMiddleware``, the real normaliser, PostgreSQL) except the LLM boundary:
``tools.aiServiceTools.create_llm_from_service`` returns ``_provider_sim.SimChatModel`` - a thin SUBCLASS of the real
LangChain class of the provider (so the normaliser detects its family exactly as in production), recording what it receives,
answering with the message shapes the REAL provider adapters produce and validating the request with the REAL converter of
its provider. See ``_provider_sim`` for what is real and what is hand-written (tests/ids with ``sim_rule`` use hand-written
rules). Retriever and MCP tools come from the ``fakes`` fixture.

What "B accepts the history" PROVES here: B's own installed converter takes the messages, tool calls and tool messages are
paired, and (Mistral/Azure, whose converters forward foreign blocks) the content items are SDK item types. It does NOT prove
what a real API would do: Anthropic signature validation, OpenAI Responses reasoning/output item pairing, role alternation,
real token accounting, image size/mime limits.

The retired-service tests exercise the resolver guard only: the patch replaces ``create_llm_from_service`` (and with it its
``ensure_service_active``), so the 409 comes from the Chat resolver, not from the LLM builder.

Remaining findings are ``xfail(strict=True, raises=ProductFinding)``: ``ProductFinding`` is raised only when the turn failed
with the generic error AND the sim recorded the expected rejection for the expected service, so any other failure is a plain
test error. The assertions that do hold sit in separate passing tests.
"""
import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional

import pytest
from langchain.agents.middleware.summarization import _get_approximate_token_counter
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from models.ai_service import AIService
from models.app import App
from models.conversation import Conversation
from models.internal_chat import ChatConversationState, ConversationTurn
from models.mcp_config import MCPConfig
from models.silo import Silo
from tests.factories import AIServiceFactory, SkillFactory, configure_factories
from tests.integration.internal_chat._chat_support import (
    ThreadProbe,
    base,
    detail,
    parse_sse,
    selection,
    turn_form,
)
from tests.integration.internal_chat._provider_sim import (
    MODEL_NAMES,
    PROVIDERS,
    REASONING_PROVIDERS,
    SUMMARY_MARKER,
    TODAY_REASONING_PROVIDERS,
    ProviderRejected,
    Sim,
    SimChatModel,
    check_tool_pairing,
    has_image_block,
    has_reasoning_shape,
    real_model,
    reply,
    summary_text,
    validate_for,
)
from tests.integration.routers.internal._eos_helpers import past
from tools.middleware.history_normalizer import INTERRUPTED_TOOL_TEXT, model_family

KEEP = 20  # factory.py / SummarizationConfig.keep_messages default
BIG_WINDOW = 1_000_000  # profile window that never triggers a summary of the small histories below
ERROR_TEXT = "Agent execution failed"  # what the user sees when the turn's model call raises

REJECT_VISION = "ProviderRejected: this model does not accept image input"
REJECT_TOOLS = "ProviderRejected: this model does not support tool calling"
REJECT_MAIN = "ProviderRejected: injected provider error (main call)"
REJECT_SUMMARY = "ProviderRejected: injected provider error (summary call)"
REJECT_OLLAMA_URL = "ProviderRejected: Ollama: images must be base64 data, got a URL / non-base64 string"

pytestmark = pytest.mark.integration


class ProductFinding(AssertionError):
    """A real product shortcoming reproduced by a test (the only exception the strict xfails accept)."""


def raise_finding_if_rejected(out, sim, service_id: int, expected_rejection: str) -> None:
    """Pass when the turn succeeded; ProductFinding when it failed exactly because of the expected rejection."""
    if out.ok:
        return
    seen = (service_id, expected_rejection) in sim.rejections
    if ERROR_TEXT in out.error + out.body and seen:
        raise ProductFinding(f"turn failed with the generic error; the provider rejected it: {expected_rejection}")
    raise AssertionError(f"turn failed for another reason: {out.error!r} {out.body!r}; rejections={sim.rejections}")


# ------------------------------------------------------------------ fixtures and helpers


@pytest.fixture(autouse=True)
def threads(test_engine):
    return ThreadProbe(test_engine)


@pytest.fixture
def sim(db, world, fakes, monkeypatch):
    """One AI service per provider in the world's App, a second silo and a recording model per service."""
    configure_factories(db)
    app = db.get(App, world["app_id"])
    panel = Sim()
    for provider in PROVIDERS:
        service = AIServiceFactory(
            app=app, provider=provider, name=f"{provider}-svc", description=MODEL_NAMES[provider],
        )
        db.flush()
        panel.ids[provider] = service.service_id
        panel.provider_of[service.service_id] = provider
    silos = [Silo(name=f"sim-silo-{i}", app_id=world["app_id"], embedding_service_id=world["emb"]) for i in (1, 2)]
    db.add_all(silos)
    db.flush()
    panel.silo, panel.silo2 = silos[0].silo_id, silos[1].silo_id
    panel.retriever = f"retriever_silo_{panel.silo}"
    panel.retriever2 = f"retriever_silo_{panel.silo2}"
    db.commit()

    def sim_llm(ai_service, temperature=0, is_vision=False):
        service_id = ai_service.service_id
        profile = None  # the profile the real class carries
        if service_id in panel.windows:
            profile = {"max_input_tokens": panel.windows[service_id]} if panel.windows[service_id] else {}
        return SimChatModel(service_id, panel.provider_of[service_id], panel, profile=profile)

    monkeypatch.setattr("tools.aiServiceTools.create_llm_from_service", sim_llm)
    return panel


@dataclass
class Out:
    ok: bool
    status: int
    text: str = ""
    cid: Optional[int] = None
    turn: Optional[dict] = None
    metadata_turn: Optional[dict] = None
    events: list = field(default_factory=list)
    tokens: str = ""
    error: str = ""
    body: str = ""


def go(client, world, message, sel, cid=None, stream=False, files=None, extra_form=None) -> Out:
    """One turn over ``/messages`` or ``/stream``, whatever the outcome (no exception escapes)."""
    path = "/stream" if stream else "/messages"
    try:
        response = client.post(
            base(world["app_id"]) + path, headers=world["alice"], data={**turn_form(message, sel, cid), **(extra_form or {})}, files=files,
        )
    except Exception as exc:  # an unhandled server error surfacing through the test client
        return Out(False, 500, error=f"raised {type(exc).__name__}")
    if response.status_code != 200:
        return Out(False, response.status_code, error=response.text, body=response.text)
    if not stream:
        data = response.json()
        return Out(
            True, 200, text=data["response"], cid=data["conversation_id"], turn=data["turn"],
            metadata_turn=data["metadata"]["turn_config"], body=response.text,
        )
    events = parse_sse(response.text)
    errors = [e for e in events if e["type"] == "error"]
    done = next((e for e in events if e["type"] == "done"), None)
    metadata = next((e for e in events if e["type"] == "metadata"), None)
    tokens = "".join(e["data"]["content"] for e in events if e["type"] == "token")
    if errors or done is None:
        return Out(False, 200, events=events, error=json.dumps(errors), body=response.text, tokens=tokens,
                   cid=metadata["data"]["conversation_id"] if metadata else None)
    return Out(
        True, 200, text=done["data"]["response"], cid=done["data"]["conversation_id"], turn=done["data"]["turn"],
        metadata_turn=metadata["data"]["turn_config"], events=events, body=response.text, tokens=tokens,
    )


def conversation_ids(db, cid) -> tuple[int, str]:
    db.expire_all()
    row = db.get(Conversation, cid)
    return row.agent_id, row.session_id


def turn_rows(db, cid) -> list[ConversationTurn]:
    db.expire_all()
    return db.query(ConversationTurn).filter_by(conversation_id=cid).order_by(ConversationTurn.turn_index).all()


def busy_marker(db, cid):
    db.expire_all()
    state = db.get(ChatConversationState, cid)
    return state.busy_until, state.busy_token


def stored_selection_service(db, cid) -> int:
    db.expire_all()
    return db.get(ChatConversationState, cid).selection["ai_service_id"]


def checkpoint_messages(test_engine, db, cid) -> list:
    """The messages of the conversation's LangGraph checkpoint (latest), read with the checkpointer's own serializer."""
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    agent_id, session_id = conversation_ids(db, cid)
    url = test_engine.url.render_as_string(hide_password=False).replace("+psycopg2", "").replace("+psycopg", "")
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        found = PostgresSaver(conn).get_tuple({"configurable": {"thread_id": f"thread_{agent_id}_{session_id}"}})
    assert found is not None, "the conversation has no checkpoint"
    return list(found.checkpoint["channel_values"].get("messages", []))


def inject_unanswered_tool_call(test_engine, db, cid, tool_name: str) -> str:
    """Append ``human + AIMessage(tool call)`` with no ToolMessage to the conversation's checkpoint (a new checkpoint
    written through the checkpointer itself, as an interrupted turn would leave it). Returns the tool call id."""
    import copy

    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.base.id import uuid6
    from psycopg.rows import dict_row

    agent_id, session_id = conversation_ids(db, cid)
    url = test_engine.url.render_as_string(hide_password=False).replace("+psycopg2", "").replace("+psycopg", "")
    call_id = "call_interrupted_0001"
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        saver = PostgresSaver(conn)
        config = {"configurable": {"thread_id": f"thread_{agent_id}_{session_id}"}}
        found = saver.get_tuple(config)
        checkpoint = copy.deepcopy(found.checkpoint)
        messages = list(checkpoint["channel_values"]["messages"]) + [
            HumanMessage("use the tool", id="interrupted-human"),
            AIMessage("", tool_calls=[{"name": tool_name, "args": {"query": "q"}, "id": call_id}], id="interrupted-ai"),
        ]
        version = saver.get_next_version(checkpoint["channel_versions"].get("messages"), None)
        checkpoint["id"] = str(uuid6())
        checkpoint["channel_values"] = {"messages": messages}
        checkpoint["channel_versions"] = {**checkpoint["channel_versions"], "messages": version}
        metadata = {"source": "update", "step": found.metadata.get("step", 0) + 1, "parents": {}}
        saver.put(found.config, checkpoint, metadata, {"messages": version})
    return call_id


BASE_TOOL = "download_url_to_workspace"  # bound on every turn (agentTools: "Base tools - always available")


def selected_tools(call) -> list[str]:
    """The tools of a model call that come from the user's selection (silo / MCP), without the always-on base tool."""
    return [t for t in call.bound_tools if t != BASE_TOOL]


def tools_in(messages) -> list[tuple[str, str]]:
    """(kind, tool call id) of every tool call / tool message of a received history."""
    found = []
    for message in messages:
        if isinstance(message, AIMessage):
            found += [("call", tc["id"]) for tc in message.tool_calls]
        elif isinstance(message, ToolMessage):
            found.append(("result", message.tool_call_id))
    return found


def block_types(message) -> list[str]:
    if isinstance(message.content, str):
        return ["str"]
    return [b["type"] if isinstance(b, dict) else "str" for b in message.content]


def has_reasoning_marker(message: AIMessage, provider: str, shape: str) -> bool:
    """The provider-specific reasoning artefact of ``shape`` is present in the message (precondition of the variants)."""
    if provider == "OpenAI":
        return "reasoning" in block_types(message)
    if provider == "Anthropic":
        return "thinking" in block_types(message)
    if provider == "Google":
        if shape == "full":
            return "thinking" in block_types(message)
        return "__gemini_function_call_thought_signatures__" in message.additional_kwargs or any(
            isinstance(b, dict) and (b.get("extras") or {}).get("signature") for b in message.content
            if not isinstance(message.content, str)
        )
    return False


def is_plain(message: AIMessage) -> bool:
    return isinstance(message.content, str) and not message.additional_kwargs


def assert_normalised(got: AIMessage, original: AIMessage) -> None:
    """A foreign-family AIMessage as the next model receives it: text + the same tool calls and ids, nothing else."""
    assert isinstance(got.content, str) and got.content == original.text
    assert got.tool_calls == original.tool_calls
    assert got.id == original.id
    assert got.additional_kwargs == {}
    if not is_plain(original):
        assert got.response_metadata == {}


# ------------------------------------------------------------------ the simulation itself (can it fail?)


def product_service(provider: str, endpoint=None):
    """Stand-in for an AIService row, with what the product's builders read."""
    return SimpleNamespace(
        description=MODEL_NAMES[provider], api_key="x", endpoint=endpoint, api_version="2024-05-01-preview", name="svc",
        provider=provider,
    )


def product_model(provider: str, endpoint=None):
    """The object ``tools.aiServiceTools`` builds for the provider (its own builders, no network at construction)."""
    from tools import aiServiceTools as built

    service = product_service(provider, endpoint)
    import warnings

    with warnings.catch_warnings():  # AzureAIChatCompletionsModel "currently in preview" (pytest's warnings plugin is off)
        warnings.filterwarnings("ignore", message=".*is currently in preview.*")
        return _product_builders(built, service)[provider]()


def _product_builders(built, service) -> dict:
    return {
        "OpenAI": lambda: built._build_openai_llm(service, 0),
        "Anthropic": lambda: built._build_anthropic_llm(service, 0),
        "MistralAI": lambda: built._build_mistral_llm(service, 0, False),
        "Azure": lambda: built._build_azure_llm(service, 0),
        "Google": lambda: built._build_google_llm(service, 0),
        "Custom": lambda: built._build_custom_llm(service, 0),
    }


class TestSimulatorFidelity:
    """The fakes are only evidence if their class, shapes and validation are the real ones and can fail."""

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_the_sim_model_is_detected_as_the_family_of_the_real_class(self, provider):
        endpoint = "http://example.invalid" if provider in ("Azure", "Custom") else None
        if provider == "Azure":
            endpoint = "https://example.invalid/models"
        built = product_model(provider, endpoint)
        simulated = SimChatModel(1, provider, Sim())
        assert isinstance(simulated, type(built))
        assert model_family(simulated) == model_family(built) == model_family(real_model(provider)) is not None
        assert model_family(simulated.bind_tools([StructuredTool.from_function(lambda: "x", name="t", description="d")])) \
            == model_family(built)
        assert simulated._llm_type == built._llm_type

    def test_openai_with_a_custom_endpoint_is_the_chat_completions_family(self):
        sim = Sim()
        built = product_model("OpenAI", endpoint="https://gateway.example/v1")
        assert built.use_responses_api is False  # aiServiceTools._build_openai_llm: ``use_responses_api=base_url is None``
        simulated = SimChatModel(1, "OpenAI", sim, use_responses_api=False, base_url="https://gateway.example/v1")
        assert model_family(simulated) == model_family(built) == "openai-chat"
        assert model_family(SimChatModel(1, "OpenAI", sim)) == "openai-responses"

    def test_replies_have_the_shape_each_adapter_produces_in_full_shape(self):
        tool = ("retriever_silo_1", {"query": "q"})
        openai = reply("OpenAI", "hi", tool)
        assert block_types(openai) == ["reasoning", "text", "function_call"]
        assert openai.response_metadata["model_provider"] == "openai" and openai.id.startswith("resp_")
        assert openai.usage_metadata["output_token_details"] == {"reasoning": 3}
        anthropic = reply("Anthropic", "hi", tool)
        assert block_types(anthropic) == ["thinking", "text", "tool_use"]
        assert anthropic.content[0]["signature"] and anthropic.response_metadata["model_provider"] == "anthropic"
        google = reply("Google", "hi", tool)
        assert block_types(google)[0] == "thinking" and google.content[0]["signature"]
        assert google.response_metadata["model_provider"] == "google_genai"
        assert google.additional_kwargs["function_call"]["name"] == "retriever_silo_1"
        mistral = reply("MistralAI", "hi", tool)
        assert mistral.content == "hi" and mistral.additional_kwargs["tool_calls"][0]["function"]["name"] == tool[0]
        assert len(mistral.tool_calls[0]["id"]) == 9  # Mistral ids are exactly 9 characters
        azure = reply("Azure", "hi", tool)
        assert azure.content == "hi" and azure.tool_calls[0]["id"].startswith("call_az")
        custom = reply("Custom", "hi", tool)
        assert custom.content == "hi" and custom.response_metadata["model_provider"] == "ollama"
        assert custom.response_metadata["done_reason"] == "stop" and len(custom.tool_calls[0]["id"]) == 36  # uuid4

    def test_replies_in_the_shape_production_produces_today(self):
        tool = ("retriever_silo_1", {"query": "q"})
        assert block_types(reply("Anthropic", "hi", tool, shape="today")) == ["text", "tool_use"]  # no ``thinking`` enabled
        openai = reply("OpenAI", "hi", tool, shape="today")
        assert block_types(openai) == ["reasoning", "text", "function_call"] and openai.content[0]["summary"] == []
        google = reply("Google", "hi", tool, shape="today")  # no include_thoughts: signatures, no ``thinking`` block
        assert block_types(google) == ["text"] and google.content[0]["extras"]["signature"]
        assert google.additional_kwargs["__gemini_function_call_thought_signatures__"]
        for provider in ("MistralAI", "Azure", "Custom"):
            assert reply(provider, "hi", reasoning=True, shape="today").content == "hi"
        assert not has_reasoning_shape("Anthropic", "today") and has_reasoning_shape("Anthropic", "full")

    def test_sim_rule_tool_pairing_rejects_orphan_calls_and_messages(self):
        call = reply("OpenAI", "", ("retriever_silo_1", {"query": "q"}), reasoning=False)
        with pytest.raises(ProviderRejected, match="no tool message"):
            check_tool_pairing([HumanMessage("q"), call, HumanMessage("next")])
        with pytest.raises(ProviderRejected, match="orphan tool call"):
            check_tool_pairing([HumanMessage("q"), call])
        with pytest.raises(ProviderRejected, match="answers no pending"):
            check_tool_pairing([HumanMessage("q"), ToolMessage("x", tool_call_id="nope", name="t")])
        check_tool_pairing([HumanMessage("q"), call, ToolMessage("x", tool_call_id=call.tool_calls[0]["id"], name="t")])

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_the_validation_of_every_provider_applies_the_pairing_rule(self, provider):
        call = reply(provider, "", ("retriever_silo_1", {"query": "q"}), reasoning=False)
        with pytest.raises(ProviderRejected, match="no tool message"):
            validate_for(provider, [HumanMessage("q"), call, HumanMessage("next")])
        paired = [HumanMessage("q"), call, ToolMessage("x", tool_call_id=call.tool_calls[0]["id"], name="t"),
                  HumanMessage("next")]
        validate_for(provider, paired)

    @pytest.mark.parametrize("target,source,exc,match", [
        # Constraints of the REAL converters of B for what the provider A produced.
        ("Google", "OpenAI", KeyError, "reasoning"),                   # langchain_google_genai: block["reasoning"] lookup
        ("Custom", "OpenAI", ValueError, "Unsupported message content type"),     # langchain_ollama: unknown block type
        ("Custom", "Anthropic", ValueError, "Unsupported message content type"),  # ``thinking`` / ``tool_use`` blocks
        ("Custom", "Google", ValueError, "Unsupported message content type"),     # ``thinking`` block
    ])
    def test_the_real_converter_of_b_raises_on_foreign_blocks(self, target, source, exc, match):
        message = reply(source, "answer", reasoning=True)
        with pytest.raises(exc, match=match):
            validate_for(target, [HumanMessage("q"), message, HumanMessage("next")])
        validate_for(target, [HumanMessage("q"), reply(source, "answer", reasoning=False), HumanMessage("next")])

    @pytest.mark.parametrize("target,pattern", [("Azure", "Azure: content item of unknown type"),
                                                ("MistralAI", "Mistral: content item of unknown type")])
    @pytest.mark.parametrize("source", sorted(REASONING_PROVIDERS))
    def test_sim_rule_mistral_and_azure_wire_content_items_are_sdk_item_types(self, target, pattern, source):
        """These converters forward foreign blocks, so the sim checks the converter OUTPUT against the SDK item types."""
        with pytest.raises(ProviderRejected, match=pattern):
            validate_for(target, [HumanMessage("q"), reply(source, "a", reasoning=True), HumanMessage("n")])
        validate_for(target, [HumanMessage("q"), HumanMessage([{"type": "text", "text": "ok"}]), AIMessage("fine")])

    def test_sim_rule_ollama_images_must_be_base64(self):
        url = HumanMessage([{"type": "text", "text": "d"}, {"type": "image_url", "image_url": {"url": "https://h/x.png"}}])
        with pytest.raises(ProviderRejected, match="images must be base64"):
            validate_for("Custom", [url])
        data = HumanMessage([{"type": "text", "text": "d"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}])
        validate_for("Custom", [data])


# ------------------------------------------------------------------ 1: provider switch matrix

# variant -> (reasoning flag, reply shape, providers A that have this shape)
VARIANTS = {
    "plain": (False, "today", PROVIDERS),
    "reasoning-today": (True, "today", sorted(TODAY_REASONING_PROVIDERS)),
    "thinking-not-produced-today": (True, "full", sorted(REASONING_PROVIDERS)),
}


def _variant_pairs(variant: str):
    return [pytest.param(variant, a, b, id=f"{variant}-{a}-to-{b}") for a in VARIANTS[variant][2] for b in PROVIDERS]


ALL_PAIRS = [p for v in VARIANTS for p in _variant_pairs(v)]


def run_two_turns(client, db, test_engine, world, sim, a, b, stream, variant):
    reasoning, shape, _ = VARIANTS[variant]
    sim.reasoning, sim.shape = reasoning, shape
    sim.call_tool[sim.ids[a]] = sim.retriever
    first = go(client, world, "turn one question", selection(sim.ids[a], silo=sim.silo), stream=stream)
    assert first.ok, first.error
    sim.after_first = len(sim.calls)  # calls before this index belong to turn 1 (A may be the same service as B)
    before = checkpoint_messages(test_engine, db, first.cid)
    sim.call_tool.pop(sim.ids[b], None)  # B never calls the tool (matters when A and B are the same service)
    second = go(client, world, "turn two question", selection(sim.ids[b], silo=sim.silo), first.cid, stream=stream)
    return first, second, before


def check_second_turn(client, db, test_engine, world, sim, threads, a, b, first, second, before, stream, variant):
    A, B = sim.ids[a], sim.ids[b]
    reasoning, shape, _ = VARIANTS[variant]
    assert second.text == f"hello from {B}"
    # B ran its own turn once: no tool call, no summary; A saw only turn 1.
    turn_one, turn_two = sim.calls[:sim.after_first], sim.calls[sim.after_first:]
    assert [(c.service_id, c.is_summary) for c in turn_one] == [(A, False), (A, False)]  # tool call, then the answer
    assert [(c.service_id, c.is_summary) for c in turn_two] == [(B, False)]
    if reasoning:  # the variant really exercises the provider's reasoning artefact
        assert has_reasoning_marker(turn_one[0].answer, a, shape), block_types(turn_one[0].answer)
    # The checkpoint after turn 1 holds A's own messages (human, AI tool call, tool result, AI answer).
    assert [m.type for m in before] == ["human", "ai", "tool", "ai"]
    assert before[1].tool_calls and before[3].text == f"hello from {A}"
    received = turn_two[0].messages  # the sim ran B's real converter (and its sim rules) on exactly this
    assert [m.type for m in received] == ["system", "human", "ai", "tool", "ai", "human"]
    assert received[1] == before[0] and received[3] == before[2]  # human and tool messages untouched
    assert received[-1].text == "turn two question"
    if a == b:  # own family: A's messages arrive unchanged (content, additional_kwargs, response_metadata, ids)
        assert received[1:5] == before
    else:  # foreign family: the normalised form, the same tool calls, ids and pairing
        assert_normalised(received[2], before[1])
        assert_normalised(received[4], before[3])
        assert received[3].tool_call_id == received[2].tool_calls[0]["id"] == before[1].tool_calls[0]["id"]
    check_tool_pairing(received)
    assert received[3].name == sim.retriever
    assert not sim.rejections

    # The CHECKPOINT still holds A's original messages after B's turn (the normalisation is a per-call view only).
    after = checkpoint_messages(test_engine, db, first.cid)
    assert after[:4] == before, "B's turn rewrote A's messages in the checkpoint"
    assert [m.type for m in after] == ["human", "ai", "tool", "ai", "human", "ai"]

    # The turn rows record the model of each turn, with consecutive indexes.
    rows = turn_rows(db, second.cid)
    assert [(r.turn_index, r.ai_service_id, r.ai_model_name) for r in rows] == [
        (1, A, MODEL_NAMES[a]), (2, B, MODEL_NAMES[b]),
    ]
    assert (first.turn["ai_service_id"], second.turn["ai_service_id"]) == (A, B)
    assert second.metadata_turn["ai_service"]["id"] == B  # metadata (sync body / stream event) shows B
    # The history API reads the checkpoint back: no provider payload leaks into the text.
    messages = detail(client, world, second.cid)["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "turn one question"), ("agent", f"hello from {A}"),
        ("user", "turn two question"), ("agent", f"hello from {B}"),
    ]
    assert [m["turn"]["ai_service_id"] for m in messages if m["role"] == "agent"] == [A, B]
    # One thread for the whole conversation.
    agent_id, session_id = conversation_ids(db, second.cid)
    assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{session_id}"}
    if stream:
        assert second.tokens == f"hello from {B}"
        assert not [e for e in second.events if e["type"] == "error"]
        assert second.events[-1]["type"] == "done"

    # A later turn back on A receives its own original messages untouched.
    sim.call_tool.pop(A, None)
    calls_before = len(sim.calls)
    third = go(client, world, "turn three question", selection(A, silo=sim.silo), first.cid, stream=stream)
    assert third.ok, third.error
    back = sim.calls[calls_before].messages
    assert back[1:5] == before, "A did not get its own messages back unchanged"
    assert [m.text for m in back if m.type == "human"] == ["turn one question", "turn two question", "turn three question"]
    assert not sim.rejections


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
class TestProviderSwitchMatrix:
    """All ordered provider pairs x history shape x /messages and /stream; every pair is a plain passing test."""

    @pytest.mark.parametrize("variant,a,b", ALL_PAIRS)
    def test_history_of_a_reaches_b_in_the_form_b_accepts(
        self, client, db, test_engine, world, sim, threads, variant, a, b, stream
    ):
        """``plain``: tool call + result + answer as the adapter produces them today; ``reasoning-today``: OpenAI
        reasoning items / Gemini thought signatures (produced today); ``thinking-not-produced-today``: Anthropic
        ``thinking``, Gemini ``thinking`` blocks, OpenAI reasoning summaries (one client flag away)."""
        first, second, before = run_two_turns(client, db, test_engine, world, sim, a, b, stream, variant)
        assert second.ok, second.error
        check_second_turn(client, db, test_engine, world, sim, threads, a, b, first, second, before, stream, variant)


# A rejection that still exists (the history normalisation fixed the converter rejections): capability and provider errors.
REJECTIONS = {
    # case -> (first-turn text, rejection recorded by the sim)
    "vision": ("describe this", REJECT_VISION),
    "tools": ("plain question", REJECT_TOOLS),
    "injected-error": ("plain question", REJECT_MAIN),
}

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000005000100"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
@pytest.mark.parametrize("case", sorted(REJECTIONS))
class TestARejectedSwitchFailsCleanly:
    """When B's provider rejects the turn (no vision, no tool calling, a provider error) the failure is contained.

    The converter rejections of cross-provider histories no longer exist (see the matrix); these are the rejections that
    remain, emulated by the sim at CALL time like a real server's 4xx.
    """

    def _fail(self, client, world, sim, case, stream):
        sim.reasoning = False
        first_text, rejection = REJECTIONS[case]
        A, B = sim.ids["OpenAI"], sim.ids["Custom"]
        files = [("files", ("pic.png", PNG, "image/png"))] if case == "vision" else None
        first = go(client, world, first_text, selection(A), stream=stream, files=files)
        assert first.ok, first.error
        {"vision": sim.no_vision, "tools": sim.no_tools, "injected-error": sim.fail_main}[case].add(B)
        second = go(client, world, "turn two question", selection(B), first.cid, stream=stream)
        return A, B, first, second, first_text, rejection

    def test_conversation_busy_marker_and_history_survive(self, client, db, test_engine, world, sim, case, stream):
        sim.reasoning = False
        A, B, first, second, first_text, rejection = self._fail(client, world, sim, case, stream)
        assert not second.ok
        assert sim.rejections == [(B, rejection)], "exactly one rejection, B's own"
        # What the user sees: a generic failure that carries nothing of A's payload.
        for leaked in ("thinking", "signature", "reasoning", "tool_use", "toolu_", "injected provider error"):
            assert leaked not in (second.error + second.body)
        assert ERROR_TEXT in second.error + second.body
        # Nothing of the failed turn was persisted, the busy marker is released, the stored selection is still A's.
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]
        assert busy_marker(db, first.cid) == (None, None)
        assert stored_selection_service(db, first.cid) == A
        # Like the playground, the failed turn's question stays in the checkpoint (LangGraph saves the input before the
        # model call): the history shows it without an answer; no turn row, no answer.
        shown = [(m["role"], m["content"]) for m in detail(client, world, first.cid)["messages"]]
        # The history API marks an uploaded image in the user's text as ``<text> [IMAGE:<hash>]``.
        want_first = rf"{first_text} \[IMAGE:[0-9a-f]+\]" if case == "vision" else re.escape(first_text)
        assert len(shown) == 3 and re.fullmatch(want_first, shown[0][1]) and shown[0][0] == "user"
        assert shown[1][0] == "agent" and shown[1][1] == f"hello from {A}"
        # Observed: in a conversation with an upload the history API also appends the marker to the later user message
        # that has no file of its own; accepted here, reported (not asserted away) in the step report.
        assert shown[2][0] == "user" and re.fullmatch(r"turn two question( \[IMAGE:[0-9a-f]+\])?", shown[2][1])
        stored = checkpoint_messages(test_engine, db, first.cid)
        assert [m.type for m in stored] == ["human", "ai", "human"]
        # And the conversation keeps working with a model that accepts the history.
        third = go(client, world, "turn three question", selection(A), first.cid, stream=stream)
        assert third.ok, third.error
        assert third.turn["turn_index"] == 2
        assert [m.text for m in sim.main_calls(A)[-1].messages if m.type == "human"] == [
            first_text, "turn two question", "turn three question"]


# ------------------------------------------------------------------ 2: tool-call history across a switch

CYCLE = list(zip(PROVIDERS, PROVIDERS[1:] + PROVIDERS[:1]))


@pytest.fixture
def mcps(db, world):
    config = MCPConfig(name="alpha-mcp", config={"alpha": {"url": "http://x", "transport": "streamable_http"}},
                       app_id=world["app_id"])
    db.add(config)
    db.commit()
    return config.config_id


@pytest.mark.parametrize("a,b", CYCLE, ids=[f"{a}-to-{b}" for a, b in CYCLE])
class TestToolCallHistoryAcrossASwitch:
    def _turn_one(self, client, world, sim, a, sel_kwargs, tool):
        sim.reasoning = False
        sim.call_tool[sim.ids[a]] = tool
        first = go(client, world, "use the tool", selection(sim.ids[a], **sel_kwargs))
        assert first.ok, first.error
        return first

    def test_the_tool_b_was_not_given_may_still_be_in_the_history_other_silo(self, client, world, sim, a, b):
        first = self._turn_one(client, world, sim, a, {"silo": sim.silo}, sim.retriever)
        second = go(client, world, "next", selection(sim.ids[b], silo=sim.silo2), first.cid)
        assert second.ok, second.error
        call = sim.main_calls(sim.ids[b])[0]
        assert selected_tools(call) == [sim.retriever2], "B is offered its own silo's retriever only"
        assert [t for t in tools_in(call.messages)][0][0] == "call"
        assert [m.name for m in call.messages if isinstance(m, ToolMessage)] == [sim.retriever]
        assert second.text == f"hello from {sim.ids[b]}"

    def test_the_tool_b_was_not_given_may_still_be_in_the_history_no_silo(self, client, world, sim, a, b):
        first = self._turn_one(client, world, sim, a, {"silo": sim.silo}, sim.retriever)
        second = go(client, world, "next", selection(sim.ids[b]), first.cid)
        assert second.ok, second.error
        call = sim.main_calls(sim.ids[b])[0]
        assert selected_tools(call) == []
        assert len(tools_in(call.messages)) == 2 and second.text == f"hello from {sim.ids[b]}"

    def test_the_tool_b_was_not_given_may_still_be_in_the_history_mcp_removed(self, client, world, sim, a, b, mcps):
        first = self._turn_one(client, world, sim, a, {"mcps": [mcps]}, "mcp_alpha")
        assert [m.name for m in sim.main_calls(sim.ids[a])[-1].messages if isinstance(m, ToolMessage)] == ["mcp_alpha"]
        second = go(client, world, "next", selection(sim.ids[b]), first.cid)
        assert second.ok, second.error
        call = sim.main_calls(sim.ids[b])[0]
        assert "mcp_alpha" not in call.bound_tools and [m.name for m in call.messages if isinstance(m, ToolMessage)] == ["mcp_alpha"]

    def test_b_has_tools_a_had_none_and_the_next_turn_goes_back_to_a(self, client, db, world, sim, a, b):
        sim.reasoning = False
        A, B = sim.ids[a], sim.ids[b]
        sim.call_tool[B] = sim.retriever
        first = go(client, world, "plain question", selection(A))
        assert first.ok and not tools_in(sim.main_calls(A)[0].messages)
        second = go(client, world, "use the tool", selection(B, silo=sim.silo), first.cid)
        assert second.ok, second.error
        assert len(sim.main_calls(B)) == 2 and selected_tools(sim.main_calls(B)[0]) == [sim.retriever]
        third = go(client, world, "back to A without tools", selection(A), first.cid)
        assert third.ok, third.error
        received = sim.main_calls(A)[-1]
        assert selected_tools(received) == [] and [k for k, _ in tools_in(received.messages)] == ["call", "result"]
        assert [m.text for m in received.messages if m.type == "human"] == [
            "plain question", "use the tool", "back to A without tools"]
        assert [(r.turn_index, r.ai_service_id) for r in turn_rows(db, first.cid)] == [(1, A), (2, B), (3, A)]


class TestSkillRemovedBetweenTurns:
    def test_b_does_not_inherit_a_skill_prompt_from_the_history(self, client, db, world, sim):
        configure_factories(db)
        skill = SkillFactory(app=db.get(App, world["app_id"]), name="skill-alpha", description="ALPHA-DESC")
        db.commit()
        A, B = sim.ids["Anthropic"], sim.ids["OpenAI"]
        sim.reasoning = False
        first = go(client, world, "q1", selection(A, skills=[skill.skill_id]))
        assert first.ok, first.error
        second = go(client, world, "q2", selection(B), first.cid)
        assert second.ok, second.error
        call_a, call_b = sim.main_calls(A)[0], sim.main_calls(B)[0]
        assert "skill-alpha" in call_a.messages[0].text and "load_skill" in call_a.bound_tools
        assert "skill-alpha" not in call_b.messages[0].text and "load_skill" not in call_b.bound_tools
        assert all("skill-alpha" not in m.text for m in call_b.messages[1:]), "a skill lives in the system prompt only"
        assert [(m.type, m.text) for m in call_b.messages[1:]] == [
            ("human", "q1"), ("ai", f"hello from {A}"), ("human", "q2")]


# ------------------------------------------------------------------ 3 and 4: summarization with the turn's model


def window_for(threshold: int) -> int:
    """A profile window whose default trigger (85%, capped at 150k) is exactly ``threshold`` tokens."""
    window = int(threshold / 0.85)
    while min(int(window * 0.85), 150_000) < threshold:
        window += 1
    assert min(int(window * 0.85), 150_000) == threshold
    return window


def question(i: int, chars: int) -> str:
    return f"Q{i:03d} ".ljust(chars, "x")


class History:
    """A conversation grown through the real endpoints, with the token arithmetic of the summarization trigger."""

    def __init__(self, client, world, sim):
        self.client, self.world, self.sim = client, world, sim
        self.cid: Optional[int] = None
        self.index = 0

    def turn(self, service_id, chars, stream=False, text=None) -> Out:
        text = text or question(self.index, chars)
        self.index += 1
        out = go(self.client, self.world, text, selection(service_id), self.cid, stream=stream)
        if out.ok:
            self.cid = out.cid
        return out

    def state(self) -> list:
        """The checkpoint's messages after the last completed turn (what the last model call saw, plus its answer)."""
        last = [c for c in self.sim.calls if not c.is_summary][-1]
        return [m for m in last.messages if not isinstance(m, SystemMessage)] + [last.answer]

    def counter(self, service_id):
        """The token counter the summarization built for this turn's model uses (it keys on the model class)."""
        model = SimChatModel(service_id=service_id, provider=self.sim.provider_of[service_id], sim=self.sim)
        return _get_approximate_token_counter(model)

    def tokens_if(self, service_id, human_text) -> int:
        return self.counter(service_id)(self.state() + [HumanMessage(human_text)])

    def human_with_tokens(self, service_id, target) -> str:
        """The shortest question text that makes the pre-model history exactly ``target`` tokens for this model."""
        low, high = 1, 2_000_000
        while low < high:
            mid = (low + high) // 2
            if self.tokens_if(service_id, "Q".ljust(mid, "x")) >= target:
                high = mid
            else:
                low = mid + 1
        text = "Q".ljust(low, "x")
        assert self.tokens_if(service_id, text) == target
        return text


def grow(history: History, service_id: int, turns: int, chars: int = 800) -> None:
    history.sim.windows[service_id] = BIG_WINDOW
    for _ in range(turns):
        out = history.turn(service_id, chars)
        assert out.ok, out.error
    assert not history.sim.summary_calls()


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
@pytest.mark.parametrize("big,small", [("OpenAI", "Anthropic"), ("Anthropic", "OpenAI")], ids=["small=Anthropic", "small=OpenAI"])
class TestSummarizationUsesTheTurnsModel:
    def test_the_trigger_the_summary_call_and_the_kept_messages_follow_the_current_turn(
        self, client, db, world, sim, threads, big, small, stream
    ):
        sim.reasoning = False
        X, Y = sim.ids[big], sim.ids[small]
        history = History(client, world, sim)
        grow(history, X, 12)  # 24 messages, far below 150k tokens, model X has a huge window
        state = history.state()
        assert len(state) == 24

        # The token counter is the turn model's: the same messages count differently for Anthropic (3.3 chars/token).
        probe = question(99, 800)
        assert history.tokens_if(X, probe) != history.tokens_if(Y, probe)

        # Just below Y's trigger (threshold = tokens + 1): no summarization at all, Y answers with the full history.
        below_text = question(12, 800)
        sim.windows[Y] = window_for(history.tokens_if(Y, below_text) + 1)
        sim.windows.pop(X)
        out = history.turn(Y, 800, text=below_text)
        assert out.ok, out.error
        assert not sim.summary_calls()
        assert len(sim.main_calls(Y)[-1].messages) == 1 + 24 + 1  # system + whole history + the new question

        # At exactly Y's trigger (tokens == threshold) the summarization runs, built with Y.
        state = history.state()
        assert len(state) == 26
        trigger_text = question(13, 800)
        pre_tokens = history.tokens_if(Y, trigger_text)
        sim.windows[Y] = window_for(pre_tokens)
        before = len(sim.calls)
        out = history.turn(Y, 800, stream=stream, text=trigger_text)
        assert out.ok, out.error
        new_calls = sim.calls[before:]
        assert [(c.service_id, c.is_summary) for c in new_calls] == [(Y, True), (Y, False)], \
            "the summary is written by the turn's model (Y), before Y's own answer; X is not involved"
        summary_call, main_call = new_calls
        assert not sim.summary_calls(X)
        # The summary prompt carries the oldest messages, not the kept ones (26 + new = 27 messages, keep 20).
        prompt = summary_call.messages[0].text
        assert SUMMARY_MARKER in prompt and "Q000" in prompt
        assert "Q003" in prompt and "Q004" not in prompt  # messages 0..6 (Q000..Q003) are summarized, 7.. are kept
        # The model call afterwards: system + summary message + the last 20 messages (the new question included).
        kept = state[-(KEEP - 1):] + [HumanMessage(trigger_text)]
        assert [(m.type, m.text) for m in main_call.messages[2:]] == [(m.type, m.text) for m in kept]
        assert len(main_call.messages) == 2 + KEEP
        summary_message = main_call.messages[1]
        assert summary_message.type == "human" and summary_message.additional_kwargs["lc_source"] == "summarization"
        assert summary_text(Y) in summary_message.text
        assert main_call.tokens < pre_tokens

        # The next turn goes back to X (huge window): it reads the summarized history correctly, no new summary.
        before = len(sim.calls)
        out = history.turn(X, 800, stream=stream)
        assert out.ok, out.error
        (x_call,) = sim.calls[before:]
        assert not x_call.is_summary and x_call.service_id == X
        texts = [(m.type, m.text) for m in x_call.messages]
        assert texts[1][0] == "human" and summary_text(Y) in texts[1][1]
        assert texts[2:-2] == [(m.type, m.text) for m in kept]  # the kept messages follow the summary unchanged
        assert texts[-2] == ("ai", f"hello from {Y}") and texts[-1][0] == "human"
        assert len(texts) == 1 + 1 + KEEP + 1 + 1  # system, summary, kept 20 (new question incl.), answer, next question
        # Same conversation, one thread, consecutive turn indexes, a model recorded per turn.
        rows = turn_rows(db, history.cid)
        assert [r.turn_index for r in rows] == list(range(1, 16))
        assert [r.ai_service_id for r in rows][-3:] == [Y, Y, X]
        agent_id, session_id = conversation_ids(db, history.cid)
        assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{session_id}"}


class TestSummarizationTrigger:
    """The default trigger of ``factory.default_trigger_tokens`` as seen through the real chain (no factory patching)."""

    @pytest.mark.parametrize("window,expected,chars", [
        (3000, 2550, 100),              # 85% of the model's input window
        (BIG_WINDOW, 150_000, 30_000),  # capped at 150k tokens (85% would be 850k)
        (None, 32_000, 6_000),          # model without a profile
    ], ids=["85-percent", "cap-150k", "no-profile-32k"])
    def test_threshold_follows_the_current_turns_profile(self, client, world, sim, window, expected, chars):
        sim.reasoning = False
        X = sim.ids["OpenAI"]
        Y = sim.ids["Google"]
        history = History(client, world, sim)
        grow(history, X, 12, chars)
        sim.windows[Y] = window
        # n == threshold - 1: no summary; the very next turn is above the threshold: summary by Y.
        below = history.human_with_tokens(Y, expected - 1)
        out = history.turn(Y, 0, text=below)
        assert out.ok, out.error
        assert not sim.summary_calls(), f"{expected - 1} tokens must not trigger a trigger of {expected}"
        above = history.human_with_tokens(Y, history.tokens_if(Y, "Q") + 40)
        before = len(sim.calls)
        out = history.turn(Y, 0, text=above)
        assert out.ok, out.error
        assert [(c.service_id, c.is_summary) for c in sim.calls[before:]] == [(Y, True), (Y, False)]

    def test_n_equal_to_the_threshold_triggers(self, client, world, sim):
        sim.reasoning = False
        X, Y = sim.ids["Anthropic"], sim.ids["MistralAI"]
        history = History(client, world, sim)
        grow(history, X, 12, 100)
        sim.windows[Y] = 3000
        exact = history.human_with_tokens(Y, 2550)
        before = len(sim.calls)
        out = history.turn(Y, 0, text=exact)
        assert out.ok, out.error
        assert [(c.service_id, c.is_summary) for c in sim.calls[before:]] == [(Y, True), (Y, False)]




# 4: history bigger than the new model's window


def grow_mixed(history: History, service_id: int, big_turns: int, small_turns: int, big_chars: int, small_chars: int):
    history.sim.windows[service_id] = BIG_WINDOW
    for i in range(big_turns + small_turns):
        out = history.turn(service_id, big_chars if i < big_turns else small_chars)
        assert out.ok, out.error


class TestASmallerContextWindow:
    """Switching to a model whose window is smaller than the stored history.

    The summarization is built with the TURN's model, so its trigger (85% of that model's window) fires BEFORE the first
    model call; the summary is written by the small model from the older history, which is bounded by that model's
    limits (``summary_input_bound``), then the model receives summary + the last 20 messages. What still cannot be
    avoided: the 20 kept messages alone not fitting (``keep`` is a message count, not a token budget).
    """

    def _setup(self, client, world, sim, big_turns, small_turns, big_chars, small_chars):
        sim.reasoning = False
        A, B = sim.ids["Google"], sim.ids["OpenAI"]
        history = History(client, world, sim)
        grow_mixed(history, A, big_turns, small_turns, big_chars, small_chars)
        sim.enforce_window.add(B)
        return A, B, history

    def test_summarization_runs_before_the_small_model_is_called_and_brings_the_input_under_its_window(
        self, client, db, world, sim
    ):
        # Older part small, last 20 messages the bulk: total above B's window, summary prompt and summarized input below.
        A, B, history = self._setup(client, world, sim, 2, 12, 100, 700)
        text = question(50, 700)
        total = history.tokens_if(B, text)
        kept_tokens = history.counter(B)(history.state()[-(KEEP - 1):] + [HumanMessage(text)])
        window = (total + kept_tokens) // 2 + 150
        assert kept_tokens + 400 < window < total, (kept_tokens, window, total)
        sim.windows[B] = window
        before = len(sim.calls)
        out = history.turn(B, 0, text=text)
        assert out.ok, out.error
        calls = sim.calls[before:]
        assert [(c.service_id, c.is_summary) for c in calls] == [(B, True), (B, False)]
        assert all(c.tokens <= window for c in calls), [c.tokens for c in calls]
        assert calls[0].tokens < total, "the summary call is the first thing the small model sees: it is not the full history"
        assert not sim.rejections
        assert [r.turn_index for r in turn_rows(db, history.cid)] == list(range(1, 16))

    def test_a_turn_without_summarization_trigger_is_unaffected_by_a_window_that_fits(self, client, world, sim):
        A, B, history = self._setup(client, world, sim, 2, 12, 100, 100)
        text = question(50, 100)
        sim.windows[B] = history.tokens_if(B, text) * 3
        out = history.turn(B, 0, text=text)
        assert out.ok and not sim.summary_calls() and not sim.rejections

    def _older_history_is_the_bulk(self, client, world, sim):
        A, B, history = self._setup(client, world, sim, 6, 8, 3000, 40)  # 14 turns: older 9 messages hold the big ones
        text = question(50, 40)
        sim.windows[B] = 2000
        assert history.tokens_if(B, text) > 2000
        return A, B, history, text

    def test_the_turn_survives_an_older_history_larger_than_the_window(self, client, db, world, sim):
        """The summary input is bounded by the summary model's window THRESHOLD (window - min(2000, window // 2)) and a
        lower TARGET (0.8 * window - overhead): asserted on the recorded summary call tokens. A single stored message
        (~750 tokens) is bigger than the 600-token target, so the product falls back to the threshold (1000)."""
        from langchain.agents.middleware.summarization import DEFAULT_SUMMARY_PROMPT
        from langchain_core.messages.utils import count_tokens_approximately
        from tools.middleware.factory import summary_trim_limits

        A, B, history, text = self._older_history_is_the_bulk(client, world, sim)
        threshold, target = summary_trim_limits(SimChatModel(B, "OpenAI", sim, profile={"max_input_tokens": 2000}), None, True)
        assert (threshold, target) == (1000, 600)
        full_older = history.counter(B)(history.state()[:-(KEEP - 1)])
        assert full_older > threshold
        out = history.turn(B, 0, text=text)
        assert out.ok, out.error
        (summary_call,) = sim.summary_calls(B)
        prompt_overhead = count_tokens_approximately([HumanMessage(DEFAULT_SUMMARY_PROMPT.format(messages=""))])
        history_tokens = summary_call.tokens - prompt_overhead  # what of the older history the summary call carries
        assert history_tokens <= threshold, (history_tokens, threshold, target)
        assert history_tokens < full_older, "the older history was trimmed before it went to the summary call"
        assert summary_call.tokens <= 2000, "and the whole call fits B's window"
        assert all(c.tokens <= 2000 for c in sim.of(B)) and not sim.rejections
        assert [r.turn_index for r in turn_rows(db, history.cid)] == list(range(1, 16))

    def test_when_the_kept_messages_alone_exceed_the_window_the_failure_is_contained(self, client, db, test_engine, world, sim):
        """Unavoidable: ``keep`` is 20 messages; if those do not fit, the main call overflows. Contained."""
        A, B, history = self._setup(client, world, sim, 0, 14, 0, 3000)
        text = question(50, 40)
        sim.windows[B] = 2000
        before = checkpoint_messages(test_engine, db, history.cid)
        out = history.turn(B, 0, text=text)
        assert not out.ok and ERROR_TEXT in out.error + out.body
        assert sim.rejections and sim.rejections[-1][0] == B and "context_length_exceeded" in sim.rejections[-1][1]
        assert not sim.calls[-1].is_summary, "the summary fitted; the main call (summary + kept messages) did not"
        assert busy_marker(db, history.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, history.cid)] == list(range(1, 15))
        after = checkpoint_messages(test_engine, db, history.cid)
        # Precisely: the summary call fitted and its state update persisted; the failed main call added nothing.
        assert len(after) == 1 + (KEEP - 1) + 1
        assert after[0].type == "human" and after[0].additional_kwargs.get("lc_source") == "summarization"
        assert summary_text(B) in after[0].text
        assert after[1:-1] == before[-(KEEP - 1):], "the 19 kept messages, unchanged"
        assert after[-1].type == "human" and after[-1].text == text and not any(m.type == "ai" and m.text == f"hello from {B}" for m in after)
        sim.windows[B] = BIG_WINDOW  # back on a model whose window holds the history: the conversation is intact
        again = history.turn(B, 0, text=text)
        assert again.ok, again.error


# ------------------------------------------------------------------ 5: capability differences


class TestCapabilityDifferences:
    """What the product knows about a model's capabilities: nothing. ``AIService`` has ``supports_video`` only (no
    vision / tool-support flag) and the Chat never filters the history or the tools by capability, so a switch to a model
    that lacks one sends the history (image blocks) and tools as they are and the provider decides."""

    def _image_turn(self, client, world, sim, a, stream=False):
        sim.reasoning = False
        return go(client, world, "describe this", selection(sim.ids[a]), files=[("files", ("pic.png", PNG, "image/png"))],
                  stream=stream)

    @pytest.mark.parametrize("b", PROVIDERS)
    def test_an_inline_image_in_the_history_is_valid_input_for_every_provider_converter(self, client, world, sim, b):
        first = self._image_turn(client, world, sim, "OpenAI")
        assert first.ok, first.error
        assert any(has_image_block(m) for m in sim.main_calls(sim.ids["OpenAI"])[0].messages)
        second = go(client, world, "and now?", selection(sim.ids[b]), first.cid)
        assert second.ok, second.error
        received = sim.main_calls(sim.ids[b])[0].messages
        assert any(has_image_block(m) for m in received), "the history is sent as stored: the image block is still there"

    def test_a_turn_with_an_explicit_empty_file_references_does_not_carry_the_image(self, client, world, sim):
        """``file_references="[]"`` is expressible (JSON array form field): no stored file is re-attached. Without the
        field every file of the conversation is attached again (``resolve_chat_files``)."""
        first = self._image_turn(client, world, sim, "OpenAI")
        assert first.ok, first.error
        A = sim.ids["OpenAI"]
        calls = len(sim.calls)
        second = go(client, world, "no image please", selection(A), first.cid, extra_form={"file_references": "[]"})
        assert second.ok, second.error
        last_human = [m for m in sim.calls[calls].messages if m.type == "human"][-1]
        assert not has_image_block(last_human) and last_human.text == "no image please"
        third = go(client, world, "image again", selection(A), first.cid)
        assert third.ok, third.error
        assert has_image_block([m for m in sim.main_calls(A)[-1].messages if m.type == "human"][-1])
        shown = [(m["role"], m["content"]) for m in detail(client, world, first.cid)["messages"] if m["role"] == "user"]
        assert [bool(re.search(r"\[IMAGE:", c)) for _, c in shown] == [True, False, True]

    @pytest.fixture
    def signed_urls(self, monkeypatch):
        """``AICT_BASE_URL`` set: the product sends signed http URLs (``build_human_message``); Google's converter would
        download them, so ``requests.get`` of its image loader is replaced and records the URLs."""
        monkeypatch.setenv("AICT_BASE_URL", "https://aict.invalid")
        fetched = []

        def fake_get(url, *args, **kwargs):
            fetched.append(url)
            return SimpleNamespace(ok=True, content=PNG, raise_for_status=lambda: None)

        monkeypatch.setattr("langchain_google_genai._image_utils.requests.get", fake_get)
        return fetched

    @pytest.mark.parametrize("b", [
        pytest.param(p, marks=pytest.mark.xfail(
            strict=True, raises=ProductFinding, reason=(
                "Finding: with AICT_BASE_URL set the Chat sends a signed http URL as the image block; the Ollama converter "
                "puts any URL into ``images`` (base64 expected), so a Custom/Ollama model rejects the turn. Hand-written sim "
                "rule (Ollama API takes base64). Smallest fix: inline the image as base64 for the Custom provider."))
        ) if p == "Custom" else p for p in PROVIDERS])
    def test_a_signed_url_image_in_the_history(self, client, world, sim, signed_urls, b):
        first = self._image_turn(client, world, sim, "OpenAI")
        assert first.ok, first.error
        url_blocks = [blk for m in sim.main_calls(sim.ids["OpenAI"])[0].messages if has_image_block(m)
                      for blk in m.content if isinstance(blk, dict) and blk.get("type") == "image_url"]
        assert url_blocks and url_blocks[0]["image_url"]["url"].startswith("https://aict.invalid/static/")
        second = go(client, world, "and now?", selection(sim.ids[b]), first.cid)
        raise_finding_if_rejected(second, sim, sim.ids[b], REJECT_OLLAMA_URL)
        assert second.ok, second.error
        received = sim.main_calls(sim.ids[b])[0].messages
        assert any(has_image_block(m) for m in received)
        if b == "Google":  # the converter downloaded the signed URL (and the sim accepted the bytes)
            assert signed_urls and all(u.startswith("https://aict.invalid/static/") for u in signed_urls)

    def test_a_model_without_vision_gets_the_image_unchanged_and_the_failure_is_contained(self, client, db, world, sim):
        first = self._image_turn(client, world, sim, "OpenAI")
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_vision.add(B)
        second = go(client, world, "and now?", selection(B), first.cid)
        assert not second.ok and ERROR_TEXT in second.error + second.body
        assert any(has_image_block(m) for m in sim.of(B)[0].messages), "the product forwarded the image block untouched"
        assert sim.rejections == [(B, REJECT_VISION)]
        assert busy_marker(db, first.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]
        third = go(client, world, "back to a vision model", selection(sim.ids["Anthropic"]), first.cid)
        assert third.ok, third.error

    @pytest.mark.xfail(strict=True, raises=ProductFinding, reason=(
        "Finding (capabilities): the Chat has no notion of vision support (models/ai_service.py has supports_video only), "
        "so switching to a model without vision keeps the image_url blocks of earlier turns in the history and the turn "
        "fails with a generic error. Smallest fix: a before_model middleware that replaces image blocks of earlier "
        "messages by a text placeholder when the turn's AIService is flagged text-only (needs a new AIService flag)."
    ))
    def test_a_model_without_vision_still_answers_a_conversation_with_an_image(self, client, world, sim):
        first = self._image_turn(client, world, sim, "OpenAI")
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_vision.add(B)
        second = go(client, world, "and now?", selection(B), first.cid)
        raise_finding_if_rejected(second, sim, B, REJECT_VISION)

    def test_every_turn_binds_the_base_tool_so_a_model_without_tool_support_fails_even_with_nothing_selected(
        self, client, db, world, sim
    ):
        sim.reasoning = False
        sim.call_tool[sim.ids["OpenAI"]] = sim.retriever
        first = go(client, world, "use the tool", selection(sim.ids["OpenAI"], silo=sim.silo))
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_tools.add(B)  # real Ollama / Azure: bind succeeds, the server answers 4xx when the call carries tools
        second = go(client, world, "plain follow-up", selection(B), first.cid)
        assert not second.ok and ERROR_TEXT in second.error + second.body
        assert sim.bind_attempts[-1] == (B, [BASE_TOOL]), "only the always-on base tool was offered"
        assert sim.rejections == [(B, REJECT_TOOLS)]
        assert busy_marker(db, first.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]

    def test_a_model_without_tool_support_fails_the_turn_when_a_tool_is_selected_and_it_is_contained(
        self, client, db, world, sim
    ):
        sim.reasoning = False
        first = go(client, world, "q", selection(sim.ids["OpenAI"]))
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_tools.add(B)
        second = go(client, world, "with a silo", selection(B, silo=sim.silo), first.cid)
        assert not second.ok and ERROR_TEXT in second.error + second.body
        assert sim.bind_attempts[-1] == (B, [BASE_TOOL, sim.retriever])
        assert sim.rejections == [(B, REJECT_TOOLS)]
        assert busy_marker(db, first.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]

    def test_a_bind_time_refusal_is_contained_too(self, client, db, world, sim):
        """Not what real Ollama/Azure do (they refuse at call time, above); kept for a client that raises in bind_tools."""
        sim.reasoning = False
        first = go(client, world, "q", selection(sim.ids["OpenAI"]))
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_tools_at_bind.add(B)
        second = go(client, world, "next", selection(B), first.cid)
        assert not second.ok and ERROR_TEXT in second.error + second.body
        assert sim.bind_attempts[-1] == (B, [BASE_TOOL]) and not sim.of(B), "refused before any model call"
        assert busy_marker(db, first.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]

    @pytest.mark.xfail(strict=True, raises=ProductFinding, reason=(
        "Finding (capabilities): the product does not know which models support tool calling and binds at least the "
        "always-on download_url_to_workspace tool (backend/tools/agentTools.py 'Base tools') on every turn, so a model "
        "that cannot take tools fails every turn with a generic error instead of answering without tools (or telling "
        "the user). Smallest fix: skip tool binding (and report a turn warning) for services flagged as without tool "
        "support, which needs a new AIService flag."
    ))
    def test_a_model_without_tool_support_answers_without_the_tool(self, client, world, sim):
        sim.reasoning = False
        first = go(client, world, "q", selection(sim.ids["OpenAI"]))
        assert first.ok, first.error
        B = sim.ids["Custom"]
        sim.no_tools.add(B)
        second = go(client, world, "with a silo", selection(B, silo=sim.silo), first.cid)
        raise_finding_if_rejected(second, sim, B, REJECT_TOOLS)


# ------------------------------------------------------------------ 6: a retired model in the middle


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
class TestARetiredModelInTheMiddle:
    @pytest.fixture
    def retired_a(self, client, db, world, sim, stream):
        sim.reasoning = False
        A = sim.ids["Anthropic"]
        sim.call_tool[A] = sim.retriever
        first = go(client, world, "before retirement", selection(A, silo=sim.silo), stream=stream)
        assert first.ok, first.error
        db.query(AIService).filter(AIService.service_id == A).update({"end_of_service_at": past(2)})
        db.commit()
        return A, first

    def test_selecting_another_model_works_and_reads_the_history(self, client, db, world, sim, retired_a, stream):
        A, first = retired_a
        B = sim.ids["OpenAI"]
        second = go(client, world, "after retirement", selection(B, silo=sim.silo), first.cid, stream=stream)
        assert second.ok, second.error
        received = sim.main_calls(B)[0].messages
        assert [m.type for m in received] == ["system", "human", "ai", "tool", "ai", "human"]
        assert received[1].text == "before retirement"
        assert [(r.turn_index, r.ai_service_id) for r in turn_rows(db, first.cid)] == [(1, A), (2, B)]
        assert busy_marker(db, first.cid) == (None, None)

    def test_still_selecting_it_is_409_service_retired_and_nothing_changes(
        self, client, db, world, sim, retired_a, stream, threads
    ):
        A, first = retired_a
        calls = len(sim.calls)
        agent_id, session_id = conversation_ids(db, first.cid)
        rows_before = threads.rows(f"thread_{agent_id}_{session_id}")
        second = go(client, world, "after retirement", selection(A, silo=sim.silo), first.cid, stream=stream)
        assert not second.ok and second.status == 409
        assert json.loads(second.body)["error_code"] == "SERVICE_RETIRED"
        assert len(sim.calls) == calls, "no model was called"
        assert busy_marker(db, first.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]
        assert stored_selection_service(db, first.cid) == A
        assert threads.rows(f"thread_{agent_id}_{session_id}") == rows_before
        assert [(m["role"], m["content"]) for m in detail(client, world, first.cid)["messages"]] == [
            ("user", "before retirement"), ("agent", f"hello from {A}")]
        # The conversation is usable again as soon as another model is picked.
        third = go(client, world, "recovered", selection(sim.ids["Google"]), first.cid, stream=stream)
        assert third.ok, third.error
        assert third.turn["turn_index"] == 2


# ------------------------------------------------------------------ 8: back and forth across providers

# Chosen so that every sequence walks through pairs that the converters used to reject before the history normalisation
# (OpenAI->Custom, Anthropic->Azure, Google->Custom, OpenAI->Google, OpenAI->Azure, Custom->OpenAI ...): nothing is avoided.
SEQUENCES = {
    "plain": (False, "today", ["OpenAI", "Custom", "Anthropic", "Azure", "Google", "Custom", "OpenAI", "Azure", "Anthropic"]),
    "reasoning-today": (True, "today", ["OpenAI", "Google", "Custom", "OpenAI", "Azure", "Google", "OpenAI", "MistralAI", "Google"]),
    "thinking-not-produced-today": (
        True, "full", ["Anthropic", "Custom", "Google", "Azure", "Anthropic", "OpenAI", "Google", "Custom", "Anthropic"]),
}


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
@pytest.mark.parametrize("variant", sorted(SEQUENCES))
def test_one_conversation_switched_back_and_forth_keeps_one_coherent_thread(
    client, db, world, sim, threads, variant, stream
):
    reasoning, shape, order = SEQUENCES[variant]
    sim.reasoning, sim.shape = reasoning, shape
    cid = None
    questions = []
    spans = []  # (first call index, end call index) of every turn
    for i, provider in enumerate(order):
        service_id = sim.ids[provider]
        if i % 2 == 0:  # every other turn calls the retriever tool on that turn's model
            sim.call_tool[service_id] = sim.retriever
        else:
            sim.call_tool.pop(service_id, None)
        questions.append(f"question {i} to {provider}")
        start = len(sim.calls)
        out = go(client, world, questions[-1], selection(service_id, silo=sim.silo), cid, stream=stream)
        assert out.ok, (i, provider, out.error)
        spans.append((start, len(sim.calls)))
        cid = out.cid
        assert out.turn["turn_index"] == i + 1 and out.turn["ai_service_id"] == service_id

    rows = turn_rows(db, cid)
    assert [(r.turn_index, r.ai_service_id) for r in rows] == [(i + 1, sim.ids[p]) for i, p in enumerate(order)]
    assert [r.ai_model_name for r in rows] == [MODEL_NAMES[p] for p in order]
    agent_id, session_id = conversation_ids(db, cid)
    assert threads.of_agent(agent_id) == {f"thread_{agent_id}_{session_id}"}
    # EVERY model call of every turn saw exactly the questions and answers asked so far, in order, with paired tool calls.
    for i, (start, end) in enumerate(spans):
        turn_calls = sim.calls[start:end]
        assert turn_calls and not any(c.is_summary for c in turn_calls)
        assert all(c.service_id == sim.ids[order[i]] for c in turn_calls)
        for call in turn_calls:
            assert [m.text for m in call.messages if m.type == "human"] == questions[:i + 1], (i, call.service_id)
            assert [m.text for m in call.messages if m.type == "ai" and m.text] == [
                f"hello from {sim.ids[p]}" for p in order[:i]], (i, call.service_id)
            check_tool_pairing(call.messages)
    messages = detail(client, world, cid)["messages"]
    assert [m["content"] for m in messages if m["role"] == "user"] == questions
    assert [m["turn"]["ai_service_id"] for m in messages if m["role"] == "agent"] == [sim.ids[p] for p in order]
    assert busy_marker(db, cid) == (None, None)
    assert not sim.rejections


# ------------------------------------------------------------------ failure paths


class TestFailurePaths:
    def test_a_failure_mid_stream_after_tokens_leaves_no_partial_answer(self, client, db, test_engine, world, sim):
        sim.reasoning = False
        A, B = sim.ids["Anthropic"], sim.ids["OpenAI"]
        first = go(client, world, "turn one question", selection(A), stream=True)
        assert first.ok, first.error
        before = checkpoint_messages(test_engine, db, first.cid)
        sim.fail_after_chunks[B] = 2  # "hello", " from" are streamed, then the stream breaks
        second = go(client, world, "turn two question", selection(B), first.cid, stream=True)
        assert not second.ok
        kinds = [e["type"] for e in second.events]
        assert "token" in kinds and "error" in kinds and "done" not in kinds
        assert kinds.index("token") < kinds.index("error"), "the error event comes after the tokens"
        assert second.tokens == "hello from"
        assert ERROR_TEXT in second.error and "injected provider error" not in second.error + second.body
        assert [(sid, r.split(":")[0]) for sid, r in sim.rejections] == [(B, "ConnectionError")]
        after = checkpoint_messages(test_engine, db, first.cid)
        assert after[:len(before)] == before
        assert [m.type for m in after[len(before):]] == ["human"], "only the question; no partial AIMessage"
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1]
        assert busy_marker(db, first.cid) == (None, None)
        sim.fail_after_chunks.clear()
        third = go(client, world, "turn three question", selection(A), first.cid, stream=True)
        assert third.ok, third.error
        seen = [m.text for m in sim.main_calls(A)[-1].messages if m.type == "ai"]
        assert seen == [f"hello from {A}"], "the partial text of the broken stream is not in the next turn's history"
        assert third.turn["turn_index"] == 2

    @pytest.mark.parametrize("b_provider", ["Anthropic", "Google", "OpenAI"])
    def test_a_switch_while_a_tool_call_is_unanswered_in_the_checkpoint(
        self, client, db, test_engine, world, sim, b_provider
    ):
        """The unanswered call is written through the checkpointer (a failing tool does not leave one: the first attempt
        of this test used a raising tool, and the failed first turn leaves no Conversation row at all)."""
        sim.reasoning = False
        A, B = sim.ids["OpenAI"], sim.ids[b_provider]
        first = go(client, world, "turn one question", selection(A))
        assert first.ok, first.error
        injected = inject_unanswered_tool_call(test_engine, db, first.cid, sim.retriever)
        before = checkpoint_messages(test_engine, db, first.cid)
        # Precondition: the checkpoint really holds an AIMessage tool call without a ToolMessage.
        assert [m.type for m in before] == ["human", "ai", "human", "ai"], [m.type for m in before]
        assert before[-1].tool_calls and before[-1].tool_calls[0]["id"] == injected
        assert not [m for m in before if isinstance(m, ToolMessage)]
        calls_before = len(sim.calls)  # B may be the very service of turn 1
        second = go(client, world, "next question", selection(B), first.cid)
        assert second.ok, second.error  # the normaliser's synthetic ToolMessage makes the history valid
        received = sim.calls[calls_before].messages
        assert sim.calls[calls_before].service_id == B
        check_tool_pairing(received)
        tool_messages = [m for m in received if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1 and tool_messages[0].content == INTERRUPTED_TOOL_TEXT
        assert tool_messages[0].tool_call_id == injected and tool_messages[0].status == "error"
        assert [m.type for m in received] == ["system", "human", "ai", "human", "ai", "tool", "human"]
        assert not sim.rejections
        after = checkpoint_messages(test_engine, db, first.cid)
        assert after[:4] == before, "the checkpoint is not rewritten"
        assert not [m for m in after if isinstance(m, ToolMessage)], "the synthetic ToolMessage lives in the call view only"
        assert [r.turn_index for r in turn_rows(db, first.cid)] == [1, 2]

    def _armed(self, client, world, sim):
        sim.reasoning = False
        X, Y = sim.ids["OpenAI"], sim.ids["Anthropic"]
        history = History(client, world, sim)
        grow(history, X, 12)
        text = question(12, 800)
        sim.windows[Y] = window_for(history.tokens_if(Y, text))  # the very next turn on Y summarizes
        return X, Y, history, text

    @pytest.mark.parametrize("status,expectation", [
        (None, "at-least-once"), (400, "exactly-once"), (429, "retried"),
    ], ids=["no-status", "status-400", "status-429"])
    def test_a_failing_summary_call_is_contained(self, client, db, test_engine, world, sim, status, expectation):
        """Attempts: an error without a status is retried (library ``with_retry``); a 4xx other than 408/429 is attempted
        ONCE and 429 is retried (``_TransientOnlyRetry`` in backend/tools/middleware/factory.py: product behaviour)."""
        X, Y, history, text = self._armed(client, world, sim)
        before = checkpoint_messages(test_engine, db, history.cid)
        sim.fail_summary.add(Y)
        if status:
            sim.summary_status[Y] = status
        out = history.turn(Y, 0, text=text)
        assert not out.ok and ERROR_TEXT in out.error + out.body
        attempts = len(sim.summary_calls(Y))
        assert attempts >= 1 and sim.calls[-1].is_summary and not sim.main_calls(Y), "no main model call happened"
        assert sim.rejections == [(Y, REJECT_SUMMARY)] * attempts, "every rejection is the summary rejection"
        if expectation == "exactly-once":
            assert attempts == 1
        elif expectation == "retried":
            assert attempts > 1
        after = checkpoint_messages(test_engine, db, history.cid)
        assert after[:len(before)] == before and [m.type for m in after[len(before):]] == ["human"]
        assert busy_marker(db, history.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, history.cid)] == list(range(1, 13))
        sim.fail_summary.clear()
        again = history.turn(Y, 0, text=question(13, 800))
        assert again.ok, again.error

    def test_a_summary_that_succeeds_before_a_failing_main_call_persists_only_as_the_checkpoint_shows(
        self, client, db, test_engine, world, sim
    ):
        """LangGraph writes the summarization's state update (summary + removal of the old messages) as its own step, so it
        survives the failure of the model call that follows; the turn row and answer do not exist."""
        X, Y, history, text = self._armed(client, world, sim)
        sim.fail_main.add(Y)
        out = history.turn(Y, 0, text=text)
        assert not out.ok and ERROR_TEXT in out.error + out.body
        assert [(c.service_id, c.is_summary) for c in sim.calls[-2:]] == [(Y, True), (Y, False)]
        assert sim.rejections == [(Y, REJECT_MAIN)]
        after = checkpoint_messages(test_engine, db, history.cid)
        assert after[0].type == "human" and after[0].additional_kwargs.get("lc_source") == "summarization"
        assert summary_text(Y) in after[0].text
        assert len(after) == 1 + (KEEP - 1) + 1  # summary, the 19 kept messages before the question, the question
        assert after[-1].text == text and not [m for m in after if m.type == "ai" and m.text == f"hello from {Y}"]
        assert busy_marker(db, history.cid) == (None, None)
        assert [r.turn_index for r in turn_rows(db, history.cid)] == list(range(1, 13))
        sim.fail_main.clear()
        again = history.turn(Y, 0, text=question(14, 800))
        assert again.ok, again.error


# ------------------------------------------------------------------ the stamp: same provider, other service


@pytest.mark.parametrize("stream", [False, True], ids=["messages", "stream"])
class TestTheStampOfTheServiceThatWroteAMessage:
    """Chat AIMessages are stamped with ``response_metadata["aict_service_id"]`` / ``["aict_model"]``; a message reaches the
    model untouched only if its wire family AND its stamp are the turn's. Another service of the SAME provider (another
    key / model / endpoint) gets the normalised text, so the reasoning item ids (OpenAI ``rs_``/``msg_``) and signatures
    that belong to the first service are never replayed to the second."""

    @pytest.mark.parametrize("provider", PROVIDERS)
    def test_checkpointed_chat_messages_carry_the_stamp(self, client, db, test_engine, world, sim, provider, stream):
        sim.reasoning, sim.shape = True, "today"
        A = sim.ids[provider]
        sim.call_tool[A] = sim.retriever
        out = go(client, world, "q", selection(A, silo=sim.silo), stream=stream)
        assert out.ok, out.error
        ai = [m for m in checkpoint_messages(test_engine, db, out.cid) if m.type == "ai"]
        assert len(ai) == 2  # tool call, answer
        for message in ai:
            assert message.response_metadata["aict_service_id"] == A
            assert message.response_metadata["aict_model"] == MODEL_NAMES[provider]

    @pytest.mark.parametrize("provider", ["OpenAI", "Google"])
    def test_another_service_of_the_same_provider_gets_normalised_text_and_the_first_gets_its_own_back(
        self, client, db, test_engine, world, sim, provider, stream
    ):
        import base64

        configure_factories(db)
        second_service = AIServiceFactory(
            app=db.get(App, world["app_id"]), provider=provider, name=f"{provider}-svc-2",
            description=MODEL_NAMES[provider],
        )
        db.flush()
        S1, S2 = sim.ids[provider], second_service.service_id
        sim.provider_of[S2] = provider
        db.commit()
        sim.reasoning, sim.shape = True, "today"
        sim.call_tool[S1] = sim.retriever
        first = go(client, world, "turn one question", selection(S1, silo=sim.silo), stream=stream)
        assert first.ok, first.error
        before = checkpoint_messages(test_engine, db, first.cid)
        assert [m.type for m in before] == ["human", "ai", "tool", "ai"]
        assert has_reasoning_marker(before[1], provider, "today"), "the history carries the provider's reasoning artefact"
        assert all(m.response_metadata["aict_service_id"] == S1 for m in before if m.type == "ai")

        sim.call_tool.pop(S1)
        calls_before = len(sim.calls)
        second = go(client, world, "turn two question", selection(S2, silo=sim.silo), first.cid, stream=stream)
        assert second.ok, second.error
        received = sim.calls[calls_before].messages
        assert sim.calls[calls_before].service_id == S2
        assert [m.type for m in received] == ["system", "human", "ai", "tool", "ai", "human"]
        assert_normalised(received[2], before[1])
        assert_normalised(received[4], before[3])
        check_tool_pairing(received)
        assert received[3].tool_call_id == received[2].tool_calls[0]["id"] == before[1].tool_calls[0]["id"]
        for message in received[2:5]:
            assert isinstance(message.content, str)
            # usage_metadata keeps a harmless reasoning TOKEN count; what is sent is content / kwargs / metadata
            text = repr((message.content, message.additional_kwargs, message.response_metadata))
            assert "reasoning" not in text and "rs_" not in text and "msg_" not in text and "signature" not in text
            assert base64.b64encode(bytes(range(64))).decode() not in text
        after = checkpoint_messages(test_engine, db, first.cid)
        assert after[:4] == before, "the checkpoint keeps the originals and their stamps"
        assert after[5].response_metadata["aict_service_id"] == S2

        # Back on service 1 (twice in a row): its own original messages, untouched; same service = identity.
        for question_text in ("turn three question", "turn four question"):
            calls_before = len(sim.calls)
            out = go(client, world, question_text, selection(S1, silo=sim.silo), first.cid, stream=stream)
            assert out.ok, out.error
            assert sim.calls[calls_before].service_id == S1
            assert sim.calls[calls_before].messages[1:5] == before
        assert not sim.rejections
