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


# ---------------------------------------------------------------- 2.4.0 값 규칙(U32·U33)
_FLOW_ACTIONS = ("NEXT", "CORRECT", "HOLD", "SKIP")


def _is_type(value, data_type: str, options) -> bool:
    if data_type == "boolean":
        return isinstance(value, bool)
    if data_type == "option":
        return isinstance(value, str) and (not options or value in options)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return data_type == "number" or float(value).is_integer()


def _key(item: str, field: str, kind: str = "") -> str:
    return f"{item}[{kind}].{field}" if kind else f"{item}.{field}"


def _kind_of(key: str) -> str:
    m = re.search(r"\[([^\]]*)\]", key)
    return m.group(1) if m else ""


def apply_value_rules(input: dict, output: dict, fields: dict, flow: dict | None = None,
                      rules: dict | None = None) -> tuple[dict, list[Violation], list[str]]:
    """칸 규격(QuestionFieldSpec)과 값 규칙(rules.value_rules)을 출력에 적용한다.

    돌려주는 것: (바뀐 출력, 바꿀 수 없는 위반 목록, 적용한 규칙 사유 목록).
    규칙에 걸리면 데이터셋 정규화기가 같은 상황에서 낸 정답 모양으로 바꾼다(D74: 서비스를 데이터셋에 맞춘다).
    값을 맞히지 않는다: 범위 밖 값은 버리고(value null) 다시 묻고, 충돌은 환자에게 확인한다.
    데이터셋에 정답이 없는 위반(자료형 불일치, 최소값 미만)은 바꾸지 않고 위반으로 돌려준다(호출자는 OUTPUT_INVALID).
    """
    rules = rules or load_rules()
    vr = rules.get("value_rules")
    out = json.loads(json.dumps(output))  # 깊은 사본: 받은 출력을 고치지 않는다
    if not vr or not isinstance(out.get("values"), list):
        return out, [], []
    spec = {f["slot"]: f for f in fields.get("fields", [])}
    qid = input["question_id"]
    vals = out["values"]
    view = {k: s.get("value") for k, s in (input.get("state") or {}).items() if isinstance(s, dict)}
    for v in vals:
        if v.get("save") is True and isinstance(v.get("key"), str):
            view[v["key"]] = v.get("value")

    def entry(key):
        for v in vals:
            if v.get("key") == key:
                return v
        v = {"key": key, "value": view.get(key), "status": "ANSWERED", "save": True}
        vals.append(v)  # 상태(이전 턴)에만 있던 칸을 대상으로 삼을 때는 출력에 칸을 더한다(정규화기와 같음)
        return v

    def unclear(key):
        e = entry(key)
        e.update(value=None, status="UNCLEAR", save=False, precision="unspecified")

    def conflict(key):
        e = entry(key)
        e.update(status="CONFLICT", save=False)

    def finish(rewrite, targets, next_item):
        out.update(action=rewrite["action"], reason=rewrite["reason"], targets=targets, next_item=next_item)
        return out, [], [rewrite["reason"]]

    # 1) 자료형·범위(정규화기 _store: DB 정의로 타입·범위 검증)
    viol, above = [], []
    am = vr["above_maximum"]
    for i, v in enumerate(vals):
        k = v.get("key")
        if v.get("save") is not True or not isinstance(k, str) or v.get("value") is None:
            continue
        f = spec.get(slot_of(k))
        if f is None:
            continue
        x = v["value"]
        if not _is_type(x, f["data_type"], f.get("options")):
            viol.append(Violation(vr["type_mismatch_code"], f"values/{i}/value", "값이 칸 자료형과 다르다"))
            continue
        if f["data_type"] in ("integer", "number"):
            if ("minimum" in f and x < f["minimum"]) or ("exclusive_minimum" in f and x <= f["exclusive_minimum"]):
                viol.append(Violation(vr["below_minimum_code"], f"values/{i}/value", "값이 칸 최소값보다 작다"))
                continue
            mx = f.get("maximum", am["unit_maximum"].get(f.get("unit", "")))
            if mx is not None and x > mx:
                above.append(k)
    if viol:
        return out, viol, []
    if above:
        for k in above:
            unclear(k)
        return finish(am["rewrite"], above, qid)

    # 2) R2 기간보다 많은 횟수(정규화기 R2, PERIOD_MAX)
    ce = vr["count_exceeds_days"]
    freq, unit = view.get(ce["frequency_slot"]), view.get(ce["unit_slot"])
    if isinstance(freq, (int, float)) and not isinstance(freq, bool) and unit in ce["period_max"] and freq > ce["period_max"][unit]:
        ks = [ce["frequency_slot"], ce["unit_slot"]]
        for k in ks:
            unclear(k)
        return finish(ce["rewrite"], ks, qid)

    # 3) R1 술을 안 마신다면서 횟수·양이 있음(정규화기 R1)
    dn = vr["does_not_drink"]
    if view.get(dn["flag_slot"]) is True:
        if view.get(dn["frequency_slot"]):  # 횟수가 있으면 충돌로 묻지 않고 '마심'으로 고친다(정규화기 set_value(..., False, "R1"))
            e = entry(dn["flag_slot"])
            e.update(value=False, status="CORRECTION", save=True, precision="approximate")
            view[dn["flag_slot"]] = False
            if flow is not None and out.get("action") in _FLOW_ACTIONS:
                fl = _Flow(flow)
                keys = [v["key"] for v in vals if isinstance(v.get("key"), str)]
                saved = {slot_of(v["key"]): v.get("value") for v in vals if v.get("save") is True and isinstance(v.get("key"), str)}
                base = max((item_of(k) for k in keys if fl.index(item_of(k)) is not None), key=fl.order.index, default=qid)
                out["next_item"] = fl.next_item(base, saved)
            return out, [], ["R1_CORRECTED"]
        amounts = [k for k in view if item_of(k) in dn["amount_items"] and slot_of(k).endswith("." + dn["amount_field"])]
        if amounts:
            ks = [dn["flag_slot"]]
            for k in amounts:
                ks += [k, _key(item_of(k), dn["unit_field"], _kind_of(k))]
            for k in ks:
                conflict(k)
            return finish(dn["rewrite"], ks, item_of(dn["flag_slot"]))

    # 4) R3 최대 음주량 < 평소 음주량(정규화기 R3, 단위가 달라도 mL로 비교)
    mb = vr["max_below_usual"]

    def ml(item, kind):
        a, u = view.get(_key(item, mb["amount_field"], kind)), view.get(_key(item, mb["unit_field"], kind))
        if a is None or u is None or isinstance(a, bool):
            return None
        per = mb["per_unit_ml"].get(u, mb["volume_ml"].get(kind, {}).get(u))
        return None if per is None else a * per

    ks = []
    for v in vals:
        k = v.get("key")
        if v.get("save") is True and isinstance(k, str) and item_of(k) == mb["max_item"] and slot_of(k).endswith("." + mb["amount_field"]):
            kind = _kind_of(k)
            usual, most = ml(mb["usual_item"], kind), ml(mb["max_item"], kind)
            if usual is not None and most is not None and most < usual:
                ks += [k, _key(mb["max_item"], mb["unit_field"], kind)]
    if ks:
        for k in ks:
            conflict(k)
        return finish(mb["rewrite"], ks, mb["max_item"])
    return out, [], []
