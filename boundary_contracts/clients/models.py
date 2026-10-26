"""I3 ModelRegistry의 HTTP 클라이언트."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..canonical import directory_hash
from ..errors import BoundaryError
from ._http import (TAR_TYPE, HttpClientBase, build_tar, check_id, check_outgoing, check_record, check_str, integrity,
                    verify_dir, verify_system_prompt)


class HttpModelRegistry(HttpClientBase):
    def list_ids(self, *, cursor: Optional[str] = None, limit: int = 100):
        return self._page("/v1/packages", cursor, limit, item_check=check_str)

    def list_versions(self, package_id: str) -> list[str]:
        return self._all("/v1/packages/" + self._q(package_id, "versions"), item_check=check_str)

    def get_manifest(self, package_id: str, version: str) -> dict:
        m = self._record("/v1/packages/" + self._q(package_id, "versions", version), "ModelPackageManifest", hashed=True)
        if (m["package_id"], m["version"]) != (package_id, version):
            raise integrity("응답의 패키지가 요청과 다르다")
        return m

    def open_adapter(self, package_id: str, version: str, *, dest: Path) -> Path:
        """dest/<package_id>/<version> 아래에 풀고 directory_hash를 manifest.adapter_hash와 대조한다. 그 경로를 돌려준다."""
        check_id(package_id, "package_id"), check_id(version, "version")
        manifest = self.get_manifest(package_id, version)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(dir=dest, prefix=".adapter-"))
        try:
            self._download_tar("/v1/packages/" + self._q(package_id, "versions", version, "adapter"), stage / "a", stage)
            verify_dir(stage / "a", manifest["adapter_hash"], "어댑터")
            verify_system_prompt(stage / "a", manifest["system_prompt"])
            final = dest / package_id / version
            self._place(stage / "a", final)
            return final
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def get_eval_report(self, ref: str) -> bytes:
        return self._bytes("/v1/eval-reports/" + self._q(ref))

    def publish(self, manifest: dict, adapter_dir: Path, eval_report: bytes) -> dict:
        check_outgoing("ModelPackageManifest", manifest)
        adapter_dir = Path(adapter_dir)
        if not adapter_dir.is_dir():
            raise BoundaryError("INVALID_RECORD", "adapter_dir가 디렉터리가 아니다")
        if directory_hash(adapter_dir) != manifest["adapter_hash"]:
            raise integrity("adapter_dir의 해시가 manifest.adapter_hash와 다르다")
        verify_system_prompt(adapter_dir, manifest["system_prompt"])
        entries = {"manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                   "eval_report": bytes(eval_report)}
        for p in adapter_dir.rglob("*"):
            if p.is_file():
                entries["adapter/" + p.relative_to(adapter_dir).as_posix()] = p
        with build_tar(entries) as body:
            resp = self._open("POST", "/v1/packages", None, body, TAR_TYPE, "application/json")
        raw = self._read(resp, self.max_body_bytes)
        try:
            rec = json.loads(raw)
        except ValueError:
            raise self._unavailable("JSON이 아닌 응답", status=resp.status) from None
        return check_record("ModelPackageManifest", rec, hashed=True)
