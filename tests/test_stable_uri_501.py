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
        # 안정 URI 로 연 계약 문서 안의 모든 다른 파일 상대 $ref 가 같은 접두로 풀린다(파일 전부, 참조 전부)
        reg = schema_registry()
        checked = 0
        for path in schema_dir().glob("*.schema.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            refs = set()
            def walk(o):
                if isinstance(o, dict):
                    r = o.get("$ref")
                    if isinstance(r, str) and not r.startswith("#") and "://" not in r:
                        refs.add(r)
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(doc)
            resolver = reg.resolver(base_uri=bc.CONTRACT_URI + path.name)
            for r in refs:
                with self.subTest(path.name, ref=r):
                    resolver.lookup(r)
                    checked += 1
        self.assertGreater(checked, 50)

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


class GatewayDefaults(unittest.TestCase):
    def test_defaults_match_schema_and_conventions(self):
        g = bc.gateway_defaults()
        ex = bc.load_schema("Exposure")["$defs"]["route"]["properties"]
        self.assertEqual(ex["max_body_bytes"]["default"], g["max_body_bytes"])
        conv = (ROOT / "CONVENTIONS.md").read_text(encoding="utf-8")
        # 사람이 읽는 표의 값과 같은지(표가 정본 파일과 어긋나면 실패)
        # 서비스와 값의 짝을 표의 행으로 대조(값만 있는지가 아니라 그 서비스 행에 그 값이 있는지)
        rows = {line.split("|")[1].strip(): line for line in conv.splitlines() if line.startswith("| ") and "초(" in line}
        for svc, ms in g["timeouts_ms"]["response_header"]["by_service"].items():
            with self.subTest(svc):
                row = next((v for k, v in rows.items() if k.startswith(svc)), None)
                self.assertIsNotNone(row, svc)
                self.assertIn(f"초({ms // 1000})", row)
        self.assertIn(f"응답 헤더 {g['timeouts_ms']['response_header']['default'] // 1000}초", conv)
        self.assertIn(f"연결 {g['timeouts_ms']['dial'] // 1000}초", conv)

    def test_returns_copy(self):
        bc.gateway_defaults()["max_body_bytes"] = 1
        self.assertEqual(bc.gateway_defaults()["max_body_bytes"], 8388608)


class SecretFormats(unittest.TestCase):
    def test_formats(self):
        f = bc.secret_format_problems
        ok = {"token_list": ["abc123", "a,b,c", "dG9rZW4=", "a:b"],
              "role_token_list": ["reviewer=t1,operator=t2", "survey-service=dG9rZW4==", "r=a:b"],
              "token_actor_role_list": ["t:author-e2e:question-author", "t1:a:r,t2:b:s"],
              "credentials_line": ["user:pa:ss", "user:pass with space", "u:p=="]}
        bad = {"token_list": ["a,,b", "a b", "a\tb", "a\x00b"],
               "role_token_list": ["t1", "=t1", "r=", "r=a b", "r=a\x01"],
               "token_actor_role_list": ["t:author", "t:a:r:x", "t::r"],
               "credentials_line": ["user", ":pass", "user:", "user:pa\nss", "us\x7fer:p"]}
        for kind, values in ok.items():
            for v in values:
                with self.subTest(kind=kind, ok=repr(v)):
                    self.assertEqual(f(kind, v), [])
        for kind, values in bad.items():
            for v in values:
                with self.subTest(kind=kind, bad=repr(v)):
                    self.assertEqual(f(kind, v), ["FORMAT"])
        self.assertEqual(f("token_list", ""), ["EMPTY"])
        with self.assertRaises(ValueError):
            f("nope", "x")

    def test_schema_acceptance_not_narrowed(self):
        # PATCH: TokenList 는 4.x 의 RoleTokenList 처럼 비어 있지 않은 문자열을 모두 받는다
        d = bc.load_schema("QuestionAuthoringEnv")["$defs"]["TokenList"]
        self.assertEqual({k: d[k] for k in ("type", "minLength")}, {"type": "string", "minLength": 1})
        self.assertNotIn("pattern", d)
