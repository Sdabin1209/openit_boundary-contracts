"""모든 계약 스키마(와 정의 묶음의 조각)가 기계적으로 만든 위반을 거부한다(4.0.5, 커버리지 점검 1층·교차검증).

정상 값에서 그 자리에 적용할 수 있는 위반을 모두 만든다:
- 타입 반전: 선언한 type 밖의 JSON 값(null·정수·문자열·배열·객체·불리언 중 type 에 없는 것) — 하나라도 있으면 모두 거부되어야 한다
- 빈 문자열(minLength > 0), 빈 배열(minItems > 0), 열거 밖 문자열(enum)
- 객체: 필수 키 하나 빼기, additionalProperties:false 에 모르는 키 더하기
만든 위반이 0건이면 실패다(검사한 척 통과하지 않는다). 정상 값이 없으면 실패다.
정의 묶음(루트에 제약 없이 $defs 만 둔 문서)은 조각마다 같은 규칙으로 보되, `$ref` 하나뿐인 조각은 가리키는 정의의 시험이 덮는다."""
import copy
import json
from pathlib import Path

import pytest

from boundary_contracts import load_schema, validator

ROOT = Path(__file__).resolve().parents[1]
NAMES = sorted(p.name.removesuffix(".schema.json") for p in (ROOT / "boundary_contracts" / "schemas").glob("*.schema.json")
               if not p.name.startswith("_"))
META = {"$schema", "$id", "title", "description", "$defs", "x-producers", "x-consumers", "examples", "x-note", "$comment"}
SAMPLES = {"null": None, "integer": 7, "string": "zz", "array": [], "object": {}, "boolean": True}


def _json_type(v):
    return ("null" if v is None else "boolean" if isinstance(v, bool) else "integer" if isinstance(v, int)
            else "number" if isinstance(v, float) else "string" if isinstance(v, str) else "array" if isinstance(v, list) else "object")


def _mutations(schema: dict, value):
    out = []
    declared = schema.get("type")
    if declared is not None:
        allowed = {declared} if isinstance(declared, str) else set(declared)
        if "number" in allowed:
            allowed |= {"integer"}
        out += [("type:" + t, v) for t, v in SAMPLES.items() if t not in allowed]
    if isinstance(value, str) and schema.get("minLength", 0) > 0:
        out.append(("minLength", ""))
    if isinstance(value, list) and schema.get("minItems", 0) > 0:
        out.append(("minItems", []))
    enum = schema.get("enum")
    if isinstance(enum, list) and enum and all(isinstance(x, str) for x in enum):
        out.append(("enum", "ZZ_NOT_IN_ENUM_405"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key in value:
                bad = copy.deepcopy(value); del bad[key]
                out.append(("required:" + key, bad))
        if schema.get("additionalProperties") is False:
            out.append(("additionalProperties", dict(value, zz_unknown_key_405=1)))
    return out


def _examples(name):
    v = validator(name)
    found = []
    for f in sorted((ROOT / "examples").rglob(f"{name}.*json")) + sorted((ROOT / "examples").rglob(f"{name}.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if v.is_valid(rec):
            found.append(rec)
    found += [r for r in load_schema(name).get("examples", []) if v.is_valid(r)]
    return found


def _is_bundle(schema):
    return not (set(schema) - META)


def _check(target_name, schema, validator_, values):
    tried = 0
    for value in values:
        for label, bad in _mutations(schema, value):
            assert not validator_.is_valid(bad), f"{target_name}: 위반({label})을 받았다: {json.dumps(bad, ensure_ascii=False)[:120]}"
            tried += 1
        if "type" not in schema:
            # 루트에 type 이 없고 anyOf/oneOf 등으로 모양을 정한 스키마(예: HttpWire): 정상 값과 다른 JSON 타입 중 적어도 하나는 거부해야 한다
            others = [v for t, v in SAMPLES.items() if t != _json_type(value) and not (t == "integer" and _json_type(value) == "number")]
            rejected = [v for v in others if not validator_.is_valid(v)]
            assert rejected, f"{target_name}: 정상 값과 다른 타입을 모두 받았다(제약 없는 스키마)"
            tried += len(rejected)
    return tried


@pytest.mark.parametrize("name", NAMES)
def test_schema_rejects_mechanical_violations(name):
    schema = load_schema(name)
    if _is_bundle(schema):
        checked = 0
        for frag, sub in schema.get("$defs", {}).items():
            if set(sub) <= {"$ref", "description", "$comment"}:
                continue      # $ref 하나뿐인 조각은 가리키는 정의의 시험이 덮는다
            fv = validator(f"{name}#/$defs/{frag}")
            values = [r for r in sub.get("examples", []) if fv.is_valid(r)]
            if not values:   # 조각에 예시가 없으면 타입 반전만 본다(값 없이도 만들 수 있는 위반)
                values = [None] if "type" not in sub else [SAMPLES.get(sub["type"] if isinstance(sub["type"], str) else sub["type"][0])]
            n = _check(f"{name}#{frag}", sub, fv, values)
            assert n > 0, f"{name}#/$defs/{frag}: 만들 수 있는 위반이 없다(제약 없는 조각인지 확인하고 분류할 것)"
            checked += 1
        assert checked > 0 or not schema.get("$defs"), f"{name}: 검사한 조각이 없다"
        return
    values = _examples(name)
    assert values, f"{name}: 이름이 맞는 정상 예시가 없다(음성 사례를 만들 수 없다)"
    n = _check(name, schema, validator(name), values)
    assert n > 0, f"{name}: 정상 예시에서 만들 수 있는 위반이 0건이다(type·required·enum·minLength 등 제약이 루트에 없는지 확인할 것)"
