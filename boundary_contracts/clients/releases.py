"""I4 ReleaseReader와 I5 GateService의 HTTP 클라이언트."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..sdk import ReleaseBundle
from ._http import HttpClientBase, check_id, check_outgoing, check_record, integrity, verify_dir, verify_json_hash

ROLES = ("LORA_A", "LORA_B")


class HttpReleaseReader(HttpClientBase):
    def get_active_pointer(self) -> Optional[dict]:
        return self._optional("/v1/active-pointer", "ActivePointer")

    def get_release(self, release_id: str) -> dict:
        r = self._record("/v1/releases/" + self._q(release_id), "ReleaseManifest", hashed=True)
        if r["release_id"] != release_id:
            raise integrity("응답의 release_id가 요청과 다르다")
        return r

    def list_releases(self, *, cursor: Optional[str] = None, limit: int = 100):
        return self._page("/v1/releases", cursor, limit, schema="ReleaseManifest")

    def get_decision(self, decision_id: str) -> dict:
        d = self._record("/v1/decisions/" + self._q(decision_id), "GateDecision")
        if d["decision_id"] != decision_id:
            raise integrity("응답의 decision_id가 요청과 다르다")
        return d

    def find_decisions(self, *, question_set: Optional[dict] = None, lora_a: Optional[dict] = None,
                       lora_b: Optional[dict] = None, submission_id: Optional[str] = None,
                       cursor: Optional[str] = None, limit: int = 100):
        q = {"submission_id": submission_id}
        for key, ref in (("question_set", question_set), ("lora_a", lora_a), ("lora_b", lora_b)):
            if ref is not None:
                q[key + "_id"], q[key + "_version"] = ref["id"], ref["version"]
        return self._page("/v1/decisions", cursor, limit, q, schema="GateDecision")

    def load_bundle(self, release_id: str, *, dest: Path) -> ReleaseBundle:
        """dest/<release_id> 아래에 manifest.json, question_bank.json, adapters/<역할>/을 풀고 모든 해시를 검증한다."""
        check_id(release_id, "release_id")
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(dir=dest, prefix=".bundle-"))
        try:
            root = stage / "b"
            self._download_tar("/v1/releases/" + self._q(release_id, "bundle"), root, stage)
            try:
                manifest = json.loads((root / "manifest.json").read_bytes())
                bank = json.loads((root / "question_bank.json").read_bytes())
            except (OSError, ValueError):
                raise integrity("번들에 manifest.json 또는 question_bank.json이 없거나 JSON이 아니다") from None
            check_record("ReleaseManifest", manifest, hashed=True)
            if manifest["release_id"] != release_id:
                raise integrity("번들의 release_id가 요청과 다르다")
            if not isinstance(bank, dict):
                raise integrity("question_bank.json이 객체가 아니다")
            verify_json_hash(bank, manifest["question_set"]["content_hash"], "QuestionBank")
            for role in ROLES:
                a = root / "adapters" / role
                if not a.is_dir():
                    raise integrity(f"번들에 어댑터 {role}가 없다")
                verify_dir(a, manifest["adapters"][role]["adapter_hash"], f"어댑터 {role}")
            final = dest / release_id
            self._place(root, final)
            return ReleaseBundle(manifest, bank, {r: final / "adapters" / r for r in ROLES})
        finally:
            shutil.rmtree(stage, ignore_errors=True)


class HttpGateService(HttpClientBase):
    def submit_candidate(self, subject: dict, *, requested_by_role: str) -> dict:
        body = {"subject": subject, "requested_by_role": requested_by_role}
        return check_record("GateSubmission", self._json("POST", "/v1/submissions", body=body))

    def activate(self, release_id: str, *, requested_by_role: str) -> dict:
        body = {"release_id": release_id, "requested_by_role": requested_by_role}
        return check_record("ActivePointer", self._json("POST", "/v1/activate", body=body))

    def request_rollback(self, request: dict) -> dict:
        check_outgoing("RollbackRequest", request)
        return check_record("RollbackReceipt", self._json("POST", "/v1/rollback", body=request))
