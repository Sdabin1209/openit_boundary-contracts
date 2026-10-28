"""LoRA-A 출력(ActionExtraction)의 의미 규칙 기준 검사기(ADR 0010, D104). 순수 함수. I/O·시간·난수 없음.

규칙은 `data/action_extraction_rules.json`(데이터)이 정하고, 이 모듈은 그 데이터를 읽어 적용하는 해석기 하나다.
형식(스키마) 검사는 ActionExtraction 스키마가 한다. 여기서는 스키마로 표현할 수 없는 규칙만 본다.
검사기를 부르는 쪽은 LoRA-A 컴포넌트(model-runtime) 하나다. 통과한 값은 다른 컴포넌트가 다시 검사하지 않는다(R7).
문항 순서 표(flow)는 문진 스키마 `QuestionFlow`의 모양(order, skips)을 그대로 받는다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from .errors import BoundaryError
from .schemas_api import validator

# 왜 이 파일: 규칙은 코드가 아니라 데이터여야 한다는 사용자 결정(D104). 해석기가 바뀌지 않는 한 규칙만 고쳐 버전을 올린다.
_RULES_PATH = Path(__file__).resolve().parent / "data" / "action_extraction_rules.json"


class Violation(NamedTuple):
    code: str
    path: str
    message: str  # 입력·출력의 값을 싣지 않는다(개인정보)


@lru_cache(maxsize=1)
def load_rules() -> dict:
    rules = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    errs = list(validator("ActionExtractionRules").iter_errors(rules))
    if errs:
        raise BoundaryError("INTEGRITY_ERROR", "action_extraction_rules.json이 ActionExtractionRules 스키마를 어긴다")
    return rules


def item_of(key: str) -> str:
    """모델 키(`Q7[soju].amount`, `Q4_1.status`)의 문항 ID."""
    return key.rsplit(".", 1)[0].split("[")[0]


def slot_of(key: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", key)


def _same(a, b) -> bool:
    """bool과 수를 구분한다(True != 1)."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


class _Flow:
    def __init__(self, flow: dict):
        self.order = list(flow["order"])
        self.skips = list(flow.get("skips", []))
        self._pos = {q: i for i, q in enumerate(self.order)}

    def index(self, item):
        return self._pos.get(item)

    def _skipped(self, item, saved):
        return any(s["skip_item"] == item and s["slot"] in saved and _same(saved[s["slot"]], s["value"]) for s in self.skips)

    def next_item(self, after, saved):
        i = self._pos[after] + 1
        while i < len(self.order) and self._skipped(self.order[i], saved):
            i += 1
        return self.order[i] if i < len(self.order) else "END"

    def plain_next(self, after):
        i = self._pos[after] + 1
        return self.order[i] if i < len(self.order) else "END"


def check_action_extraction(input: dict, output: dict, flow: dict, rules: dict | None = None) -> list[Violation]:
    """출력의 규칙 위반 목록(없으면 빈 목록). 입력이 ActionExtractionInput을 어기면 BoundaryError(INVALID_RECORD)."""
    rules = rules or load_rules()
    errs = list(validator("ActionExtractionInput").iter_errors(input))
    if errs:
        raise BoundaryError("INVALID_RECORD", "ActionExtractionInput을 어긴 입력")
    fl = _Flow(flow)
    out: list[Violation] = []
    values = output.get("values") if isinstance(output, dict) else None
    if not isinstance(values, list) or not all(isinstance(v, dict) for v in values) or not isinstance(output.get("action"), str):
        return [Violation("OUTPUT_SCHEMA", "(root)", "출력 구조가 ActionExtraction이 아니다")]

    sr = rules["save_rule"]
    saved_st = rules["statuses"]["saved"]
    null_st = rules["statuses"]["null"]
    keys = []
    for i, v in enumerate(values):
        k, st = v.get("key"), v.get("status")
        keys.append(k if isinstance(k, str) else "")
        want_save = st in saved_st
        if v.get("save") is not want_save:
            out.append(Violation(sr["code"], f"values/{i}/save", "save는 status가 저장 상태일 때만 true"))
        if st in null_st and v.get("value") is not None:
            out.append(Violation(sr["code"], f"values/{i}/value", "값이 없는 status이면 value는 null"))
        if want_save and sr["saved_value_non_null"] and v.get("value") is None:
            out.append(Violation(sr["code"], f"values/{i}/value", "저장하는 값은 null일 수 없다"))

    keyset = set(keys)
    targets = output.get("targets") or []
    if not isinstance(targets, list):
        targets = []
    if rules["targets"]["each_target_is_a_values_key"]:
        for i, t in enumerate(targets):
            if t not in keyset:
                out.append(Violation(rules["targets"]["code"], f"targets/{i}", "targets 항목이 values의 key에 없다"))

    action, nxt, qid = output["action"], output.get("next_item"), input["question_id"]
    if not isinstance(nxt, str):
        return out
    ui = rules["unknown_item"]
    all_keys = [k for k in keys if k] + [t for t in targets if isinstance(t, str)]
    unknown = set()
    if "values.key" in ui["every_item_in_flow"] or "targets" in ui["every_item_in_flow"]:
        unknown |= {item_of(k) for k in all_keys if fl.index(item_of(k)) is None}
    if "input.question_id" in ui["every_item_in_flow"] and fl.index(qid) is None:
        unknown.add(qid)
    if unknown:
        out.append(Violation(ui["code"], "values", f"문항 순서 표에 없는 문항 {len(unknown)}개"))
        return out
    if "next_item" in ui["every_item_in_flow"] and nxt != ui["end_marker"] and fl.index(nxt) is None:
        out.append(Violation(ui["code"], "next_item", "next_item이 문항 순서 표에 없다"))
        return out

    ni = rules["next_item"]
    for rule in ni["by_action"]:
        if action not in rule["actions"]:
            continue
        kind = rule["next_item_is"]
        if kind == "input.question_id":
            if nxt != qid:
                out.append(Violation(ni["mismatch_code"], "next_item", f"{action}의 next_item은 입력 question_id와 같아야 한다"))
        elif kind == "item_of_targets":
            if nxt not in {item_of(t) for t in targets if isinstance(t, str)}:
                out.append(Violation(ni["mismatch_code"], "next_item", f"{action}의 next_item은 targets 칸의 문항이어야 한다"))
        elif kind == "flow_next":
            saved = {slot_of(k): v.get("value") for k, v in zip(keys, values) if v.get("save") is True and k}
            base = max((item_of(k) for k in all_keys), key=fl.order.index) if all_keys else qid
            if nxt != fl.next_item(base, saved):
                if rule.get("also_allowed") == "item_of_values" and nxt in {item_of(k) for k in keys if k}:
                    pass
                else:
                    plain = fl.plain_next(base)
                    pos = len(fl.order) if nxt == ui["end_marker"] else fl.index(nxt)
                    pplain = len(fl.order) if plain == ui["end_marker"] else fl.index(plain)
                    out.append(Violation(ni["skip_order_code"] if pos >= pplain else ni["mismatch_code"], "next_item",
                                         f"{action}의 next_item이 문항 순서·건너뛰기 규칙과 다르다"))
        break
    return out
