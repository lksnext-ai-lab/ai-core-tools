"""Bounded, safe delivery of sandbox output files (services.sandbox_output_pull)."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import nullcontext

import pytest

from services.agent_execution_service import _is_remote_output_file, _remote_workspace_relative
from services.sandbox_output_pull import PullLimits, pull_outputs, safe_local_name, unique_name
from tools.sandbox.provider import SandboxHandle, SandboxProvider


class Fake:
    def __init__(self, files: dict[str, bytes], sizes: dict | None = None):
        self.files = files
        self.sizes = sizes
        self.reads: list[str] = []
        self.asked: list[int] = []
        self.list_error: Exception | None = None
        self.gate: threading.Event | None = None

    def list_files(self, handle):
        if self.list_error:
            raise self.list_error
        return [f"/workspace/{p}" for p in self.files]

    def file_sizes(self, handle, rels):
        if self.sizes is not None:
            return self.sizes
        return {r: len(self.files[r]) for r in rels}

    def read_file(self, handle, rel):  # the unbounded read must never be used while a cap is configured
        raise AssertionError("unbounded read_file used")

    def read_file_limited(self, handle, rel, max_bytes):
        self.reads.append(rel)
        self.asked.append(max_bytes)
        if self.gate is not None:
            self.gate.wait(10)
        return self.files[rel][: max_bytes + 1]  # like the real providers: at most cap + 1 bytes


def run(provider, out, *, limits=None, chat=False, pre=frozenset()):
    limits = limits or PullLimits(20, 50 * 2**20, 100 * 2**20, 5.0)
    return asyncio.run(pull_outputs(
        provider, SandboxHandle("s", "/w", "fake"), is_output_file=_is_remote_output_file,
        to_relative=_remote_workspace_relative, pre_existing=set(pre), output_dir=str(out),
        lease=nullcontext, chat=chat, log_key="conv_1_1", limits=limits,
    ))


def test_files_under_the_limits_are_delivered_unchanged(tmp_path):
    p = Fake({"output/a.txt": b"A", "output/b.bin": b"BB"})
    outcome = run(p, tmp_path)
    assert (outcome.pulled, outcome.skipped, outcome.incomplete) == (2, 0, False)
    assert (tmp_path / "a.txt").read_bytes() == b"A" and (tmp_path / "b.bin").read_bytes() == b"BB"


def test_the_size_cap_skips_big_files_without_reading_them(tmp_path):
    p = Fake({"output/small": b"x", "output/big": b"y" * 50})
    outcome = run(p, tmp_path, limits=PullLimits(20, 10, 1000, 5))
    assert (outcome.pulled, outcome.skipped) == (1, 1)
    assert p.reads == ["output/small"]  # the big one was never read
    assert not (tmp_path / "big").exists()


def test_total_and_count_caps(tmp_path):
    p = Fake({f"output/f{i}": b"z" * 10 for i in range(6)})
    outcome = run(p, tmp_path, limits=PullLimits(20, 100, 35, 5))  # 3 fit in 35 bytes
    assert (outcome.pulled, outcome.skipped) == (3, 3)
    outcome = run(Fake({f"output/g{i}": b"z" for i in range(6)}), tmp_path, limits=PullLimits(2, 100, 100, 5))
    assert (outcome.pulled, outcome.skipped) == (2, 4)


def test_unknown_size_never_reads_more_than_cap_plus_one(tmp_path):
    p = Fake({"output/x": b"y" * 5000}, sizes={})
    outcome = run(p, tmp_path, limits=PullLimits(20, 10, 1000, 5))
    assert (outcome.pulled, outcome.skipped) == (0, 1) and not (tmp_path / "x").exists()
    assert p.asked == [10]  # the fake was asked for at most the cap (it hands back cap + 1)


def test_a_lying_stat_does_not_lift_the_cap(tmp_path):
    p = Fake({"output/huge": b"z" * 100_000}, sizes={"output/huge": 1})  # the sandbox claims 1 byte
    outcome = run(p, tmp_path, limits=PullLimits(20, 100, 1000, 5))
    assert (outcome.pulled, outcome.skipped) == (0, 1)
    assert p.asked == [100] and not (tmp_path / "huge").exists()


def test_a_file_that_grows_between_stat_and_read_is_still_bounded(tmp_path):
    p = Fake({"output/g": b"a" * 50})
    original = p.read_file_limited

    def grown(handle, rel, max_bytes):  # stat saw 50 bytes, the read sees much more
        p.files[rel] = b"a" * 10_000
        return original(handle, rel, max_bytes)

    p.read_file_limited = grown
    outcome = run(p, tmp_path, limits=PullLimits(20, 100, 1000, 5))
    assert outcome.skipped == 1 and p.asked == [100] and not (tmp_path / "g").exists()


def test_many_candidates_beyond_the_stat_window_are_still_bounded(tmp_path):
    p = Fake({f"output/f{i}": b"q" * 500 for i in range(300)}, sizes={})
    run(p, tmp_path, limits=PullLimits(5, 100, 1000, 5))
    assert p.asked and max(p.asked) <= 100


def test_the_remaining_total_budget_bounds_each_read(tmp_path):
    p = Fake({"output/a": b"1" * 60, "output/b": b"2" * 60}, sizes={})
    outcome = run(p, tmp_path, limits=PullLimits(20, 100, 100, 5))
    assert outcome.pulled == 1 and p.asked == [100, 40]  # second read capped at what is left of the total


def test_a_provider_that_cannot_bound_a_read_is_refused_not_read_whole(tmp_path):
    p = Fake({"output/a": b"x", "output/b": b"y"})

    def refuse(handle, rel, max_bytes):
        raise NotImplementedError

    p.read_file_limited = refuse
    outcome = run(p, tmp_path)
    assert outcome.refused and outcome.pulled == 0 and outcome.skipped == 2


def test_a_zero_budget_means_no_budget_and_busy_slots_skip_at_once(tmp_path):
    import services.sandbox_output_pull as module

    assert PullLimits.from_settings().time_budget_s >= 0
    outcome = run(Fake({"output/a": b"A"}), tmp_path, limits=PullLimits(20, 100, 100, 0))
    assert outcome.pulled == 1
    pool, slots = module._executor()
    held = [slots.acquire(blocking=False) for _ in range(5)]
    try:
        busy = run(Fake({"output/a": b"A"}), tmp_path)
    finally:
        for ok in held:
            if ok:
                slots.release()
    assert busy.incomplete and busy.pulled == 0


def test_symlinks_in_the_sandbox_are_never_followed(tmp_path):
    p = Fake({"output/link": b"secret"}, sizes={"output/link": -1})
    outcome = run(p, tmp_path)
    assert outcome.skipped == 1 and p.reads == []


def test_same_basename_in_two_folders_does_not_overwrite(tmp_path):
    p = Fake({"output/a/x.txt": b"one", "output/b/x.txt": b"two"})
    outcome = run(p, tmp_path)
    assert outcome.pulled == 2
    assert sorted(f.read_bytes() for f in tmp_path.iterdir()) == [b"one", b"two"]
    assert {f.name for f in tmp_path.iterdir()} == {"x.txt", "x-2.txt"}


@pytest.mark.parametrize("name", ["", ".", "..", ".hidden", "a\x00b", "a\nb", "x" * 300])
def test_unsafe_names_are_refused(name):
    assert safe_local_name(f"output/{name}") is None


def test_only_the_base_name_is_ever_used_and_nothing_escapes(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert safe_local_name("output/../../etc/passwd") == "passwd"  # a base name only, written inside out/
    assert safe_local_name("/abs/evil") == "evil"
    p = Fake({"output/..%2f..%2fevil": b"e", "output/sub/ok.txt": b"k"})
    run(p, out)
    assert {f.name for f in out.iterdir()} <= {"..%2f..%2fevil", "ok.txt"}
    assert not any(tmp_path.glob("evil*"))


def test_a_symlink_at_the_destination_is_replaced_not_followed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    os.symlink(target, out / "a.txt")
    run(Fake({"output/a.txt": b"new"}), out)
    assert target.read_text() == "keep"
    assert (out / "a.txt").read_bytes() == b"new" and not (out / "a.txt").is_symlink()


def test_unique_name_numbers_collisions():
    used: set = set()
    assert [unique_name("a.txt", used) for _ in range(3)] == ["a.txt", "a-2.txt", "a-3.txt"]


def test_list_files_raising_is_contained_and_chat_logs_class_name_only(tmp_path, caplog):
    p = Fake({})
    p.list_error = RuntimeError("SECRET-MARKER /workspace/evil-name.txt")
    import services.sandbox_output_pull as module

    lines: list[str] = []

    def record(message, *args):
        lines.append(message % args if args else message)

    from unittest.mock import patch

    with patch.object(module.logger, "warning", side_effect=record), \
         patch.object(module.logger, "error", side_effect=record), \
         patch.object(module.logger, "info", side_effect=record), \
         patch.object(module.logger, "debug", side_effect=record):
        outcome = run(p, tmp_path, chat=True)
    text = "\n".join(lines)
    assert outcome.incomplete and outcome.pulled == 0
    assert "SECRET-MARKER" not in text and "evil-name" not in text
    assert "RuntimeError" in text and "conv_1_1" in text


def test_a_read_that_hangs_past_the_budget_returns_in_time_and_keeps_going(tmp_path):
    p = Fake({"output/a.txt": b"A"})
    p.gate = threading.Event()
    try:
        outcome = run(p, tmp_path, limits=PullLimits(20, 100, 100, 0.3))
    finally:
        p.gate.set()
    assert outcome.incomplete and outcome.pulled == 0
    assert outcome.undelivered == 1


def test_default_file_sizes_parses_stat_output():
    class P(SandboxProvider):
        SUPPORTED_LANGUAGES = ["bash"]

        def create_sandbox(self, *a, **k): ...
        def destroy_sandbox(self, handle): ...
        def run_code(self, handle, code, **k):
            return "regular file|12|output/a b.txt\nsymbolic link|3|output/l\nregular file|x|output/bad\n"
        def write_file(self, *a): ...
        def read_file(self, *a): ...
        def list_files(self, *a): ...

    sizes = P().file_sizes(SandboxHandle("s", "/w", "p"), ["output/a b.txt", "output/l", "output/bad", "output/none"])
    assert sizes == {"output/a b.txt": 12, "output/l": -1, "output/bad": -1}
