"""계약 JSON 공통 규칙(5.0.0, CONVENTIONS 10절 첫 항목, I-JSON RFC 7493)과 검토 값 검사."""
import json
import pathlib
import unittest

from boundary_contracts import BoundaryError, canonicalize, strict_json, validate
from boundary_contracts.review_input import review_value_problems
from boundary_contracts.strict_json import MAX_JSON_BYTES, MAX_JSON_DEPTH, check_json_value, dumps, loads

ROOT = pathlib.Path(__file__).resolve().parents[1]


def nest(n):
    """깊이 n(루트 배열 = 1)인 값."""
    v = []
    for _ in range(n - 1):
        v = [v]
    return v


class Depth(unittest.TestCase):
    def test_경계(self):
        check_json_value(nest(MAX_JSON_DEPTH))
        with self.assertRaises(BoundaryError):
            check_json_value(nest(MAX_JSON_DEPTH + 1))
        self.assertEqual(loads(json.dumps(nest(MAX_JSON_DEPTH))), nest(MAX_JSON_DEPTH))
        with self.assertRaises(BoundaryError) as cm:
            loads(json.dumps(nest(MAX_JSON_DEPTH + 1)))
        self.assertEqual(cm.exception.code, "INVALID_RECORD")

    def test_스칼라는_깊이에_세지_않는다(self):
        v = nest(MAX_JSON_DEPTH)
        cur = v
        while cur:
            cur = cur[0]
        cur.append("leaf")
        check_json_value(v)

    def test_깊이_5000_은_재귀_한도_없이_거부(self):
        raw = "[" * 5000 + "]" * 5000
        with self.assertRaises(BoundaryError):
            loads(raw)
        v = []
        cur = v
        for _ in range(4999):
            nxt = []
            cur.append(nxt)
            cur = nxt
        with self.assertRaises(BoundaryError):
            check_json_value(v)
        with self.assertRaises(ValueError):
            canonicalize(v)


class Numbers(unittest.TestCase):
    def test_NaN_Infinity_오버플로_거부(self):
        for raw in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', '{"a": 1e999}', '{"a": -1e999}', '{"a": %d}' % (2**53 + 1)):
            with self.subTest(raw=raw), self.assertRaises(BoundaryError):
                loads(raw)
        self.assertEqual(loads('{"a": 1.5e300, "b": 9007199254740992}'), {"a": 1.5e300, "b": 2**53})

    def test_직렬화는_NaN_을_쓰지_않는다(self):
        with self.assertRaises(BoundaryError):
            dumps({"a": float("inf")})
        self.assertEqual(dumps({"a": 1}), '{"a": 1}')

    def test_검증기는_파일_간_참조_뒤에서도_비유한_수를_거부한다(self):
        # codex 재검토: 확장 클래스는 $ref 로 다른 파일($schema 있음)에 들어가면 표준 클래스로 돌아갔다. 실제 파일 참조로 회귀 시험
        import copy
        from boundary_contracts import validator
        ex = json.loads((ROOT / "examples/ActionExtractionSample.json").read_text(encoding="utf-8"))
        v = validator("ActionExtractionSample")
        self.assertTrue(v.is_valid(ex))
        for bad in (float("inf"), float("-inf"), float("nan")):
            d = copy.deepcopy(ex)
            num = [x for x in d["expected"]["values"]]
            num[0]["value"] = bad          # ActionExtractionSample.expected -> ActionExtraction.schema.json(파일 간 $ref)의 number 칸
            with self.subTest(bad=bad):
                self.assertFalse(v.is_valid(d))
                self.assertTrue(any(e.validator == "finite" for e in v.iter_errors(d)))
                with self.assertRaises(Exception):
                    v.validate(d)

    def test_evolve_와_descend_뒤에도_비유한_수를_거부한다(self):
        # codex 3차: evolve 가 표준 검증기를 돌려줘 검사를 건너뛰었다(link _resolve, question-authoring wiring/contract.py 경로)
        import copy
        import jsonschema
        from boundary_contracts import validator
        from boundary_contracts.schemas_api import ContractValidator
        ex = json.loads((ROOT / "examples/ActionExtractionSample.json").read_text(encoding="utf-8"))
        base = validator("ActionExtractionSample")
        whole = base.evolve(schema=base.schema)                                        # 파일 참조(expected -> ActionExtraction.schema.json)
        frag = validator("ActionExtraction").evolve(schema={"$ref": validator("ActionExtraction").schema["$id"] + "#/properties/values"})
        self.assertIsInstance(whole, ContractValidator); self.assertIsInstance(frag, ContractValidator)
        self.assertIs(whole.format_checker, base.format_checker)
        self.assertTrue(whole.is_valid(ex))
        for bad in (float("nan"), float("inf"), float("-inf")):
            d = copy.deepcopy(ex); d["expected"]["values"][0]["value"] = bad
            vals = [dict(ex["expected"]["values"][0], value=bad)]
            with self.subTest(bad=bad):
                for v, inst in ((whole, d), (frag, vals)):
                    self.assertFalse(v.is_valid(inst))
                    self.assertTrue(any(e.validator == "finite" for e in v.iter_errors(inst)))
                    self.assertIsNotNone(jsonschema.exceptions.best_match(v.iter_errors(inst)))
                    with self.assertRaises(jsonschema.ValidationError):
                        v.validate(inst)
                errs = list(base.descend(d["expected"], {"type": "object"}, path="expected"))
                self.assertTrue(errs and all(e.validator == "finite" for e in errs))
                self.assertEqual(list(errs[0].absolute_path)[0], "expected")
        # format_checker 가 evolve 뒤에도 강제된다(format uri)
        push = validator("PushSubscriptionRequest")
        ev = push.evolve(schema=push.schema)
        good = json.loads((ROOT / "examples/PushSubscriptionRequest.json").read_text(encoding="utf-8"))
        self.assertTrue(ev.is_valid(good))
        bad = dict(good, endpoint=good["endpoint"] + "%zz")
        self.assertEqual([e.validator for e in ev.iter_errors(bad)], ["format"])

    def test_조각_참조와_HTTP_계약도_비유한_수를_거부한다(self):
        from boundary_contracts import validator
        from boundary_contracts.http_contracts import ContractViolation, HttpContract
        frag = validator("ActionExtraction#/properties/values")
        good = [{"key": "Q1.D01.count", "value": 1.5, "precision": "exact", "status": "ANSWERED", "save": True}]
        self.assertTrue(frag.is_valid(good))
        self.assertFalse(frag.is_valid([dict(good[0], value=float("inf"))]))
        c = HttpContract("question-authoring")
        with self.assertRaises(ContractViolation):
            c.check({"type": "object"}, {"a": float("nan")}, "body")
        c.check({"type": "object"}, {"a": 1.0}, "body")

    def test_validate_진입점(self):
        with self.assertRaises(BoundaryError):
            validate("BoundaryError", {"pipeline_schema_version": "5.0", "code": "UNAVAILABLE", "message": "x", "retryable": True, "details": {"n": float("inf")}})


class SizeBudget(unittest.TestCase):
    def _str_body(self, n_chars, ch):
        return ch * n_chars

    def test_dumps_와_loads_는_같은_바이트_상한(self):
        # 직렬화 '"' + s + '"' 의 바이트 = 문자 바이트 * n + 2
        for ch, w in (("a", 1), ("가", 3)):
            n_ok = (MAX_JSON_BYTES - 2) // w
            with self.subTest(ch=ch):
                out = dumps(ch * n_ok)
                self.assertLessEqual(len(out.encode("utf-8")), MAX_JSON_BYTES)
                self.assertEqual(loads(out), ch * n_ok)
                with self.assertRaises(BoundaryError):
                    dumps(ch * (n_ok + 1))
                with self.assertRaises(BoundaryError):
                    loads(json.dumps(ch * (n_ok + 1), ensure_ascii=False))

    def test_validate_는_압축_직렬화_크기를_본다(self):
        rec = {"pipeline_schema_version": "5.0", "code": "UNAVAILABLE", "message": "x" * MAX_JSON_BYTES, "retryable": True}
        with self.assertRaises(BoundaryError):
            validate("BoundaryError", rec)


class NoValuesInErrors(unittest.TestCase):
    def test_오류에_값과_사용자_키가_없다(self):
        canary = "CANARY환자문장-010"
        rec = {"pipeline_schema_version": "5.0", "code": canary, "message": canary, "retryable": "no", canary: canary}
        with self.assertRaises(BoundaryError) as cm:
            validate("BoundaryError", rec)
        dumped = json.dumps(cm.exception.to_record("5.0"), ensure_ascii=False)
        self.assertNotIn("CANARY", dumped)
        self.assertTrue(cm.exception.details["errors"])
        for e in cm.exception.details["errors"]:
            self.assertEqual(set(e), {"schema_path", "keyword"})

    def test_strict_loads_오류에_키가_없다(self):
        with self.assertRaises(BoundaryError) as cm:
            loads('{"CANARY키": 1, "CANARY키": 2}')
        self.assertNotIn("CANARY", str(cm.exception.message))


class Others(unittest.TestCase):
    def test_중복_키_서로게이트_크기(self):
        with self.assertRaises(BoundaryError):
            loads('{"a": 1, "a": 2}')
        with self.assertRaises(BoundaryError):
            loads('{"a": "\\ud800"}')
        with self.assertRaises(BoundaryError):
            loads(b'"' + b"a" * (strict_json.MAX_JSON_BYTES) + b'"')

    def test_값_수_예산(self):
        with self.assertRaises(BoundaryError):
            check_json_value([0] * 10, max_nodes=10)
        check_json_value([0] * 9, max_nodes=10)


class ReviewValue(unittest.TestCase):
    def test_개인정보와_길이(self):
        self.assertEqual(review_value_problems({"values": [{"key": "Q1.D01.count", "value": 3}]}), [])
        self.assertEqual(review_value_problems({"t": "연락처 010-1234-5678"}), ["phone_kr"])
        self.assertEqual(review_value_problems({"t": "a@b.co"}), ["email"])
        self.assertIn("rrn_kr", review_value_problems({"t": "900101-1234567"}))
        self.assertEqual(review_value_problems({"t": "x" * 20001}), ["string_too_long>20000"])
        self.assertEqual(review_value_problems({"t": "x" * 20000}), [])
        with self.assertRaises(BoundaryError):
            review_value_problems(nest(MAX_JSON_DEPTH + 1))


if __name__ == "__main__":
    unittest.main()
