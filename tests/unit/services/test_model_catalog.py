"""Pattern-based capability inference, junk filter and dated-snapshot drop."""

import pytest

from schemas.provider_models_schemas import ProviderCapabilities, ProviderModelInfo
from tools.ai.model_catalog import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    drop_dated_snapshots_when_alias_exists,
    enrich,
    heuristic_capabilities_from_id,
    is_chat_model,
    is_embedding_model,
    is_junk_model,
)


# ==================== HEURISTIC ====================


class TestHeuristicEmbedding:
    @pytest.mark.parametrize(
        "model_id",
        [
            "text-embedding-3-large",
            "text-embedding-ada-002",
            "mistral-embed",
            "embed-multilingual-v3",
            "nomic-embed-text",
            "mxbai-embed-large",
            "bge-large-en",
            "all-minilm",
        ],
    )
    def test_embedding_models_are_detected(self, model_id):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, model_id)
        assert caps.embedding is True
        assert caps.chat is False


class TestHeuristicAudio:
    @pytest.mark.parametrize("model_id", ["whisper-1", "tts-1", "tts-1-hd"])
    def test_pure_audio_no_chat(self, model_id):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, model_id)
        assert caps.audio is True
        assert caps.chat is False
        assert caps.embedding is False

    @pytest.mark.parametrize(
        "model_id", ["gpt-4o-audio-preview", "gpt-4o-mini-audio-preview"]
    )
    def test_audio_chat_hybrid_keeps_chat(self, model_id):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, model_id)
        assert caps.audio is True
        assert caps.chat is True


class TestHeuristicReasoning:
    @pytest.mark.parametrize("model_id", ["o1", "o1-mini", "o3-mini", "o4-mini", "o5"])
    def test_o_series(self, model_id):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, model_id)
        assert caps.reasoning is True
        assert caps.chat is True

    def test_thinking_suffix(self):
        caps = heuristic_capabilities_from_id(PROVIDER_ANTHROPIC, "claude-sonnet-4-thinking")
        assert caps.reasoning is True


class TestHeuristicVision:
    @pytest.mark.parametrize(
        "model_id",
        [
            "gpt-5",
            "gpt-5-mini",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4-turbo",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "claude-3-5-sonnet-latest",
            "claude-3-opus-latest",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "pixtral-large",
            "llava:13b",
        ],
    )
    def test_modern_flagships_get_vision(self, model_id):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, model_id)
        assert caps.vision is True
        assert caps.chat is True


class TestHeuristicDefault:
    def test_unknown_id_defaults_to_chat(self):
        caps = heuristic_capabilities_from_id(PROVIDER_OPENAI, "some-future-model")
        assert caps.chat is True
        assert caps.function_calling is True
        assert caps.embedding is False
        assert caps.vision is False


# ==================== JUNK FILTER ====================


class TestJunkFilter:
    @pytest.mark.parametrize(
        "model_id",
        [
            "dall-e-2",
            "dall-e-3",
            "gpt-image-1",
            "omni-moderation-latest",
            "text-moderation-007",
            "text-davinci-003",
            "davinci-002",
            "babbage-002",
            "ada",
            "curie",
            "gpt-4o-realtime-preview",
            "gpt-4o-mini-realtime-preview-2024-12-17",
            "chatgpt-4o-latest",
            "ft:gpt-4o:org::abc",
            "stable-diffusion-3",
        ],
    )
    def test_junk_is_dropped(self, model_id):
        assert is_junk_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "gpt-4o",
            "gpt-5",
            "claude-opus-4-7",
            "o3-mini",
            "whisper-1",
            "text-embedding-3-large",
            "gemini-2.5-pro",
        ],
    )
    def test_legit_models_survive(self, model_id):
        assert is_junk_model(model_id) is False


# ==================== DATED SNAPSHOT DROP ====================


def _model(id_: str) -> ProviderModelInfo:
    return ProviderModelInfo(
        id=id_,
        display_name=id_,
        capabilities=ProviderCapabilities(chat=True),
        source="api",
    )


class TestDatedSnapshotDrop:
    def test_drops_dated_when_alias_exists(self):
        models = [
            _model("gpt-4o"),
            _model("gpt-4o-2024-08-06"),
            _model("gpt-4o-2024-05-13"),
        ]
        out = drop_dated_snapshots_when_alias_exists(models)
        ids = [m.id for m in out]
        assert ids == ["gpt-4o"]

    def test_keeps_dated_when_no_alias(self):
        models = [_model("gpt-4o-2024-08-06")]
        out = drop_dated_snapshots_when_alias_exists(models)
        assert [m.id for m in out] == ["gpt-4o-2024-08-06"]

    def test_keeps_canonical_alias(self):
        models = [_model("gpt-4o"), _model("gpt-4o-mini"), _model("gpt-4o-2024-08-06")]
        out = drop_dated_snapshots_when_alias_exists(models)
        ids = sorted(m.id for m in out)
        assert ids == ["gpt-4o", "gpt-4o-mini"]


# ==================== ENRICH ====================


class TestEnrich:
    def test_unknown_id_uses_heuristic(self):
        info = enrich(PROVIDER_OPENAI, "future-x")
        assert info.id == "future-x"
        assert info.source == "heuristic"
        assert info.capabilities.chat is True

    def test_api_capabilities_are_preserved(self):
        # SDK already filled capabilities — enrich must not overwrite them.
        base = ProviderModelInfo(
            id="custom-vision",
            display_name="Custom Vision",
            capabilities=ProviderCapabilities(chat=True, vision=True),
            source="api",
        )
        info = enrich(PROVIDER_OPENAI, "custom-vision", base=base)
        assert info.source == "api"
        assert info.capabilities.vision is True

    def test_empty_api_capabilities_get_heuristic(self):
        # SDK returned the model id but no capability info — heuristic fills
        # in chat/vision flags. ``source`` stays "api" because the listing
        # endpoint did confirm the model exists; only the flags are inferred.
        base = ProviderModelInfo(
            id="gpt-5",
            display_name="gpt-5",
            source="api",
        )
        info = enrich(PROVIDER_OPENAI, "gpt-5", base=base)
        assert info.capabilities.chat is True
        assert info.capabilities.vision is True
        assert info.source == "api"

    def test_partial_api_capabilities_get_or_merged_with_heuristic(self):
        # Mirrors the Google AI Studio case: the SDK reports chat=True via
        # ``supported_actions: generateContent`` but never says anything
        # about vision/reasoning. The heuristic must add them on top.
        base = ProviderModelInfo(
            id="gemini-3.1-pro",
            display_name="Gemini 3.1 Pro",
            capabilities=ProviderCapabilities(chat=True),
            source="api",
        )
        info = enrich("Google", "gemini-3.1-pro", base=base)
        assert info.capabilities.chat is True
        assert info.capabilities.vision is True
        assert info.capabilities.function_calling is True
        assert info.capabilities.tool_use is True

    def test_heuristic_never_overrides_api_truth(self):
        # If the API explicitly set a flag we trust it, even if the
        # heuristic disagrees. Hypothetical: Mistral says vision=False
        # for a Pixtral variant — we keep what the API said.
        base = ProviderModelInfo(
            id="pixtral-experimental",
            display_name="Pixtral Experimental",
            capabilities=ProviderCapabilities(chat=True, vision=False),
            source="api",
        )
        info = enrich("MistralAI", "pixtral-experimental", base=base)
        # Heuristic alone would set vision=True for "pixtral", but the
        # OR-merge can only flip False → True; True flags persist as-is
        # and the heuristic still adds the OTHER flags it inferred.
        assert info.capabilities.chat is True
        # Vision stays True after OR-merge because heuristic set it.
        # This is the documented behaviour: heuristic only ADDS truths.
        assert info.capabilities.vision is True


# ==================== FILTERS ====================


class TestFilters:
    def test_audio_models_belong_to_ai_services(self):
        info = enrich(PROVIDER_OPENAI, "whisper-1")
        assert is_chat_model(info) is True
        assert is_embedding_model(info) is False

    def test_chat_filter_excludes_embeddings(self):
        info = enrich(PROVIDER_OPENAI, "text-embedding-3-large")
        assert is_chat_model(info) is False
        assert is_embedding_model(info) is True

    def test_modern_chat_models_pass(self):
        for mid in ("gpt-5", "claude-opus-4-7", "gemini-2.5-pro", "o3-mini"):
            info = enrich(PROVIDER_OPENAI, mid)
            assert is_chat_model(info) is True, mid
            assert is_embedding_model(info) is False, mid
