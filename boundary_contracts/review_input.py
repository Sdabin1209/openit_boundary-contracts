"""사람이 쓰는 실패 사례 검토 값의 계약 검사(5.0.0). 규칙 데이터: data/review_input_rules.json.

왜 계약에 두나: 4.x 에서 ops-feedback review_decider 만 개인정보 패턴·문자열 길이·깊이로 거부해, 계약(CaseReviewRequest)이 받는다고 한 값을
코드가 따로 거부했다(D117 위반, 결함 대장 #10). 같은 기준을 사람 입구(admin-console 미리 검사 포함)와 ops-feedback 이 함께 쓰도록 여기에 둔다.
저장된 환자 발화 원문과 비교하는 거부는 원문을 가진 ops-feedback 만 할 수 있어 함수가 아니라 판정 기준으로 INTERFACES.md 에 선언한다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .strict_json import check_json_value

_LOCAL = re.compile(r"[A-Za-z0-9._%+-]")
_TAIL = re.compile(r"[A-Za-z0-9.-]*")


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads((Path(__file__).resolve().parent / "data/review_input_rules.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _patterns():
    return {n: re.compile(p) for n, p in rules()["patterns"].items()}


def has_email(s: str) -> bool:
    """'@' 위치마다 앞 문자 하나와 뒤 도메인 문자 구간만 본다(입력 길이에 선형)."""
    i = s.find("@")
    while i != -1:
        if i > 0 and _LOCAL.match(s[i - 1]):
            dom = _TAIL.match(s, i + 1).group(0)
            k = dom.rfind(".")
            while k != -1:
                tld = dom[k + 1:k + 3]
                if k >= 1 and len(tld) == 2 and tld.isascii() and tld.isalpha():
                    return True
                k = dom.rfind(".", 0, k)
        i = s.find("@", i + 1)
    return False


def _strings(value: Any):
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            stack.extend(v.keys()); stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)


def review_value_problems(value: Any) -> list[str]:
    """검토 값의 위반 이름 목록(빈 목록 = 통과). 값 자체는 싣지 않는다(개인정보일 수 있다).
    순서: 계약 JSON 공통 규칙(깊이 64 등) → 문자열 길이 → 개인정보 패턴."""
    check_json_value(value)
    out: list[str] = []
    limit = rules()["max_string_length"]
    for s in _strings(value):
        if len(s) > limit:
            out.append(f"string_too_long>{limit}")
            continue
        if has_email(s):
            out.append("email")
        for name, rx in _patterns().items():
            if rx.search(s):
                out.append(name)
    return sorted(set(out))
