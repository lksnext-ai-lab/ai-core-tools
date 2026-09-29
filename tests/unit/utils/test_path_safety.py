import os

import pytest

from utils.path_safety import UnsafePathError, resolve_within


def test_relative_path_inside_base_is_resolved(tmp_path):
    assert resolve_within(str(tmp_path), "a", "b.txt") == os.path.join(os.path.realpath(tmp_path), "a", "b.txt")


def test_absolute_path_inside_base_is_allowed(tmp_path):
    inside = os.path.join(os.path.realpath(tmp_path), "x.txt")
    assert resolve_within(str(tmp_path), inside) == inside


@pytest.mark.parametrize("parts", [("..",), ("../etc/passwd",), ("a", "../../b"), ("/etc/passwd",)])
def test_paths_escaping_base_are_rejected(tmp_path, parts):
    with pytest.raises(UnsafePathError):
        resolve_within(str(tmp_path / "base"), *parts)


def test_sibling_directory_with_same_prefix_is_rejected(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base-evil").mkdir()
    with pytest.raises(UnsafePathError):
        resolve_within(str(tmp_path / "base"), "../base-evil/x")


def test_symlink_pointing_outside_base_is_rejected(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        resolve_within(str(base), "link", "secret")
