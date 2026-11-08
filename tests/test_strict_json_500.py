"""계약 JSON 공통 규칙(5.0.0, CONVENTIONS 10절 첫 항목, I-JSON RFC 7493)과 검토 값 검사."""
import json
import unittest

from boundary_contracts import BoundaryError, canonicalize, strict_json, validate
from boundary_contracts.review_input import review_value_problems
from boundary_contracts.strict_json import MAX_JSON_DEPTH, check_json_value, dumps, loads


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

    def test_검증기는_무한대를_number_로_보지_않는다(self):
        from boundary_contracts.schemas_api import _finite_validator_class
        V = _finite_validator_class()
        self.assertFalse(V({"type": "number"}).is_valid(float("inf")))
        self.assertFalse(V({"type": "number"}).is_valid(float("nan")))
        self.assertTrue(V({"type": "number"}).is_valid(1.5))
        self.assertTrue(V({"type": "integer"}).is_valid(3))

    def test_validate_진입점(self):
        with self.assertRaises(BoundaryError):
            validate("BoundaryError", {"pipeline_schema_version": "5.0", "code": "UNAVAILABLE", "message": "x", "retryable": True, "details": {"n": float("inf")}})


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
