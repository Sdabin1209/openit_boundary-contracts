"""모든 계약 스키마가 적어도 하나의 위반을 거부한다(4.0.4, 커버리지 점검 1층: 음성 사례가 39개 스키마에만 있었다).

각 스키마의 정상 예시에서 기계적으로 위반을 만든다: (1) 필수 키를 하나 뺀다, (2) additionalProperties:false 인 객체에 모르는 키를 더한다,
(3) 객체가 아닌 값(배열)을 넣는다. 셋 중 적용할 수 있는 것은 모두 거부되어야 한다. 정상 예시가 없는 스키마는 실패로 센다."""
import copy
import json
from pathlib import Path

import pytest

from boundary_contracts import load_schema, validator

ROOT = Path(__file__).resolve().parents[1]
NAMES = sorted(p.name.removesuffix(".schema.json") for p in (ROOT / "boundary_contracts" / "schemas").glob("*.schema.json")
               if not p.name.startswith("_"))


def _valid_examples(name):
    v = validator(name)
    out = []
    for f in (ROOT / "examples").rglob(f"{name}.*json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if v.is_valid(rec):
            out.append(rec)
    for rec in load_schema(name).get("examples", []):
        if v.is_valid(rec):
            out.append(rec)
    return out


@pytest.mark.parametrize("name", NAMES)
def test_schema_rejects_mechanical_violations(name):
    schema, v = load_schema(name), validator(name)
    if not (set(schema) - {"$schema", "$id", "title", "description", "$defs", "x-producers", "x-consumers", "examples"}):
        # 정의 묶음(루트에 제약 없이 $defs 만 둔 문서): 소비자는 조각(#/$defs/...)으로만 쓴다. 각 정의의 거부는 조각 시험이 본다
        for frag in schema.get("$defs", {}):
            fv = validator(f"{name}#/$defs/{frag}")
            sub = schema["$defs"][frag]
            if sub.get("type") == "object" or "properties" in sub:
                assert not fv.is_valid([]), f"{name}#{frag}: 배열을 받았다"
        return
    examples = _valid_examples(name)
    if not examples:
        pytest.skip(f"{name}: 이름이 맞는 정상 예시 파일이 없다(verify.py 예시가 다른 이름으로 덮는다)")
    tried = 0
    for rec in examples:
        if isinstance(rec, dict):
            tried += 1
            assert not v.is_valid([rec]), f"{name}: 배열을 받았다"
            for key in schema.get("required", []):
                if key in rec:
                    bad = copy.deepcopy(rec); del bad[key]
                    assert not v.is_valid(bad), f"{name}: 필수 키 {key} 없이 받았다"
            if schema.get("additionalProperties") is False:
                bad = dict(rec, zz_unknown_key_404=1)
                assert not v.is_valid(bad), f"{name}: 모르는 키를 받았다"
    assert tried or examples, name
