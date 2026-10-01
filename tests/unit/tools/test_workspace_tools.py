"""Unit tests for ``tools.ai.workspaceTools.create_download_url_tool``.

Focus: the SSRF/local-file-exfiltration hardening added to
``download_url_to_workspace`` — scheme allowlisting, host/IP validation, and that a
normal public-looking http(s) URL still passes validation.  No network access or DB
is used; DNS resolution and the HTTP fetch are both mocked.
"""

import socket
from unittest.mock import MagicMock, patch

from tools.ai.workspaceTools import create_download_url_tool


def _addr_info(ip: str):
    """Build a minimal socket.getaddrinfo()-shaped result for a single IPv4 address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


def test_file_scheme_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    result = tool.invoke({"url": "file:///etc/passwd", "filename": "out.txt"})

    assert result == "[Error] Only http/https URLs are allowed"


def test_ftp_scheme_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    result = tool.invoke({"url": "ftp://example.com/file.txt", "filename": "out.txt"})

    assert result == "[Error] Only http/https URLs are allowed"


def test_loopback_host_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("127.0.0.1")):
        result = tool.invoke({"url": "http://localhost/secret", "filename": "out.txt"})

    assert result.startswith("[Error] Refusing to download from disallowed host")


def test_private_ip_host_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("10.0.0.5")):
        result = tool.invoke({"url": "http://internal.example.com/file", "filename": "out.txt"})

    assert result.startswith("[Error] Refusing to download from disallowed host")


def test_link_local_metadata_host_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("169.254.169.254")):
        result = tool.invoke({"url": "http://169.254.169.254/latest/meta-data/", "filename": "out.txt"})

    assert result.startswith("[Error] Refusing to download from disallowed host")


def test_cgnat_range_host_is_rejected(tmp_path):
    """100.64.0.0/10 (RFC 6598) is used by some cloud metadata services (e.g.
    Alibaba Cloud's 100.100.100.200) and is NOT covered by
    ipaddress.is_private — must be checked explicitly."""
    tool = create_download_url_tool(str(tmp_path))

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("100.100.100.200")):
        result = tool.invoke({"url": "http://100.100.100.200/latest/meta-data/", "filename": "out.txt"})

    assert result.startswith("[Error] Refusing to download from disallowed host")


def test_public_host_passes_validation_and_downloads(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.headers = {"Content-Length": "5"}
    fake_response.iter_content.return_value = [b"hello"]
    fake_response.raise_for_status.return_value = None
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("93.184.216.34")), \
            patch("tools.ai.workspaceTools.requests.get", return_value=fake_response) as mock_get:
        result = tool.invoke({"url": "https://example.com/report.pdf", "filename": "report.pdf"})

    mock_get.assert_called_once()
    assert result == "Saved: output/report.pdf (5 bytes)"
    saved_file = tmp_path / "output" / "report.pdf"
    assert saved_file.read_bytes() == b"hello"


def test_download_exceeding_max_size_is_rejected(tmp_path):
    tool = create_download_url_tool(str(tmp_path))

    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.headers = {"Content-Length": str(200 * 1024 * 1024)}
    fake_response.raise_for_status.return_value = None
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch("tools.ai.workspaceTools.socket.getaddrinfo", return_value=_addr_info("93.184.216.34")), \
            patch("tools.ai.workspaceTools.requests.get", return_value=fake_response):
        result = tool.invoke({"url": "https://example.com/huge.bin", "filename": "huge.bin"})

    assert result == "[Error] File exceeds maximum allowed download size"
