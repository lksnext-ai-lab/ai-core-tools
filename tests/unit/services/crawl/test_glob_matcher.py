"""Unit tests for crawl glob matching utilities."""
import pytest
from services.crawl.glob_matcher import matches_glob, should_include, validate_globs


def test_empty_include_pass_through():
    assert should_include('/about', [], []) is True


def test_include_filter_miss():
    assert should_include('/blog', ['/docs/**'], []) is False


def test_include_filter_hit():
    assert should_include('/docs/page', ['/docs/**'], []) is True


def test_exclude_wins_over_include():
    assert should_include('/docs/private', ['/docs/**'], ['/docs/private']) is False


def test_double_star_matches_slash():
    assert matches_glob('/docs/**', '/docs/a/b/c') is True


def test_single_star_no_slash():
    assert matches_glob('/docs/*', '/docs/a/b') is False


def test_single_star_matches_single_segment():
    assert matches_glob('/docs/*', '/docs/page') is True


def test_root_glob():
    assert matches_glob('/**', '/any/path/here') is True


def test_exact_match():
    assert matches_glob('/about', '/about') is True


def test_no_match():
    assert matches_glob('/blog/*', '/about') is False


def test_validate_globs_valid():
    assert validate_globs(['/docs/**', '/blog/*']) == []


def test_validate_globs_empty():
    assert validate_globs([]) == []


def test_exclude_only_excludes_matching():
    # Only the matching URL is excluded; non-matching is still included
    assert should_include('/api/private', [], ['/api/private']) is False
    assert should_include('/api/public', [], ['/api/private']) is True
