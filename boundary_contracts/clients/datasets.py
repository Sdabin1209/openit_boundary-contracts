"""I2 DatasetStore의 HTTP 클라이언트(HTTP.md ## I2, D100). I3(models.py)와 같은 구조다."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Mapping, Optional

from ..canonical import file_hash
from ..errors import BoundaryError
from ._http import TAR_TYPE, HttpClientBase, build_tar, check_id, check_outgoing, check_record, check_str, integrity, verify_json_hash  # noqa: F401


def _safe_path(path: str) -> str:
    # 왜: manifest의 경로가 tar 항목과 URL 조각이 되므로 상위 경로·절대 경로를 보내기 전에 막는다(tar 규칙과 같다)
    if (not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or "\x00" in path
            or ".." in path.split("/")):
        raise BoundaryError("INVALID_RECORD", "데이터셋 파일 경로가 허용되지 않는다")
    return path


def check_publish(manifest: dict, read_bytes) -> None:
    """publish 검증(클라이언트와 참조 서버가 같은 규칙을 쓴다): 파일 해시, 줄 수, EVAL 시나리오가 학습·검증과 겹치지 않음.
    read_bytes(path) -> bytes. 위반은 해시면 INTEGRITY_ERROR, 그 밖은 INVALID_RECORD."""
    import hashlib
    scen: dict[str, set] = {"TRAIN": set(), "VALIDATION": set(), "EVAL": set()}
    for f in manifest["files"]:
        data = read_bytes(_safe_path(f["path"]))
        if "sha256:" + hashlib.sha256(data).hexdigest() != f["content_hash"]:
            raise integrity(f"{f['path']}의 해시가 manifest와 다르다")
        lines = [ln for ln in data.decode("utf-8").split("\n") if ln.strip()]
        if len(lines) != f["sample_count"]:
            raise BoundaryError("INVALID_RECORD", f"{f['path']}의 줄 수가 sample_count와 다르다")
        for ln in lines:
            try:
                sid = json.loads(ln).get("scenario_id")
            except (ValueError, AttributeError):
                raise BoundaryError("INVALID_RECORD", f"{f['path']}에 JSON이 아닌 줄이 있다") from None
            if sid is not None:
                scen[f["split"]].add(sid)
    if scen["EVAL"] & (scen["TRAIN"] | scen["VALIDATION"]):
        raise BoundaryError("INVALID_RECORD", "EVAL 시나리오가 TRAIN·VALIDATION과 겹친다")


class HttpDatasetStore(HttpClientBase):
    def list_ids(self, *, cursor: Optional[str] = None, limit: int = 100):
        return self._page("/v1/datasets", cursor, limit, item_check=check_str)

    def list_versions(self, dataset_id: str) -> list[str]:
        return self._all("/v1/datasets/" + self._q(dataset_id, "versions"), item_check=check_str)

    def get_manifest(self, dataset_id: str, version: str) -> dict:
        m = self._record("/v1/datasets/" + self._q(dataset_id, "versions", version), "DatasetManifest", hashed=True)
        if (m["dataset_id"], m["version"]) != (dataset_id, version):
            raise integrity("응답의 데이터셋이 요청과 다르다")
        return m

    def open_file(self, dataset_id: str, version: str, path: str) -> BinaryIO:
        """파일 바이트를 받아 manifest의 content_hash와 대조한 뒤 돌려준다. manifest에 없는 경로는 NOT_FOUND."""
        check_id(dataset_id, "dataset_id"), check_id(version, "version")
        entry = next((f for f in self.get_manifest(dataset_id, version)["files"] if f["path"] == path), None)
        if entry is None:
            raise BoundaryError("NOT_FOUND", "manifest에 없는 파일이다")
        data = self._bytes("/v1/datasets/" + self._q(dataset_id, "versions", version, "files", path))
        import hashlib
        if "sha256:" + hashlib.sha256(data).hexdigest() != entry["content_hash"]:
            raise integrity("파일의 해시가 manifest와 다르다")
        return io.BytesIO(data)

    def download(self, dataset_id: str, version: str, *, dest: Path) -> Path:
        """dest/<dataset_id>/<version> 아래에 파일 묶음을 풀고 파일마다 해시를 대조한다. 그 경로를 돌려준다."""
        check_id(dataset_id, "dataset_id"), check_id(version, "version")
        manifest = self.get_manifest(dataset_id, version)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(dir=dest, prefix=".dataset-"))
        try:
            self._download_tar("/v1/datasets/" + self._q(dataset_id, "versions", version, "files"), stage / "d", stage)
            want = {f["path"]: f["content_hash"] for f in manifest["files"]}
            got = sorted(p.relative_to(stage / "d").as_posix() for p in (stage / "d").rglob("*") if p.is_file())
            if got != sorted(want):
                raise integrity("묶음의 파일 집합이 manifest와 다르다")
            for p, h in want.items():
                if file_hash(stage / "d" / p) != h:
                    raise integrity(f"{p}의 해시가 manifest와 다르다")
            final = dest / dataset_id / version
            self._place(stage / "d", final)
            return final
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def publish(self, manifest: dict, files: Mapping[str, Path]) -> dict:
        check_outgoing("DatasetManifest", manifest)
        if set(files) != {f["path"] for f in manifest["files"]}:
            raise BoundaryError("INVALID_RECORD", "files의 키가 manifest.files[].path와 다르다")
        check_publish(manifest, lambda p: Path(files[p]).read_bytes())
        entries = {"manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8")}
        for p, src in files.items():
            entries["files/" + p] = Path(src)
        with build_tar(entries) as body:
            resp = self._open("POST", "/v1/datasets", None, body, TAR_TYPE, "application/json")
        raw = self._read(resp, self.max_body_bytes)
        try:
            rec = json.loads(raw)
        except ValueError:
            raise self._unavailable("JSON이 아닌 응답", status=resp.status) from None
        return check_record("DatasetManifest", rec, hashed=True)
