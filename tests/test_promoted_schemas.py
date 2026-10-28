"""영역이 올린 경계 스키마(D107)의 계약 시험.
통과 예시(conformance/examples)는 통과하고, 거부 예시(conformance/examples_invalid)는 거부되며, 스키마마다 둘 다 있다.
예시 이름 규칙: `<스키마>[.<$defs 이름>][.<변형>].json`. 스키마 루트에 type이 없는 묶음 스키마는 두 번째 조각이 $defs 이름이면 그것으로 검증한다.
이 시험은 '영역이 낸 예시와 스키마가 서로 맞는다'를 본다. 이웃 영역이 실제로 그 모양을 읽고 쓰는지는 확인하지 않는다.
"""
import json
import unittest
from pathlib import Path

import jsonschema

from boundary_contracts import load_schema, schema_dir, validator

ROOT = Path(__file__).resolve().parent.parent / "conformance"
PROMOTED = sorted(json.loads(p.read_text(encoding="utf-8")) and p.name.split(".")[0] for p in (ROOT / "promoted").glob("*.MANIFEST.json"))


def _entries(m):
    for k in ("entries", "items", "schemas"):
        if isinstance(m.get(k), list):
            yield from m[k]


def _names():
    out = set()
    for p in (ROOT / "promoted").glob("*.MANIFEST.json"):
        out |= {e["name"] for e in _entries(json.loads(p.read_text(encoding="utf-8")))}
    return out


def _check(stem):
    parts = stem.split(".")
    name = parts[0]
    schema = load_schema(name)
    if len(parts) > 1 and "type" not in schema and parts[1] in schema.get("$defs", {}):
        v = validator(name)
        sub = {"$ref": f"#/$defs/{parts[1]}"}
        return jsonschema.Draft202012Validator({**{k: schema[k] for k in ("$defs",)}, **sub}, resolver=v.resolver)
    return validator(name)


def _errors(stem, doc):
    errs = list(_check(stem).iter_errors(doc))
    if stem.split(".")[0] == "ImageLabels" and not errs:
        # contentSchema는 검증기가 강제하지 않으므로 JSON 문자열 라벨의 내용을 따로 풀어 검증한다(deploy validate.py와 같은 방식).
        for label, name in (("io.openit.jobs", "JobsDeclaration"), ("io.openit.exposure", "Exposure")):
            if label in doc:
                try:
                    errs += list(validator(name).iter_errors(json.loads(doc[label])))
                except ValueError:
                    errs.append(f"{label}가 JSON이 아니다")
    return errs


class PromotedSchemas(unittest.TestCase):
    def test_스키마_목록은_매니페스트와_같다(self):
        on_disk = {p.name[: -len(".schema.json")] for p in schema_dir().glob("*.schema.json")}
        self.assertTrue(_names() <= on_disk, _names() - on_disk)
        self.assertGreaterEqual(len(_names()), 50)

    def test_스키마는_유효하고_ref가_풀린다(self):
        for n in sorted(_names()):
            jsonschema.Draft202012Validator.check_schema(load_schema(n))
            validator(n)

    def test_통과_예시는_통과한다(self):
        n = 0
        for p in sorted((ROOT / "examples").glob("*.json")):
            if p.stem.split(".")[0] not in _names():
                continue
            errs = _errors(p.stem, json.loads(p.read_text(encoding="utf-8")))
            self.assertEqual(errs, [], p.name)
            n += 1
        self.assertGreaterEqual(n, 120)

    def test_거부_예시는_거부된다(self):
        n = 0
        for p in sorted((ROOT / "examples_invalid").glob("*.json")):
            errs = _errors(p.stem, json.loads(p.read_text(encoding="utf-8")))
            self.assertTrue(errs, f"거부되어야 하는데 통과: {p.name}")
            n += 1
        self.assertGreaterEqual(n, 140)

    def test_스키마마다_통과와_거부_예시가_있다(self):
        have_v = {p.stem.split(".")[0] for p in (ROOT / "examples").glob("*.json")}
        have_i = {p.stem.split(".")[0] for p in (ROOT / "examples_invalid").glob("*.json")}
        self.assertEqual(sorted(_names() - have_v), [])
        self.assertEqual(sorted(_names() - have_i), [])


if __name__ == "__main__":
    unittest.main()
