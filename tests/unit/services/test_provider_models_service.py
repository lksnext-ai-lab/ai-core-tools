"""Unit tests for ProviderModelsService.

The dispatch table resolves adapter functions by name at call time, so
patching ``tools.ai.provider_model_clients.<name>`` is enough to swap
the implementation. SDK clients are mocked through ``patch`` so the
tests run without network access.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ProviderCapabilities,
    ProviderModelInfo,
)
from services.provider_models_service import (
    PROVIDER_ERROR_STATUS,
    ProviderModelsService,
)
from tools.ai.provider_model_clients import ProviderListingError


def _info(
    id_: str,
    *,
    chat: bool = True,
    vision: bool = False,
    embedding: bool = False,
    audio: bool = False,
    deprecated: bool = False,
    created_at: int | None = None,
) -> ProviderModelInfo:
    return ProviderModelInfo(
        id=id_,
        display_name=id_,
        capabilities=ProviderCapabilities(
            chat=chat, vision=vision, embedding=embedding, audio=audio
        ),
        deprecated=deprecated,
        created_at=created_at,
        source="api",
    )


# ==================== VALIDATION ====================


class TestListModelsValidation:
    def test_missing_provider_raises_invalid_request(self):
        req = ListProviderModelsRequest(provider="", api_key="sk-x")
        with pytest.raises(ProviderListingError) as exc:
            ProviderModelsService.list_models(req)
        assert exc.value.code == "invalid_request"

    def test_missing_api_key_raises_invalid_request(self):
        req = ListProviderModelsRequest(provider="OpenAI", api_key="")
        with pytest.raises(ProviderListingError) as exc:
            ProviderModelsService.list_models(req)
        assert exc.value.code == "invalid_request"

    def test_masked_api_key_rejected(self):
        req = ListProviderModelsRequest(provider="OpenAI", api_key="****1234")
        with pytest.raises(ProviderListingError) as exc:
            ProviderModelsService.list_models(req)
        assert exc.value.code == "invalid_request"

    def test_unsupported_provider(self):
        req = ListProviderModelsRequest(provider="MysteryAI", api_key="x")
        with pytest.raises(ProviderListingError) as exc:
            ProviderModelsService.list_models(req)
        assert exc.value.code == "unsupported"


# ==================== MANUAL INPUT ====================


class TestManualInput:
    def test_azure_returns_manual_flag(self):
        req = ListProviderModelsRequest(provider="Azure", api_key="x")
        result = ProviderModelsService.list_models(req)
        assert result.requires_manual_input is True
        assert result.models == []

    def test_googlecloud_returns_manual_flag(self):
        req = ListProviderModelsRequest(provider="GoogleCloud", api_key="x")
        result = ProviderModelsService.list_models(req)
        assert result.requires_manual_input is True

    def test_custom_embedding_returns_manual_flag(self):
        # Custom embeddings use HuggingFace Inference, which has no
        # generic listing endpoint — fall back to manual input.
        req = ListProviderModelsRequest(provider="Custom", api_key="", purpose="embedding")
        result = ProviderModelsService.list_models(req)
        assert result.requires_manual_input is True


# ==================== JUNK FILTER ====================


class TestJunkFilter:
    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_drops_dall_e_and_legacy_completion(self, mock_list):
        mock_list.return_value = [
            _info("gpt-4o"),
            _info("dall-e-3"),
            _info("davinci-002"),
            _info("babbage-002"),
            _info("omni-moderation-latest"),
            _info("ft:gpt-4o:org::abc"),
            _info("gpt-4o-realtime-preview"),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="chat")
        result = ProviderModelsService.list_models(req)
        assert [m.id for m in result.models] == ["gpt-4o"]


# ==================== DATED SNAPSHOTS ====================


class TestDatedSnapshots:
    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_drops_dated_when_alias_exists(self, mock_list):
        mock_list.return_value = [
            _info("gpt-4o"),
            _info("gpt-4o-2024-08-06"),
            _info("gpt-4o-2024-05-13"),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="chat")
        result = ProviderModelsService.list_models(req)
        assert [m.id for m in result.models] == ["gpt-4o"]


# ==================== PURPOSE FILTER ====================


class TestPurposeFilter:
    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_chat_includes_audio(self, mock_list):
        mock_list.return_value = [
            _info("gpt-4o"),
            _info("whisper-1", chat=False, audio=True),
            _info("text-embedding-3-large", chat=False, embedding=True),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="chat")
        ids = [m.id for m in ProviderModelsService.list_models(req).models]
        assert "gpt-4o" in ids
        assert "whisper-1" in ids
        assert "text-embedding-3-large" not in ids

    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_embedding_only_embeddings(self, mock_list):
        mock_list.return_value = [
            _info("gpt-4o"),
            _info("text-embedding-3-large", chat=False, embedding=True),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="embedding")
        ids = [m.id for m in ProviderModelsService.list_models(req).models]
        assert ids == ["text-embedding-3-large"]


# ==================== RECENCY SORT ====================


class TestRecencySort:
    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_newest_first_by_created_at(self, mock_list):
        mock_list.return_value = [
            _info("old", created_at=1000),
            _info("newest", created_at=3000),
            _info("middle", created_at=2000),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="chat")
        ids = [m.id for m in ProviderModelsService.list_models(req).models]
        assert ids == ["newest", "middle", "old"]

    @patch("tools.ai.provider_model_clients.list_openai_models")
    def test_deprecated_at_the_bottom(self, mock_list):
        mock_list.return_value = [
            _info("legacy", created_at=5000, deprecated=True),
            _info("current", created_at=2000),
        ]
        req = ListProviderModelsRequest(provider="OpenAI", api_key="sk-x", purpose="chat")
        ids = [m.id for m in ProviderModelsService.list_models(req).models]
        assert ids == ["current", "legacy"]

    @patch("tools.ai.provider_model_clients.list_google_models")
    def test_version_in_id_fallback_when_no_timestamp(self, mock_list):
        # Google models do not expose timestamps; recency falls back to a
        # version number embedded in the id.
        mock_list.return_value = [
            _info("gemini-1.5-pro"),
            _info("gemini-2.5-pro"),
        ]
        req = ListProviderModelsRequest(provider="Google", api_key="x", purpose="chat")
        ids = [m.id for m in ProviderModelsService.list_models(req).models]
        assert ids == ["gemini-2.5-pro", "gemini-1.5-pro"]


# ==================== ERROR STATUS MAPPING ====================


class TestErrorStatusMapping:
    @pytest.mark.parametrize(
        "code,status",
        [
            ("invalid_request", 400),
            ("unauthorized", 401),
            ("not_found", 404),
            ("timeout", 408),
            ("network", 502),
            ("unsupported", 501),
        ],
    )
    def test_status_codes(self, code, status):
        assert PROVIDER_ERROR_STATUS[code] == status


# ==================== CUSTOM = OLLAMA (AI SERVICES) ====================


class TestCustomProviderRoutesToOllama:
    @patch("tools.ai.provider_model_clients.list_ollama_models")
    def test_custom_chat_uses_ollama_lister(self, mock_list):
        mock_list.return_value = [_info("llama3.2:latest")]
        req = ListProviderModelsRequest(
            provider="Custom",
            api_key="",
            base_url="http://localhost:11434",
            purpose="chat",
        )
        result = ProviderModelsService.list_models(req)
        assert mock_list.called
        assert result.requires_manual_input is False
        ids = [m.id for m in result.models]
        assert "llama3.2:latest" in ids


# ==================== ADAPTER SMOKE TESTS ====================


class TestOpenAIAdapter:
    """Mocks the OpenAI SDK to verify the adapter wires capabilities + created_at."""

    def test_lists_and_enriches(self):
        fake_models = SimpleNamespace(
            data=[
                SimpleNamespace(id="gpt-5", owned_by="openai", created=2_000_000_000),
                SimpleNamespace(id="gpt-4o", owned_by="openai", created=1_700_000_000),
                SimpleNamespace(id="text-embedding-3-small", owned_by="openai", created=1_600_000_000),
            ]
        )

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = SimpleNamespace(list=lambda: fake_models)

        with patch("tools.ai.provider_model_clients.OpenAI", FakeClient):
            req = ListProviderModelsRequest(
                provider="OpenAI", api_key="sk-test", purpose="chat"
            )
            result = ProviderModelsService.list_models(req)

        ids = [m.id for m in result.models]
        # Heuristic flags gpt-5 with vision; embeddings excluded by purpose.
        assert "gpt-5" in ids
        assert "gpt-4o" in ids
        assert "text-embedding-3-small" not in ids
        # Newest first by created_at
        assert ids[0] == "gpt-5"
        gpt5 = next(m for m in result.models if m.id == "gpt-5")
        assert gpt5.capabilities.vision is True
        assert gpt5.created_at == 2_000_000_000

    def test_unauthorized_is_classified(self):
        class FakeAuthError(Exception):
            pass

        FakeAuthError.__name__ = "AuthenticationError"

        class FakeClient:
            def __init__(self, *args, **kwargs):
                def _raise():
                    raise FakeAuthError("Invalid API key sk-secret-12345")

                self.models = SimpleNamespace(list=_raise)

        with patch("tools.ai.provider_model_clients.OpenAI", FakeClient):
            req = ListProviderModelsRequest(
                provider="OpenAI", api_key="sk-secret-12345"
            )
            with pytest.raises(ProviderListingError) as exc:
                ProviderModelsService.list_models(req)

        assert exc.value.code == "unauthorized"
        assert "sk-secret-12345" not in exc.value.message


def _fake_anthropic_listing():
    import datetime as dt

    return SimpleNamespace(
        data=[
            SimpleNamespace(
                id="claude-opus-4-7",
                display_name="Claude Opus 4.7",
                created_at=dt.datetime(2026, 1, 1),
            ),
            SimpleNamespace(
                id="future-claude",
                display_name="Future Claude",
                created_at=dt.datetime(2026, 6, 1),
            ),
        ]
    )


class TestAnthropicAdapter:
    def test_capabilities_inferred_by_pattern(self):
        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = SimpleNamespace(list=_fake_anthropic_listing)

        fake_module = SimpleNamespace(Anthropic=FakeClient)
        with patch.dict("sys.modules", {"anthropic": fake_module}):
            req = ListProviderModelsRequest(provider="Anthropic", api_key="sk-x")
            result = ProviderModelsService.list_models(req)

        ids = [m.id for m in result.models]
        # Newest by created_at first
        assert ids[0] == "future-claude"
        opus = next(m for m in result.models if m.id == "claude-opus-4-7")
        # Pattern matches modern Claude → vision + chat
        assert opus.capabilities.vision is True
        assert opus.capabilities.chat is True


def _fake_mistral_listing():
    cap_chat = SimpleNamespace(
        completion_chat=True,
        completion_fim=False,
        function_calling=True,
        fine_tuning=False,
        vision=True,
    )
    cap_embed = SimpleNamespace(
        completion_chat=False,
        completion_fim=False,
        function_calling=False,
        fine_tuning=False,
        vision=False,
    )
    return SimpleNamespace(
        data=[
            SimpleNamespace(
                id="mistral-large-latest",
                name="Mistral Large",
                owned_by="mistralai",
                max_context_length=128000,
                deprecation=None,
                created=1_700_000_000,
                capabilities=cap_chat,
            ),
            SimpleNamespace(
                id="mistral-embed",
                name="Mistral Embed",
                owned_by="mistralai",
                max_context_length=8000,
                deprecation=None,
                created=1_650_000_000,
                capabilities=cap_embed,
            ),
        ]
    )


class TestMistralAdapter:
    def test_uses_native_capabilities(self):
        listing = _fake_mistral_listing()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = SimpleNamespace(list=lambda: listing)

        fake_module = SimpleNamespace(Mistral=FakeClient)
        with patch.dict("sys.modules", {"mistralai": fake_module}):
            req_chat = ListProviderModelsRequest(
                provider="MistralAI", api_key="x", purpose="chat"
            )
            req_emb = ListProviderModelsRequest(
                provider="MistralAI", api_key="x", purpose="embedding"
            )
            chat_result = ProviderModelsService.list_models(req_chat)
            emb_result = ProviderModelsService.list_models(req_emb)

        chat_ids = [m.id for m in chat_result.models]
        emb_ids = [m.id for m in emb_result.models]
        assert "mistral-large-latest" in chat_ids
        assert "mistral-embed" not in chat_ids
        assert "mistral-embed" in emb_ids
        large = next(m for m in chat_result.models if m.id == "mistral-large-latest")
        assert large.capabilities.vision is True
        assert large.capabilities.function_calling is True
        assert large.context_window == 128000
        assert large.created_at == 1_700_000_000


def _fake_google_pager():
    items = [
        SimpleNamespace(
            name="models/gemini-2.5-pro",
            display_name="Gemini 2.5 Pro",
            input_token_limit=2000000,
            supported_actions=["generateContent", "countTokens"],
        ),
        SimpleNamespace(
            name="models/gemini-1.5-pro",
            display_name="Gemini 1.5 Pro",
            input_token_limit=2000000,
            supported_actions=["generateContent"],
        ),
        SimpleNamespace(
            name="models/text-embedding-004",
            display_name="Text Embedding 004",
            input_token_limit=2048,
            supported_actions=["embedContent"],
        ),
    ]
    return iter(items)


class TestGoogleAdapter:
    def test_uses_supported_actions_and_version_sort(self):
        from google import genai

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = SimpleNamespace(
                    list=lambda config=None: _fake_google_pager()
                )

        with patch.object(genai, "Client", FakeClient):
            req = ListProviderModelsRequest(
                provider="Google", api_key="x", purpose="chat"
            )
            chat = ProviderModelsService.list_models(req)
            req_emb = ListProviderModelsRequest(
                provider="Google", api_key="x", purpose="embedding"
            )
            emb = ProviderModelsService.list_models(req_emb)

        chat_ids = [m.id for m in chat.models]
        # Newer version should appear before older one (no created_at)
        assert chat_ids[0] == "gemini-2.5-pro"
        assert chat_ids[1] == "gemini-1.5-pro"
        emb_ids = [m.id for m in emb.models]
        assert emb_ids == ["text-embedding-004"]


def _fake_ollama_listing():
    import datetime as dt

    return SimpleNamespace(
        models=[
            SimpleNamespace(
                model="llama3.2:latest",
                modified_at=dt.datetime(2026, 1, 15),
                details=SimpleNamespace(family="llama", families=["llama"]),
            ),
            SimpleNamespace(
                model="nomic-embed-text:latest",
                modified_at=dt.datetime(2025, 12, 1),
                details=SimpleNamespace(family="nomic-bert", families=["nomic-bert"]),
            ),
            SimpleNamespace(
                model="llava:13b",
                modified_at=dt.datetime(2026, 2, 1),
                details=SimpleNamespace(family="llava", families=["llama", "llava"]),
            ),
        ]
    )


class TestOllamaAdapter:
    def test_classifies_by_family_and_sorts_by_modified_at(self):
        listing = _fake_ollama_listing()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                # Mirror ollama.Client(host=..., timeout=...); we ignore both.
                ...

            def list(self):
                return listing

        fake_module = SimpleNamespace(Client=FakeClient)
        with patch.dict("sys.modules", {"ollama": fake_module}):
            req_chat = ListProviderModelsRequest(
                provider="Ollama", api_key="", purpose="chat"
            )
            chat = ProviderModelsService.list_models(req_chat)
            req_emb = ListProviderModelsRequest(
                provider="Ollama", api_key="", purpose="embedding"
            )
            emb = ProviderModelsService.list_models(req_emb)

        chat_ids = [m.id for m in chat.models]
        # llava is most recently modified → first; embeddings excluded.
        assert chat_ids[0] == "llava:13b"
        assert "llama3.2:latest" in chat_ids
        assert "nomic-embed-text:latest" not in chat_ids
        emb_ids = [m.id for m in emb.models]
        assert emb_ids == ["nomic-embed-text:latest"]
        llava = next(m for m in chat.models if m.id == "llava:13b")
        assert llava.capabilities.vision is True

    def test_ollama_allows_empty_api_key(self):
        listing = SimpleNamespace(models=[])

        class FakeClient:
            def __init__(self, *args, **kwargs):
                # Mirror ollama.Client(host=..., timeout=...); we ignore both.
                ...

            def list(self):
                return listing

        fake_module = SimpleNamespace(Client=FakeClient)
        with patch.dict("sys.modules", {"ollama": fake_module}):
            req = ListProviderModelsRequest(provider="Ollama", api_key="")
            result = ProviderModelsService.list_models(req)
        assert result.models == []
