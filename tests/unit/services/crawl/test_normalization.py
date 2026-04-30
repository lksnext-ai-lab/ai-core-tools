"""Unit tests for crawl URL normalization utilities."""
import pytest
from services.crawl.normalization import normalize_url, same_host


def test_lowercase_host():
    assert normalize_url('HTTP://Example.COM/path') == 'http://example.com/path'


def test_strip_fragment():
    assert normalize_url('https://example.com/page#section') == 'https://example.com/page'


def test_strip_tracking_params_utm():
    result = normalize_url('https://example.com/?utm_source=x&q=1')
    assert 'utm_source' not in result
    assert 'q=1' in result


def test_strip_gclid():
    result = normalize_url('https://example.com/?gclid=abc')
    assert 'gclid' not in result


def test_strip_fbclid():
    result = normalize_url('https://example.com/?fbclid=abc')
    assert 'fbclid' not in result


def test_drop_default_port_http():
    assert normalize_url('http://example.com:80/path') == 'http://example.com/path'


def test_drop_default_port_https():
    assert normalize_url('https://example.com:443/path') == 'https://example.com/path'


def test_non_default_port_kept():
    result = normalize_url('https://example.com:8443/path')
    assert '8443' in result


def test_trailing_slash_stripped():
    assert normalize_url('https://example.com/path/') == 'https://example.com/path'


def test_root_slash_preserved():
    assert normalize_url('https://example.com/') == 'https://example.com/'


def test_same_host_true():
    assert same_host('https://example.com/a', 'https://example.com/b') is True


def test_same_host_www():
    # www subdomain is treated as a different host
    assert same_host('https://example.com/', 'https://www.example.com/') is False


def test_same_host_different_domain():
    assert same_host('https://example.com/', 'https://other.com/') is False
