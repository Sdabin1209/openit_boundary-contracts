"""U45(2.5.1): 계약 클라이언트가 응답을 손 검사 대신 계약 스키마로 검증한다. 위반은 서버 결함(INTEGRITY_ERROR)."""
import unittest
from unittest import mock

from boundary_contracts import BoundaryError
from boundary_contracts.clients import runtime as rt
from boundary_contracts.clients import ops
from boundary_contracts.clients._http import HttpClientBase


def client(cls, body):
    c = cls("http://127.0.0.1:9", "t")
    c._json = mock.Mock(return_value=body)
    return c


class U45Test(unittest.TestCase):
    def code(self, fn, *a):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a)
        return cm.exception.code

    def test_적재_상태의_error는_BoundaryError여야_한다(self):
        c = client(rt.HttpModelRuntime, {"release_id": "rel-1", "state": "FAILED", "error": {"code": "NOPE"}})
        self.assertEqual(self.code(c.get_release_state, "rel-1"), "INTEGRITY_ERROR")

    def test_적재_상태_정상(self):
        c = client(rt.HttpModelRuntime, {"release_id": "rel-1", "state": "LOADED", "error": None})
        self.assertEqual(c.get_release_state("rel-1")["state"], "LOADED")

    def test_목록_next_cursor는_문자열이나_null(self):
        c = client(HttpClientBase, {"items": [], "next_cursor": 3})
        self.assertEqual(self.code(c._page, "/v1/x", None, 10), "INTEGRITY_ERROR")

    def test_비식별_Trace는_계약을_지켜야_한다(self):
        cls = next(v for v in vars(ops).values() if isinstance(v, type) and hasattr(v, "get_trace"))
        c = client(cls, {"anything": "원문 조각"})
        self.assertEqual(self.code(c.get_trace, "dtr-1"), "INTEGRITY_ERROR")


if __name__ == "__main__":
    unittest.main()
