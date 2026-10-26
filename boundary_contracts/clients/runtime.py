"""I9 ModelRuntime 추론 서버의 HTTP 클라이언트(HTTP.md I9, 계약 2.0.0).

LoRA-A는 `extract`(ActionExtractionInput -> ActionExtraction, JSON), LoRA-B는 `respond`(ResponseRequest -> 응답 문장, text/plain)다.
ActionExtraction과 ResponseText는 레코드가 아니라 모델 출력이므로 버전·ext가 없고, 읽기 모드 완화 없이 엄격하게 검증한다.
"""
from __future__ import annotations

import json
import re
from typing import NamedTuple, Optional

from ._http import HttpClientBase, _validator, check_id, check_outgoing, check_record, integrity

OUTCOME_HEADER = "X-Openit-Outcome"
_PROTECTION = re.compile(r"^[A-Za-z][A-Za-z0-9_]*:[0-9]+(,[A-Za-z][A-Za-z0-9_]*:[0-9]+)*$")


class RuntimeResult(NamedTuple):
    """output: extract는 ActionExtraction(dict), respond는 응답 문장(str).
    outcome: X-Openit-Outcome 값. extract는 항상 'ok', respond는 'ok' 또는 'fallback'(서버가 대체 문장을 냈다).
    attempts: X-Openit-Attempts(없으면 None). protections: X-Openit-Protections를 {규칙 코드: 건수}로 푼 것."""
    output: object
    outcome: str
    attempts: Optional[int]
    protections: dict

    @property
    def is_fallback(self) -> bool:
        return self.outcome != "ok"


class HttpModelRuntime(HttpClientBase):
    # ---- 릴리스 적재 ----
    def load_release(self, release_id: str) -> dict:
        """PUT /v1/releases/{id}. 멱등. 200 LOADED 또는 202 LOADING의 본문을 그대로 돌려준다."""
        return self._state(self._json("PUT", "/v1/releases/" + self._q(check_id(release_id, "release_id"))), release_id)

    def get_release_state(self, release_id: str) -> dict:
        return self._state(self._json("GET", "/v1/releases/" + self._q(check_id(release_id, "release_id"))), release_id)

    @staticmethod
    def _state(body, release_id: str) -> dict:
        if (not isinstance(body, dict) or body.get("release_id") != release_id
                or body.get("state") not in ("ABSENT", "LOADING", "LOADED", "FAILED")):
            raise integrity("적재 상태 응답이 형식에 맞지 않는다")
        err = body.get("error")
        if err is not None:
            check_record("BoundaryError", err)
        return body

    def info(self) -> dict:
        body = self._json("GET", "/v1/info")
        if not isinstance(body, dict) or not isinstance(body.get("loaded"), list):
            raise integrity("info 응답이 형식에 맞지 않는다")
        return body

    # ---- 추론 ----
    def extract(self, release_id: str, request: dict) -> RuntimeResult:
        """LoRA-A. 입력은 ActionExtractionInput. 출력은 ActionExtraction이며 서버가 형식 검증을 마친 것이다.
        모델 출력이 끝내 깨지면 서버는 대체 출력을 만들지 않고 UNAVAILABLE(details.reason=OUTPUT_INVALID)을 낸다."""
        check_outgoing("ActionExtractionInput", request)
        resp = self._open("POST", self._infer_path(release_id, "extract"), None, self._dump(request),
                          "application/json", "application/json")
        status, headers, raw = resp.status, resp.headers, self._read(resp, self.max_body_bytes)
        out = self._parse_json(raw, status)
        errs = list(_validator("ActionExtraction").iter_errors(out))
        if errs:
            raise integrity("ActionExtraction 응답이 스키마를 위반한다", reason=errs[0].message[:200])
        return self._result(out, headers, allowed=("ok",))

    def respond(self, release_id: str, request: dict) -> RuntimeResult:
        """LoRA-B. 입력은 ResponseRequest. 출력은 응답 문장(text/plain). 대체 문장이면 outcome이 'fallback'이다."""
        check_outgoing("ResponseRequest", request)
        resp = self._open("POST", self._infer_path(release_id, "respond"), None, self._dump(request),
                          "application/json", "text/plain")
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        headers, raw = resp.headers, self._read(resp, self.max_body_bytes)
        if ctype != "text/plain":
            raise integrity("respond 응답이 text/plain이 아니다", content_type=ctype[:60])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise integrity("respond 응답이 UTF-8이 아니다") from None
        if list(_validator("ResponseText").iter_errors(text)):
            raise integrity("ResponseText 응답이 비어 있다")
        return self._result(text, headers, allowed=("ok", "fallback"))

    # ---- 내부 ----
    def _infer_path(self, release_id: str, op: str) -> str:
        return "/v1/releases/" + self._q(check_id(release_id, "release_id"), op)

    @staticmethod
    def _dump(obj) -> bytes:
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")

    def _parse_json(self, raw: bytes, status: int):
        try:
            return json.loads(raw)
        except ValueError:
            raise self._unavailable("JSON이 아닌 응답", status=status) from None

    @staticmethod
    def _result(output, headers, *, allowed: tuple) -> RuntimeResult:
        outcome = headers.get(OUTCOME_HEADER)
        if outcome not in allowed:
            raise integrity(f"{OUTCOME_HEADER} 헤더가 없거나 값이 허용 밖이다", value=str(outcome)[:30])
        attempts = headers.get("X-Openit-Attempts")
        try:
            n = None if attempts is None else int(attempts)
            if n is not None and n < 1:
                raise ValueError
        except ValueError:
            raise integrity("X-Openit-Attempts 헤더가 양의 정수가 아니다") from None
        prot_raw = headers.get("X-Openit-Protections")
        prot: dict = {}
        if prot_raw:
            if not _PROTECTION.match(prot_raw):
                raise integrity("X-Openit-Protections 헤더 형식이 맞지 않는다")
            for part in prot_raw.split(","):
                code, cnt = part.split(":")
                prot[code] = prot.get(code, 0) + int(cnt)
        return RuntimeResult(output, outcome, n, prot)
