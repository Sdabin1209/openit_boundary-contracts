"""I4 ReleaseReader와 I5 GateService의 HTTP 클라이언트."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..sdk import ReleaseBundle
from ._http import HttpClientBase, check_id, check_outgoing, check_record, integrity, verify_dir, verify_json_hash, verify_system_prompt

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

    def get_release_question_bank(self, release_id: str) -> dict:
        """GET /v1/releases/{id}/question-bank(2.7.0, OPEN_GAPS U47, SurveyQuestionBankRead). 어댑터 없이 릴리스에 묶인 문항 세트만.
        PASS가 아닌 릴리스는 412(load_bundle과 같다). 문항 세트 해시를 응답의 content_hash로 검증한다."""
        body = self._record("/v1/releases/" + self._q(check_id(release_id, "release_id"), "question-bank"), "SurveyQuestionBankRead")
        if body.get("release_id") != release_id or "question_bank" not in body or "content_hash" not in body:
            raise integrity("문항 세트 응답의 release_id가 요청과 다르거나 question_bank·content_hash가 없다")
        verify_json_hash(body["question_bank"], body["content_hash"], "QuestionBank")
        return body

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
                verify_system_prompt(a, manifest["adapters"][role]["system_prompt"])
            final = dest / release_id
            self._place(root, final)
            return ReleaseBundle(manifest, bank, {r: final / "adapters" / r for r in ROLES})
        finally:
            shutil.rmtree(stage, ignore_errors=True)


class HttpGateService(HttpClientBase):
    def submit_candidate(self, subject: dict, *, requested_by_role: str) -> dict:
        body = {"subject": subject, "requested_by_role": requested_by_role}
        check_outgoing("GateSubmissionRequest", body)   # 3.1.0
        return check_record("GateSubmission", self._json("POST", "/v1/submissions", body=body))

    def activate(self, release_id: str, *, requested_by_role: str) -> dict:
        body = {"release_id": release_id, "requested_by_role": requested_by_role}
        check_outgoing("ActivateRequest", body)   # 3.1.0: 보내는 본문을 계약으로 검사한다(CONVENTIONS 4절)
        return check_record("ActivePointer", self._json("POST", "/v1/activate", body=body))

    def request_rollback(self, request: dict) -> dict:
        check_outgoing("RollbackRequest", request)
        return check_record("RollbackReceipt", self._json("POST", "/v1/rollback", body=request))

    def get_review_report(self, submission_id: str) -> dict:
        """승인 요청 보고서(D53). 자동 검사 전이면 409(CONFLICT). 해시가 필요하면 get_review_report_with_hash."""
        return self.get_review_report_with_hash(submission_id)[0]

    def get_review_report_with_hash(self, submission_id: str) -> tuple:
        """(ReviewReport, X-Openit-Report-Hash). 승인자가 본 보고서의 해시를 decide(report_hash=...)에 그대로 넘긴다(3.1.0, HTTP.md I5).
        해시는 계산하지 않고 서버가 준 머리글 값을 쓴다."""
        check_id(submission_id)
        resp = self._open("GET", "/v1/submissions/" + self._q(submission_id, "review-report"), None, None, None, "application/json")
        report_hash = resp.headers.get("X-Openit-Report-Hash")
        try:
            body = json.loads(self._read(resp, self.max_body_bytes))
        except ValueError:
            raise integrity("review-report 응답이 JSON이 아니다") from None
        if not report_hash:
            raise integrity("review-report 응답에 X-Openit-Report-Hash가 없다")
        return check_record("ReviewReport", body), report_hash

    def decide(self, submission_id: str, decision: str, *, approver_role: str, report_hash: str,
               reason: Optional[str] = None) -> dict:
        """출고 결정(D53). 본문은 계약 ApprovalRequest{submission_id, decision, approver_role, report_hash, reason?}.
        승인자 신원은 본문이 아니라 X-Openit-User로만 간다(D88): 내부망에서 직접 부르면 클라이언트를 user=로 만든다.
        report_hash는 승인자가 본 보고서의 값(get_review_report_with_hash)이다. 결정 순간에 다시 받아 채우면 STALE_REPORT 검사가 무력해지므로 받지 않는다(3.1.0)."""
        check_id(submission_id)
        body = {"submission_id": submission_id, "decision": decision, "approver_role": approver_role, "report_hash": report_hash}
        if reason is not None:
            body["reason"] = reason
        check_outgoing("ApprovalRequest", body)
        return check_record("GateApproval", self._json("POST", "/v1/approvals", body=body))

    def list_submissions(self, *, status: Optional[str] = None, cursor: Optional[str] = None, limit: int = 100):
        """제출 목록(D68). 승인 대기 건은 status="AWAITING_APPROVAL"."""
        q = {"limit": limit}
        if status:
            q["status"] = status
        if cursor:
            q["cursor"] = cursor
        r = self._json("GET", "/v1/submissions", query=q)
        return [check_record("SubmissionView", x) for x in r.get("items", [])], r.get("next_cursor")

    def get_submission(self, submission_id: str) -> dict:
        check_id(submission_id)
        return check_record("SubmissionView", self._json("GET", f"/v1/submissions/{submission_id}"))
