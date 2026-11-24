"""Chat image URLs: no email in the URL, nothing sensitive in the log; the working dir is not put in the Chat prompt."""
from types import SimpleNamespace
from unittest.mock import patch

import tools.agentTools as at
from utils.security import verify_static_access


def _agent():
    return SimpleNamespace(prompt_template=None)


def _build(chat, monkeypatch):
    monkeypatch.setenv("AICT_BASE_URL", "https://mattin.example")
    img = {"file_path": "conversations/5/pic.png", "file_id": "FILE-ID-1"}
    seen = []
    with patch.object(at.logger, "info", side_effect=lambda m, *a: seen.append(m % a if a else m)):
        message = at.build_human_message(_agent(), "look", [img], {"email": "secret.user@example.com"}, chat_turn=chat)
    url = message.content[1]["image_url"]["url"]
    return url, seen


def test_a_chat_image_url_carries_an_opaque_identity_and_still_verifies(monkeypatch):
    url, logs = _build(True, monkeypatch)
    assert "secret.user" not in url and "example.com%40" not in url and "user=chat-image" in url
    sig = url.split("sig=")[1].split("&")[0]
    assert verify_static_access("conversations/5/pic.png", "chat-image", sig, None, None)
    joined = " ".join(logs)
    assert "FILE-ID-1" in joined and "sig=" not in joined and "https://" not in joined and "secret.user" not in joined


def test_other_channels_keep_their_url_but_never_log_it(monkeypatch):
    url, logs = _build(False, monkeypatch)
    assert "user=secret.user@example.com" in url
    assert "secret.user" not in " ".join(logs) and "sig=" not in " ".join(logs)
