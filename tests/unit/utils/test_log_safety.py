from utils.log_safety import sanitize_for_log


def test_line_breaks_cannot_forge_log_lines():
    forged = "abc\n2026-10-03 [INFO] admin logged in\r\nx"
    out = sanitize_for_log(forged)
    assert "\n" not in out and "\r" not in out
    assert out == "abc\\n2026-10-03 [INFO] admin logged in\\r\\nx"


def test_control_characters_are_escaped_and_text_kept():
    assert sanitize_for_log("a\x1b[31mb\tc ñ") == "a\\x1b[31mb\\x09c ñ"
    assert sanitize_for_log(42) == "42"


def test_long_values_are_capped():
    assert len(sanitize_for_log("x" * 2000)) == 501
