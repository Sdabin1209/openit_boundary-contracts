import json
import unittest

from boundary_contracts import load_schema, schema_dir, validator, PIPELINE_SCHEMA_VERSION


class Package(unittest.TestCase):
    def test_스키마는_패키지_안에_있다(self):
        names = sorted(p.name for p in schema_dir().glob("*.schema.json"))
        self.assertIn("ReleaseManifest.schema.json", names)
        self.assertIn("_common.schema.json", names)
        records = {n[: -len(".schema.json")] for n in names if not n.startswith("_")}
        self.assertEqual(len(records), 84)  # 2.4.0: QuestionFieldSpec(U32) 1개 추가로 84. 2.0.0: 31개. 2.2.0: ActionExtractionRules(ADR 0010) 1개와 영역 경계 스키마 49개(D107), QuestionFlowTable·ExtractRequest(ADR 0010)를 더했다
        self.assertFalse({"ParserSample", "GeneratorSample"} & records)
        self.assertTrue({"ActionExtractionInput", "ActionExtraction", "ActionExtractionSample", "ResponseRequest",
                         "ResponseText", "ResponseSample"} <= records)

    def test_모르는_계약은_KeyError(self):
        with self.assertRaises(KeyError):
            load_schema("Nope")

    def test_validator는_예시를_통과시킨다(self):
        root = schema_dir().parent.parent / "examples"
        rec = json.loads((root / "ReleaseManifest.json").read_text())
        self.assertEqual(list(validator("ReleaseManifest").iter_errors(rec)), [])
        rec["pipeline_schema_version"] = "1"
        self.assertTrue(list(validator("ReleaseManifest").iter_errors(rec)))

    def test_버전_상수(self):
        from importlib.metadata import version  # 왜: 버전 리터럴을 시험에 복제하지 않고 설치된 패키지에서 읽는다
        self.assertEqual(PIPELINE_SCHEMA_VERSION, ".".join(version("boundary-contracts").split(".")[:2]))

    def test_패키지_버전은_계약_버전과_MAJOR_MINOR가_같다(self):
        import re
        from pathlib import Path
        text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        version = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
        self.assertEqual(".".join(version.split(".")[:2]), PIPELINE_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
