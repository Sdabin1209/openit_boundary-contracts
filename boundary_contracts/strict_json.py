"""계약 JSON 공통 규칙(5.0.0, CONVENTIONS 1절 'JSON 값의 범위'): I-JSON(RFC 7493) + 깊이·노드·바이트 예산.

왜 패키지에 두나: 같은 규칙을 영역마다 구현하면 경계값이 갈린다(D117). link(영역 통신 기반)의 _strict_json 은 0.3.0 부터
I-JSON·깊이 64 를 지켰지만 그 밖의 입구·잡·파일 읽기는 각자였고, 깊은 입력에서 재귀 한도(RecursionError)로 500 이 날 수 있었다
(2026-11-08 결함 대장 #10, release-gate rollback ext 가설). 이 모듈이 정본이고, 어기면 BoundaryError INVALID_RECORD 다.

깊이를 세는 법: 루트 객체·배열이 1, 그 안의 객체·배열마다 1 을 더한다. 스칼라(문자열·수·참거짓·null)는 세지 않는다.
예: {} = 1, {"a": [1]} = 2, 스칼라 하나만 있는 본문 = 0.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .errors import BoundaryError

# 근거: link 0.3.0 openit_link/server.py 의 max_json_depth=64 와 _bracket_depth(루트 괄호=1) 사전 검사. 그 값을 계약으로 올렸다(측정값 아님, 설계 상한).
MAX_JSON_DEPTH = 64
# 근거: link DEFAULT_MAX_BODY = 1 MiB(계약 요청 본문 레코드 하나의 상한, 설계 판단). 큰 본문(패키지 tar 등 바이너리)은 이 규칙의 대상이 아니다.
MAX_JSON_BYTES = 1 * 2**20
# 근거: 바이트 예산에서 나온다. 값 하나는 구분자를 포함해 최소 2바이트("0,")이므로 1 MiB 본문의 값 수는 2**19 를 넘을 수 없다.
# 바이트가 없는 파이썬 객체 진입점(check_json_value)도 같은 예산을 쓴다.
MAX_JSON_NODES = 2**19
# 근거: I-JSON(RFC 7493) 2.2 — IEEE 754 배정밀도로 정확한 정수 범위. canonical(RFC 8785) 과 같은 값.
MAX_SAFE_INT = 2**53


def _bad(msg: str) -> BoundaryError:
    return BoundaryError("INVALID_RECORD", msg)


def check_json_value(value: Any, *, max_depth: int = MAX_JSON_DEPTH, max_nodes: int = MAX_JSON_NODES) -> None:
    """파이썬 값이 계약 JSON 규칙을 지키는지 반복 순회로 본다(재귀 없음). 어기면 BoundaryError(INVALID_RECORD).
    규칙: 타입은 dict·list·str·int·float·bool·None, 키는 문자열, 수는 유한하고 정수는 ±2**53 이내, 문자열에 짝 없는 서로게이트 없음,
    깊이 ≤ max_depth, 값 수 ≤ max_nodes."""
    stack = [(value, 0)]
    nodes = 0
    while stack:
        v, d = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise _bad(f"JSON 값이 너무 많다(상한 {max_nodes})")
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, int):
            if abs(v) > MAX_SAFE_INT:
                raise _bad("정수가 I-JSON 범위(±2**53)를 벗어난다")
            continue
        if isinstance(v, float):
            if not math.isfinite(v):
                raise _bad("NaN·무한대는 JSON 값이 아니다(I-JSON)")
            continue
        if isinstance(v, str):
            _check_str(v)
            continue
        if isinstance(v, (dict, list, tuple)):
            if d + 1 > max_depth:
                raise _bad(f"중첩이 너무 깊다(상한 {max_depth})")
            if isinstance(v, dict):
                for k, x in v.items():
                    if not isinstance(k, str):
                        raise _bad("객체의 키는 문자열이어야 한다")
                    _check_str(k)
                    stack.append((x, d + 1))
            else:
                stack.extend((x, d + 1) for x in v)
            continue
        raise _bad(f"JSON 으로 표현할 수 없는 타입: {type(v).__name__}")


def _check_str(s: str) -> None:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise _bad("짝 없는 서로게이트가 있는 문자열(I-JSON 2.1)") from None


def _bracket_depth(text: str) -> int:
    """문자열 밖 괄호 깊이(재귀 없음). json.loads 가 깊은 입력에서 RecursionError 로 죽기 전에 거른다."""
    d = m = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            d += 1
            if d > m:
                m = d
        elif ch in "]}":
            d -= 1
    return m


def _no_dup(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"중복 키 {k[:40]!r}(I-JSON 2.3)")
        out[k] = v
    return out


def _reject_constant(name):
    raise ValueError(f"{name} 는 JSON 값이 아니다(I-JSON)")


def _finite_float(s: str) -> float:
    f = float(s)
    if not math.isfinite(f):
        raise ValueError("배정밀도로 표현할 수 없는 수(오버플로, I-JSON 2.2)")
    return f


def loads(raw: bytes | str, *, max_depth: int = MAX_JSON_DEPTH, max_bytes: int = MAX_JSON_BYTES, max_nodes: int = MAX_JSON_NODES) -> Any:
    """계약 JSON 엄격 디코더. UTF-8, 중복 키·NaN·Infinity·오버플로 수(1e999)·짝 없는 서로게이트 거부, 깊이·노드·바이트 예산.
    어기면 BoundaryError(INVALID_RECORD). 깊은 입력도 재귀 한도로 죽지 않는다(괄호 깊이를 먼저 센다)."""
    try:
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        if len(data) > max_bytes:
            raise _bad(f"JSON 본문이 너무 크다(상한 {max_bytes}바이트)")
        text = data.decode("utf-8")
        if _bracket_depth(text) > max_depth:
            raise _bad(f"중첩이 너무 깊다(상한 {max_depth})")
        obj = json.loads(text, object_pairs_hook=_no_dup, parse_constant=_reject_constant, parse_float=_finite_float)
    except BoundaryError:
        raise
    except (ValueError, UnicodeError, RecursionError) as e:
        raise _bad(f"올바른 계약 JSON 이 아니다: {str(e)[:120]}") from None
    check_json_value(obj, max_depth=max_depth, max_nodes=max_nodes)
    return obj


def dumps(value: Any, **kw) -> str:
    """계약 JSON 직렬화: 먼저 check_json_value, 그다음 allow_nan=False 로(NaN·Infinity 를 쓰지 않는다)."""
    check_json_value(value)
    kw.setdefault("ensure_ascii", False)
    return json.dumps(value, allow_nan=False, **kw)
