import base64
from unittest.mock import patch

from tools.ai.fileTools import fetch_file_in_base64


def _invoke(tmp_path, file_path):
    with patch("tools.ai.fileTools.get_app_config", return_value={"TMP_BASE_FOLDER": str(tmp_path / "tmp")}):
        return fetch_file_in_base64.invoke({"file_path": file_path})


def test_reads_attachment_under_tmp_base_folder(tmp_path):
    (tmp_path / "tmp" / "conversations" / "1").mkdir(parents=True)
    (tmp_path / "tmp" / "conversations" / "1" / "doc.txt").write_bytes(b"hello")

    assert _invoke(tmp_path, "conversations/1/doc.txt") == base64.b64encode(b"hello").decode()


def test_refuses_files_outside_tmp_base_folder(tmp_path):
    """Regression (Sonar pythonsecurity:S2083): the LLM could read any file on the server."""
    (tmp_path / "tmp").mkdir()
    secret = tmp_path / "secret.env"
    secret.write_bytes(b"SECRET_KEY=x")

    for path in (str(secret), "../secret.env", "/etc/passwd"):
        assert _invoke(tmp_path, path).startswith("Error:")
