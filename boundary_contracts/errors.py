"""경계 호출의 공통 오류(CONVENTIONS.md 3절). 모든 SDK와 서비스 클라이언트는 이것을 던진다."""
from __future__ import annotations

from typing import Any

CODES = {
    "NOT_FOUND": False,
    "INVALID_RECORD": False,
    "UNSUPPORTED_VERSION": False,
    "CONFLICT": False,
    "INTEGRITY_ERROR": False,
    "FAILED_PRECONDITION": False,
    "PERMISSION_DENIED": False,
    "UNAVAILABLE": True,
}


class BoundaryError(Exception):
    """code는 CODES의 키, retryable은 코드로 정해진다(UNAVAILABLE만 true)."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        if code not in CODES:
            raise ValueError(f"알 수 없는 오류 코드: {code}")
        if not isinstance(message, str) or not message:
            raise ValueError("BoundaryError.message 는 비어 있지 않은 문자열이다(계약 BoundaryError.message minLength 1)")   # 4.0.0: 만들 때 막아 직렬화가 계약을 어기지 않게
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}

    @property
    def retryable(self) -> bool:
        return CODES[self.code]

    def to_record(self, pipeline_schema_version: str | None = None) -> dict:
        """BoundaryError 스키마에 맞는 레코드."""
        from .schemas_api import PIPELINE_SCHEMA_VERSION
        rec = {"pipeline_schema_version": pipeline_schema_version or PIPELINE_SCHEMA_VERSION, "code": self.code,
               "message": self.message, "retryable": self.retryable}
        if self.details:
            rec["details"] = self.details
        from .schemas_api import validator
        errs = sorted("/".join(map(str, e.absolute_path)) or "(최상위)" for e in validator("BoundaryError").iter_errors(rec))
        if errs:   # 생산자 검증(R7): 계약을 어긴 오류 레코드를 내보내지 않는다(값은 싣지 않고 위치만)
            raise ValueError("BoundaryError 레코드가 계약을 어긴다: " + ", ".join(errs[:5]))
        return rec

    @classmethod
    def from_record(cls, rec: dict) -> "BoundaryError":
        return cls(rec["code"], rec["message"], rec.get("details"))
