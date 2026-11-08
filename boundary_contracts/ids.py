"""계약 식별자 함수(5.0.0). CONVENTIONS 10절 116행 '외부 식별자를 봉투에 넣을 때'의 정본 구현이다.

왜 패키지 함수인가: 4.x 까지 이 규칙은 문장뿐이라 생산자(survey-service)와 소비자(ops-feedback)가 각자 구현했고,
한쪽이 Id 패턴의 끝 줄바꿈 금지((?![\\s\\S]))를 빠뜨리거나 원본과 변환값을 다르게 비교해 Trace 가 거부됐다(2026-11-08 결함 #17·#23).
같은 뜻은 한 번만 정의한다(D117): 영역은 이 함수를 부르고 자기 사본을 두지 않는다. 적합성 벡터는 conformance/vectors/envelope_id.json.
"""
from __future__ import annotations

import hashlib
import re

from .schemas_api import load_schema

_ID_DEF = load_schema("_common")["$defs"]["Id"]
_ID_RE = re.compile(_ID_DEF["pattern"])   # 패턴은 스키마에서 읽는다(사본 금지)
_ID_MIN = _ID_DEF.get("minLength", 1)
_ID_MAX = _ID_DEF["maxLength"]
ENVELOPE_PREFIX = "x-"
ENVELOPE_HEX_LEN = 32   # CONVENTIONS 116행: SHA-256 앞 32자(소문자 16진). 128비트면 세션·턴 수에서 충돌을 무시할 수 있다


def is_id(value: str) -> bool:
    """value 가 계약 Id(_common.$defs.Id) 형식이면 True. 길이는 JSON Schema 처럼 코드 포인트 수로 센다."""
    return isinstance(value, str) and _ID_MIN <= len(value) <= _ID_MAX and _ID_RE.search(value) is not None


def envelope_id(raw: str) -> str:
    """바깥이 정한 식별자를 봉투(TraceEnvelope 등)의 Id 로 바꾼다. Id 형식이면 그대로, 아니면
    'x-' + 원본 UTF-8 바이트의 SHA-256 앞 32자(소문자 16진). 결정적이라 같은 원본은 같은 값이다(멱등).
    빈 문자열도 Id 가 아니므로 변환한다. 문자열이 아니면 TypeError(계약 위반은 호출자의 결함이다)."""
    if not isinstance(raw, str):
        raise TypeError("envelope_id 는 문자열만 받는다")
    if is_id(raw):
        return raw
    return ENVELOPE_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:ENVELOPE_HEX_LEN]
