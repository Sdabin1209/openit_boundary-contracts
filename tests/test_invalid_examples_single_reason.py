"""거부 예시(conformance/examples_invalid)는 규칙 하나만 어긴다.

시험 설계 원칙: 음성 예시는 "정상 값 하나에 의도한 위반 하나"여야 한다. 위반이 둘 이상이면 의도한 규칙이 회귀해
(예: 스키마에서 그 규칙이 빠져도) 다른 위반 때문에 여전히 거부되어 시험이 회귀를 잡지 못한다.
판정: 검증 오류가 모두 같은 (검증 키워드, 인스턴스 경로)에서 나와야 한다. oneOf/anyOf 처럼 규칙 하나가 오류를
여러 줄 내는 경우는 최상위 오류가 한 (키워드, 경로)이므로 그대로 통과한다. 같은 경로의 required 여러 개도
"필수 속성 누락" 규칙 하나로 본다.
스키마 이름과 $defs 선택 규칙은 test_promoted_schemas._check 를 그대로 쓴다(이름 규칙을 두 곳에 두지 않는다).
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_promoted_schemas import _check  # noqa: E402

from boundary_contracts import schema_dir, validator  # noqa: E402

INVALID = HERE.parent / "conformance" / "examples_invalid"

# 규칙 하나가 본래 여러 (키워드, 경로) 오류를 내는 경우만 여기에 둔다. 항목마다 이유를 적는다.
# 현재 그런 예시는 없다(2026-11-08 4.0.5 작업 트리 기준 전부 단일 이유).
ALLOWLIST: dict[str, str] = {}

# ImageLabels 의 JSON 문자열 라벨은 contentSchema 라 검증기가 강제하지 않는다. test_promoted_schemas._errors 와 같은
# 방식으로 내용을 풀어 검증하고, 경로 앞에 라벨 이름을 붙여 같은 기준으로 센다.
_CONTENT_LABELS = (("io.openit.jobs", "JobsDeclaration"), ("io.openit.exposure", "Exposure"))


def _keys(stem, doc):
    errs = list(_check(stem).iter_errors(doc))
    keys = {(e.validator, "/".join(map(str, e.absolute_path))) for e in errs}
    if stem.split(".")[0] == "ImageLabels" and not errs:
        for label, name in _CONTENT_LABELS:
            if label not in doc:
                continue
            try:
                inner = json.loads(doc[label])
            except ValueError:
                keys.add(("json", label))
                continue
            keys |= {(e.validator, label + ":" + "/".join(map(str, e.absolute_path))) for e in validator(name).iter_errors(inner)}
    return keys


class InvalidExamplesSingleReason(unittest.TestCase):
    def test_거부_예시는_규칙_하나만_어긴다(self):
        names = {p.name[: -len(".schema.json")] for p in schema_dir().glob("*.schema.json")}
        checked = 0
        for p in sorted(INVALID.glob("*.json")):
            if p.stem.split(".")[0] not in names:
                continue
            with self.subTest(example=p.name):
                keys = _keys(p.stem, json.loads(p.read_text(encoding="utf-8")))
                self.assertTrue(keys, f"거부되어야 하는데 통과: {p.name}")
                if p.name in ALLOWLIST:
                    continue
                self.assertEqual(len(keys), 1, f"{p.name} 은 규칙 하나만 어겨야 한다: {sorted(keys)}")
            checked += 1
        self.assertGreaterEqual(checked, 140)

    def test_허용_목록은_실제_파일만_가리킨다(self):
        for name in ALLOWLIST:
            self.assertTrue((INVALID / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
