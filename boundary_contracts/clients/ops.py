"""I6 TraceIngest와 I7 FailureStore의 HTTP 클라이언트."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..errors import BoundaryError
from ._http import HttpClientBase, check_outgoing, check_record, integrity


class HttpTraceIngest(HttpClientBase):
    def send(self, envelope: dict) -> dict:
        check_outgoing("TraceEnvelope", envelope)
        return check_record("IngestResult", self._json("POST", "/v1/traces", body=envelope))


class HttpFailureStore(HttpClientBase):
    def publish_case(self, case: dict) -> dict:
        raise BoundaryError("FAILED_PRECONDITION", "publish_case는 HTTP로 열지 않는다(ops-feedback 내부 잡이 쓴다)")

    def get_case(self, case_id: str, *, version: Optional[int] = None) -> dict:
        c = self._record("/v1/cases/" + self._q(case_id), "FailureCase", {"version": version})
        if c["case_id"] != case_id or (version is not None and c["version"] != version):
            raise integrity("응답의 케이스가 요청과 다르다")
        return c

    def list_cases(self, *, review_status: Optional[str] = None, failure_type: Optional[str] = None,
                   source_release_id: Optional[str] = None, updated_since: Optional[datetime] = None,
                   latest_only: bool = True, cursor: Optional[str] = None, limit: int = 100):
        since = None
        if updated_since is not None:
            t = updated_since if updated_since.tzinfo else updated_since.replace(tzinfo=timezone.utc)
            since = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        q = {"review_status": review_status, "failure_type": failure_type, "source_release_id": source_release_id,
             "updated_since": since, "latest_only": "true" if latest_only else "false"}
        return self._page("/v1/cases", cursor, limit, q, schema="FailureCase")

    def get_trace(self, deidentified_trace_ref: str) -> dict:
        # U45(2.5.1): 객체인지만 보던 것을 계약 스키마로(비식별 결과가 계약을 어기면 받는 쪽이 원문 조각을 쓰지 않게)
        return check_record("OpsFeedbackDeidentifiedTrace", self._json("GET", "/v1/deidentified-traces/" + self._q(deidentified_trace_ref)))
