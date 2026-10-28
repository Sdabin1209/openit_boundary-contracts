"""직원 호출 재알림·실패 기록의 HTTP 클라이언트(PUBLIC_API.md G절, CR-H001). 키오스크 기기 토큰으로 호출한다."""
from __future__ import annotations

from ._http import HttpClientBase, check_id, check_outgoing, check_record


class HttpStaffCall(HttpClientBase):
    def retry(self, session_id: str, turn_id: str) -> dict:
        """같은 alert_id로 다시 전달한다. 429(UNAVAILABLE)면 details.retry_after_s초 뒤에 다시 부른다."""
        check_id(session_id, "session_id")
        body = check_outgoing("StaffCallRetryRequest", {"turn_id": turn_id})
        return check_record("StaffCallRetryResult", self._json("POST", "/v1/sessions/" + self._q(session_id, "staff-call", "retry"), body=body))

    def report(self, session_id: str, outcome: str, turn_id: str) -> dict:
        """'직접 알리셨나요?' 응답을 남긴다. 갱신된 StaffAlert를 돌려준다."""
        check_id(session_id, "session_id")
        body = check_outgoing("StaffCallReport", {"outcome": outcome, "turn_id": turn_id})
        return check_record("StaffAlert", self._json("POST", "/v1/sessions/" + self._q(session_id, "staff-call", "report"), body=body))
