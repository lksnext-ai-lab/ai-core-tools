import os

import pytest

from utils import async_files


@pytest.mark.asyncio
async def test_text_json_and_bytes_round_trip(tmp_path):
    await async_files.write_text(str(tmp_path / "a.txt"), "ñandú ✓")
    assert await async_files.read_text(str(tmp_path / "a.txt")) == "ñandú ✓"

    await async_files.write_json(str(tmp_path / "a.json"), {"k": [1, 2]})
    assert await async_files.read_json(str(tmp_path / "a.json")) == {"k": [1, 2]}
    assert (tmp_path / "a.json").read_text() == '{\n  "k": [\n    1,\n    2\n  ]\n}'  # same as json.dump(indent=2)

    await async_files.write_bytes(str(tmp_path / "a.bin"), b"\x00\xff")
    assert (tmp_path / "a.bin").read_bytes() == b"\x00\xff"


@pytest.mark.asyncio
async def test_write_temp_file_persists_with_suffix_in_dir(tmp_path):
    path = await async_files.write_temp_file(b"data", suffix=".pdf", dir=str(tmp_path))

    assert os.path.dirname(path) == str(tmp_path)
    assert path.endswith(".pdf")
    assert open(path, "rb").read() == b"data"
