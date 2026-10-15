"""I1 QuestionReader의 HTTP 클라이언트."""
from __future__ import annotations

from typing import Optional

from ._http import HttpClientBase, check_ref, check_str, integrity, verify_json_hash


class HttpQuestionReader(HttpClientBase):
    def _versions_path(self, ref: dict) -> str:
        check_ref(ref)
        return "/v1/question-sets/" + self._q(ref["id"], "versions", ref["version"])

    def get_question_bank(self, ref: dict) -> dict:
        bank = self._json("GET", self._versions_path(ref))
        if not isinstance(bank, dict):
            raise integrity("QuestionBank 응답이 객체가 아니다")
        verify_json_hash(bank, ref["content_hash"], "QuestionBank")
        if "version" in bank and str(bank["version"]) != ref["version"]:
            raise integrity("QuestionBank.version이 ref.version과 다르다")
        return bank

    def latest(self, question_set_id: str, *, reviewed_only: bool = False) -> dict:
        ref = self._json("GET", "/v1/question-sets/" + self._q(question_set_id, "latest"),
                         {"reviewed_only": "true" if reviewed_only else "false"})
        try:
            check_ref(ref)
        except Exception:
            raise integrity("ArtifactRef 응답이 형식에 맞지 않는다") from None
        if ref["id"] != question_set_id:
            raise integrity("응답의 문항 세트 ID가 요청과 다르다")
        return ref

    def list_ids(self, *, cursor: Optional[str] = None, limit: int = 100):
        return self._page("/v1/question-sets", cursor, limit, item_check=check_str)

    def list_versions(self, question_set_id: str, *, cursor: Optional[str] = None, limit: int = 100):
        def chk(r):
            try:
                check_ref(r)
            except Exception:
                raise integrity("ArtifactRef 응답이 형식에 맞지 않는다") from None
        return self._page("/v1/question-sets/" + self._q(question_set_id, "versions"), cursor, limit, item_check=chk)

    def get_reviews(self, ref: dict) -> list[dict]:
        return self._all(self._versions_path(ref) + "/reviews", schema="ReviewRecord")

    def get_change(self, ref: dict) -> Optional[dict]:
        return self._optional(self._versions_path(ref) + "/change", "ChangeClassification")
