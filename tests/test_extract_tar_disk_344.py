"""3.4.4 RUNTIME R3.27: tar 를 푸는 중 호출자 쪽 쓰기 실패는 UNAVAILABLE(재시도 가능), 내용 위반은 INTEGRITY_ERROR."""
import io
import tarfile
from unittest import mock

import pytest

from boundary_contracts import BoundaryError
from boundary_contracts.clients import _http


def _tar(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf


def test_disk_full_while_writing_is_unavailable(tmp_path):
    real_open = open

    def full(path, mode="r", *a, **k):
        if "x" in mode:
            raise OSError(28, "No space left on device")
        return real_open(path, mode, *a, **k)

    with mock.patch("builtins.open", full):
        with pytest.raises(BoundaryError) as e:
            _http.extract_tar(_tar({"a.txt": b"hello"}), tmp_path / "out", 1 << 20)
    assert e.value.code == "UNAVAILABLE"
    assert e.value.retryable is True
    assert e.value.details["reason"] == "OSError"


def test_corrupt_tar_is_integrity_error(tmp_path):
    with pytest.raises(BoundaryError) as e:
        _http.extract_tar(io.BytesIO(b"not a tar at all" * 100), tmp_path / "out", 1 << 20)
    assert e.value.code == "INTEGRITY_ERROR"


def test_good_tar_extracts(tmp_path):
    _http.extract_tar(_tar({"d/a.txt": b"hello"}), tmp_path / "out", 1 << 20)
    assert (tmp_path / "out" / "d" / "a.txt").read_bytes() == b"hello"
