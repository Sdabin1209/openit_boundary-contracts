"""공개 API(I10, PUBLIC_API.md)의 HTTP 클라이언트: 세션 시작·발화·종료·상태 조회와 직원 개입 결정, /healthz.

본문 스키마(`FrontendMessage`, `FrontendInput`)는 문진 스키마(survey-service 소유)라 이 패키지에 없다. 그래서 보내는 본문은
PUBLIC_API.md의 모양을 여기서 직접 확인하고, 받는 `FrontendInput`은 필수 필드와 타입만 읽기 모드로 확인한다(위반은 INTEGRITY_ERROR).
`SessionState`는 이 패키지 스키마로 검증한다. 키오스크는 기기 토큰, 개입 결정은 staff 토큰으로 부른다.
"""
from __future__ import annotations

import re
from typing import Optional

from ..errors import BoundaryError
from ._http import HttpClientBase, check_record, integrity

_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SUBJECT_REF = re.compile(r"^[A-Za-z0-9._:/#=+-]{1,128}$")


_DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")   # 인증서 주체 CN에서 온 기기 ID(ADR 0012)


def _sid(session_id) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID.match(session_id):
        raise BoundaryError("INVALID_RECORD", "session_id는 영문·숫자·-_ 1~64자여야 한다")
    return session_id


def _turn(turn_id) -> str:
    if not isinstance(turn_id, str) or not turn_id:
        raise BoundaryError("INVALID_RECORD", "turn_id가 비었다")
    return turn_id


def check_frontend_input(rec) -> dict:
    """FrontendInput 읽기 모드 확인: response_text(비지 않은 문자열|null), turn_failure_signal(객체|null)."""
    if not isinstance(rec, dict) or "response_text" not in rec or "turn_failure_signal" not in rec:
        raise integrity("FrontendInput 응답이 아니다")
    rt, sig = rec["response_text"], rec["turn_failure_signal"]
    if not (rt is None or (isinstance(rt, str) and rt)):
        raise integrity("response_text가 문자열이나 null이 아니다")
    if sig is not None and not (isinstance(sig, dict) and isinstance(sig.get("session_id"), str)
                                and isinstance(sig.get("write_committed"), str) and isinstance(sig.get("staff_alert"), str)):
        raise integrity("turn_failure_signal 형식이 아니다")
    return rec


class HttpPublicApi(HttpClientBase):
    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 10.0, device_id: Optional[str] = None):
        """2.3.0: 키오스크 기기 인증은 게이트웨이의 클라이언트 인증서(mTLS, ADR 0012)다. 게이트웨이를 거치면 token도 device_id도 주지 않는다.
        게이트웨이 뒤 내부망에서 서비스를 직접 부를 때(시험·운영 도구)는 device_id로 `X-Openit-Device`를 싣는다(서비스는 이 헤더를 믿는다).
        token(기기 토큰 Bearer)은 2.x 호환으로만 남고 3.0.0에서 없어진다."""
        super().__init__(base_url, token, timeout)
        if device_id is not None:
            if not _DEVICE_ID.match(device_id):
                raise ValueError("device_id 형식이 아니다")
            self._headers["X-Openit-Device"] = device_id

    def start_session(self, session_id: Optional[str] = None, subject_ref: Optional[str] = None) -> dict:
        """`POST /v1/sessions`. 첫 안내 문장이 든 FrontendInput. session_id는 생략한다: 서버가 발급해 응답에 돌려준다(D106, PUBLIC_API.md 7행).
        주는 것은 2.x 호환으로만 받는다."""
        body = {"kind": "SESSION_START"}
        if session_id is not None:
            body["session_id"] = _sid(session_id)
        if subject_ref is not None:
            if not isinstance(subject_ref, str) or not _SUBJECT_REF.match(subject_ref):
                raise BoundaryError("INVALID_RECORD", "subject_ref 형식이 아니다")
            body["subject_ref"] = subject_ref
        return check_frontend_input(self._json("POST", "/v1/sessions", body=body))

    def send_utterance(self, session_id: str, utterance: str, turn_id: str) -> dict:
        """`POST /v1/sessions/{id}/turns`. 응답을 받지 못한 재전송에만 같은 turn_id를 쓴다(멱등)."""
        if not isinstance(utterance, str):
            raise BoundaryError("INVALID_RECORD", "utterance가 문자열이 아니다")
        body = {"session_id": _sid(session_id), "kind": "UTTERANCE", "utterance": utterance, "turn_id": _turn(turn_id)}
        return check_frontend_input(self._json("POST", "/v1/sessions/" + self._q(session_id, "turns"), body=body))

    def end_session(self, session_id: str) -> dict:
        """`POST /v1/sessions/{id}/end`. response_text는 null일 수 있다."""
        body = {"session_id": _sid(session_id), "kind": "SESSION_END"}
        return check_frontend_input(self._json("POST", "/v1/sessions/" + self._q(session_id, "end"), body=body))

    def get_state(self, session_id: str) -> dict:
        """`GET /v1/sessions/{id}/state` -> SessionState (위험 정지 중 2초 간격 폴링)."""
        _sid(session_id)
        return self._record("/v1/sessions/" + self._q(session_id, "state"), "SessionState")

    def intervene(self, session_id: str, decision: str, turn_id: str) -> dict:
        """`POST /v1/sessions/{id}/intervention` (staff 토큰). decision은 RESUME|END."""
        if decision not in ("RESUME", "END"):
            raise BoundaryError("INVALID_RECORD", "decision은 RESUME 또는 END")
        body = {"session_id": _sid(session_id), "decision": decision, "turn_id": _turn(turn_id)}
        return check_frontend_input(self._json("POST", "/v1/sessions/" + self._q(session_id, "intervention"), body=body))

    def healthz(self) -> bool:
        """`GET /healthz`가 200이면 True. 못 닿으면 UNAVAILABLE."""
        self._json("GET", "/healthz")
        return True
