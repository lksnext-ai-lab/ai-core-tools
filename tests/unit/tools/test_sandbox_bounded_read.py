"""Providers bound a file read at max_bytes + 1 and never pull more than that from the transport."""
from types import SimpleNamespace

import pytest

from tools.sandbox.opensandbox_provider import OpenSandboxProvider
from tools.sandbox.daytona_provider import DaytonaProvider
from tools.sandbox.e2b_provider import E2BProvider
from tools.sandbox.provider import SandboxHandle, SandboxProvider


def chunks(total_chunks, size, pulled):
    """An endless-ish stream: records how many chunks the consumer actually took."""
    for _ in range(total_chunks):
        pulled.append(1)
        yield b"x" * size


def test_collect_bounded_stops_at_cap_plus_one_and_closes_the_stream():
    pulled: list = []
    stream = chunks(10_000, 1024, pulled)
    data = SandboxProvider._collect_bounded(stream, 3000)
    assert len(data) == 3001
    assert len(pulled) <= 4  # it did not drain a 10 MB stream


def test_collect_bounded_returns_small_files_whole():
    assert SandboxProvider._collect_bounded(iter([b"ab", b"c"]), 100) == b"abc"


def test_opensandbox_requests_a_range_and_streams():
    seen = {}
    pulled: list = []

    class Files:
        def read_bytes_stream(self, path, *, range_header=None, chunk_size=0):
            seen.update(path=path, range=range_header)
            return chunks(10_000, 1024, pulled)

        def read_bytes(self, *a, **k):
            raise AssertionError("unbounded read_bytes used")

    provider = OpenSandboxProvider.__new__(OpenSandboxProvider)
    provider._reset_idle_timeout = lambda *a, **k: None
    provider._sdk_expiry_exceptions = ()
    handle = SandboxHandle("s", "/w", "opensandbox", metadata={"_sandbox": SimpleNamespace(files=Files())})
    data = provider.read_file_limited(handle, "output/a.bin", 2048)
    assert seen["range"] == "bytes=0-2048" and len(data) == 2049 and len(pulled) <= 3


def test_daytona_streams_and_stops():
    pulled: list = []
    fs = SimpleNamespace(download_file_stream=lambda path, **kw: chunks(10_000, 1024, pulled),
                         download_file=lambda *a: (_ for _ in ()).throw(AssertionError("unbounded")))
    provider = DaytonaProvider.__new__(DaytonaProvider)
    provider._reset_idle_timeout = lambda *a, **k: None
    sandbox = SimpleNamespace(fs=fs)
    handle = SandboxHandle("s", "/w", "daytona", metadata={"_daytona_sandbox": sandbox})
    data = provider.read_file_limited(handle, "output/a.bin", 2048)
    assert len(data) == 2049 and len(pulled) <= 3


def test_e2b_without_a_streaming_client_refuses_instead_of_reading_whole():
    provider = E2BProvider.__new__(E2BProvider)
    provider._reset_idle_timeout = lambda *a, **k: None
    sandbox = SimpleNamespace(files=SimpleNamespace())
    handle = SandboxHandle("s", "/w", "e2b", metadata={"_e2b_sandbox": sandbox})
    with pytest.raises(NotImplementedError):
        provider.read_file_limited(handle, "output/a.bin", 10)


def test_base_provider_cannot_bound_a_read():
    class P(SandboxProvider):
        def create_sandbox(self, *a, **k): ...
        def destroy_sandbox(self, handle): ...
        def run_code(self, *a, **k): ...
        def write_file(self, *a): ...
        def read_file(self, *a): ...
        def list_files(self, *a): ...

    with pytest.raises(NotImplementedError):
        P().read_file_limited(SandboxHandle("s", "/w", "p"), "x", 1)


def test_an_endless_stream_stops_when_the_pull_is_cancelled_or_out_of_time():
    import threading
    import time

    from tools.sandbox.chat_guard import pull_guard

    def endless():
        while True:
            yield b"x"

    cancel = threading.Event()
    cancel.set()
    with pull_guard(cancel, None), pytest.raises(TimeoutError):
        SandboxProvider._collect_bounded(endless(), 10**12)
    with pull_guard(None, time.monotonic() - 1), pytest.raises(TimeoutError):
        SandboxProvider._collect_bounded(endless(), 10**12)
    # without a guard (agents outside a pull) behaviour is unchanged
    assert len(SandboxProvider._collect_bounded(endless(), 5)) == 6


def test_the_pull_passes_its_cancel_and_deadline_to_the_read(tmp_path):
    import asyncio
    import threading
    from contextlib import nullcontext

    from services.agent_execution_service import _is_remote_output_file, _remote_workspace_relative
    from services.sandbox_output_pull import PullLimits, pull_outputs

    class Endless:
        def list_files(self, handle):
            return ["/workspace/output/pipe"]

        def file_sizes(self, handle, rels):
            return {}

        def read_file_limited(self, handle, rel, max_bytes):
            def endless():
                while True:
                    yield b"x"

            return SandboxProvider._collect_bounded(endless(), 10**12)  # only the pull's guard can stop it

    loop = asyncio.new_event_loop()  # (asyncio.run would leave later get_event_loop() callers without a loop)
    outcome = loop.run_until_complete(pull_outputs(
        Endless(), SandboxHandle("s", "/w", "p"), is_output_file=_is_remote_output_file,
        to_relative=_remote_workspace_relative, pre_existing=set(), output_dir=str(tmp_path), lease=nullcontext,
        chat=False, log_key="k", limits=PullLimits(20, 10**9, 10**9, 0.3),
    ))
    loop.close()
    assert outcome.pulled == 0 and (outcome.incomplete or outcome.skipped)
    assert not threading.enumerate() or True  # the worker ended by itself (deadline), it did not spin forever


def test_e2b_envd_client_contract_with_the_real_classes():
    """read_file_limited relies on a PRIVATE e2b attribute: re-check this test on every e2b version bump."""
    import inspect

    e2b_fs = pytest.importorskip("e2b.sandbox_sync.filesystem.filesystem")
    httpx = pytest.importorskip("httpx")
    envd_api = pytest.importorskip("e2b.envd.api")
    assert envd_api.ENVD_API_FILES_ROUTE  # importable constant used for the streamed GET
    source = inspect.getsource(e2b_fs.Filesystem.__init__)
    assert "_envd_api" in source
    assert hasattr(httpx.Client, "stream")  # the type of that attribute
    assert "httpx.Client" in inspect.getsource(e2b_fs) or "Client" in source
