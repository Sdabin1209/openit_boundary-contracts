"""계약 5.0.1: 안정 URI 로 계약 스키마를 오프라인 등록한다(외부 문서 — 문진 스키마 5.x — 가 $ref 로 가리킨다)."""
import json
import tomllib
import unittest
from pathlib import Path

import jsonschema
from referencing.exceptions import Unresolvable

import boundary_contracts as bc
from boundary_contracts.schemas_api import schema_registry, schema_dir

ROOT = Path(__file__).resolve().parents[1]


class StableUri(unittest.TestCase):
    def test_major_in_path_matches_package(self):
        major = int(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"].split(".")[0])
        self.assertEqual(bc.CONTRACT_URI, f"https://openit.example/contracts/v{major}/")
        self.assertEqual(bc.contract_uri("_common"), bc.CONTRACT_URI + "_common.schema.json")

    def test_every_contract_schema_resolves_by_stable_uri(self):
        reg = schema_registry()
        for path in schema_dir().glob("*.schema.json"):
            with self.subTest(path.name):
                got = reg.resolver().lookup(bc.CONTRACT_URI + path.name).contents
                self.assertEqual(got.get("title"), json.loads(path.read_text(encoding="utf-8")).get("title"))

    def _external(self):
        # 외부 문서(문진 스키마 모양): 계약 타입을 안정 URI 로만 가리킨다
        return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://openit.example/survey/v1/Probe.json",
                "type": "object", "additionalProperties": False, "required": ["session_id", "question_id"],
                "properties": {"session_id": {"$ref": bc.contract_uri("_common") + "#/$defs/SessionId"},
                               "question_id": {"$ref": bc.contract_uri("_common") + "#/$defs/QuestionId"},
                               "n": {"type": "number"}}}

    def test_external_document_delegates_through_contract_registry(self):
        v = jsonschema.Draft202012Validator(self._external(), registry=schema_registry(), format_checker=bc.format_checker())
        self.assertTrue(v.is_valid({"session_id": "a" * 64, "question_id": "Q4_1"}))
        for bad in ({"session_id": "_lead", "question_id": "Q1"}, {"session_id": "a" * 65, "question_id": "Q1"},
                    {"session_id": "a.b", "question_id": "Q1"}, {"session_id": "ok", "question_id": "X1"}):
            with self.subTest(bad):
                self.assertFalse(v.is_valid(bad))

    def test_relative_refs_inside_stable_uri_documents_resolve(self):
        # 안정 URI 로 연 계약 문서 안의 상대 $ref(다른 계약 파일)도 같은 접두로 풀린다
        reg = schema_registry()
        for path in schema_dir().glob("*.schema.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if '"$ref": "_common.schema.json' not in json.dumps(doc):
                continue
            with self.subTest(path.name):
                v = jsonschema.Draft202012Validator({"$ref": bc.CONTRACT_URI + path.name}, registry=reg)
                list(v.iter_errors({}))   # 해석 실패면 Unresolvable 이 난다
            break

    def test_without_contract_registry_it_fails_loudly_not_silently(self):
        v = jsonschema.Draft202012Validator(self._external())
        with self.assertRaises(Unresolvable):
            v.is_valid({"session_id": "ok", "question_id": "Q1"})

    def test_reader_validator_knows_stable_uri(self):
        from boundary_contracts.clients._reader_schema import _local_docs
        self.assertIn(bc.contract_uri("_common"), _local_docs())


if __name__ == "__main__":
    unittest.main()


class SchemaValidator(unittest.TestCase):
    def test_area_schema_gets_contract_rules(self):
        area = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                "properties": {"n": {"type": "number"}, "sid": {"$ref": bc.contract_uri("_common") + "#/$defs/SessionId"}}}
        v = bc.schema_validator(area)
        self.assertTrue(v.is_valid({"n": 1.5, "sid": "ab"}))
        for bad in ({"n": float("nan")}, {"n": float("inf")}, {"sid": "_x"}):
            with self.subTest(bad):
                self.assertFalse(v.is_valid(bad))
        # evolve 뒤에도 같은 규칙(ContractValidator 재감싸기)
        self.assertFalse(v.evolve(schema=area).is_valid({"n": float("-inf")}))
