import unittest
from datetime import datetime, timezone

from _fixtures import READ, WRITE, example, make_server
from boundary_contracts import BoundaryError
from boundary_contracts.clients import HttpFailureStore, HttpTraceIngest


class Ops(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.f = HttpFailureStore(self.srv.url, READ)
        self.t = HttpTraceIngest(self.srv.url, WRITE)

    def code(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception.code

    def test_trace_전송은_멱등(self):
        env = example("TraceEnvelope")
        first = self.t.send(env)
        self.assertEqual(first["status"], "ACCEPTED")
        self.assertEqual(self.t.send(env)["status"], "DUPLICATE")

    def test_trace_보내기_전_검증(self):
        self.assertEqual(self.code(self.t.send, {"session_id": "s"}), "INVALID_RECORD")
        self.assertEqual([p for _, p, _ in self.srv.requests if p == "/v1/traces"], [])

    def test_읽기_토큰은_trace_전송_거부(self):
        self.assertEqual(self.code(HttpTraceIngest(self.srv.url, READ).send, example("TraceEnvelope")), "PERMISSION_DENIED")

    def test_케이스_조회(self):
        self.assertEqual(self.f.get_case("fc-1")["version"], 2)
        self.assertEqual(self.f.get_case("fc-1", version=1)["version"], 1)
        self.assertEqual(self.code(self.f.get_case, "fc-9"), "NOT_FOUND")
        self.assertEqual(self.code(self.f.get_case, "fc-1", version=7), "NOT_FOUND")

    def test_케이스_목록과_필터(self):
        items, nxt = self.f.list_cases()
        self.assertEqual(sorted((c["case_id"], c["version"]) for c in items), [("fc-1", 2), ("fc-2", 1)])
        self.assertEqual(len(self.f.list_cases(latest_only=False)[0]), 3)
        self.assertEqual(len(self.f.list_cases(review_status="CONFIRMED")[0]), 1)
        since = datetime(2026, 10, 15, tzinfo=timezone.utc)
        self.assertEqual(len(self.f.list_cases(updated_since=since)[0]), 2)
        self.assertTrue(any("updated_since=2026-10-15T00%3A00%3A00Z" in p for _, p, _ in self.srv.requests))
        page, cur = self.f.list_cases(latest_only=False, limit=2)
        self.assertEqual((len(page), cur), (2, "2"))
        self.assertEqual(len(self.f.list_cases(latest_only=False, cursor=cur, limit=2)[0]), 1)

    def test_비식별_trace(self):
        self.assertEqual(self.f.get_trace("tr-1")["turn_id"], "t-1")
        self.assertEqual(self.code(self.f.get_trace, "nope"), "NOT_FOUND")

    def test_publish_case는_열지_않는다(self):
        self.assertEqual(self.code(self.f.publish_case, example("FailureCase")), "FAILED_PRECONDITION")

    def test_스키마_위반_케이스는_INTEGRITY_ERROR(self):
        self.srv.cases[0] = {"case_id": "fc-1", "version": 1}
        self.assertEqual(self.code(self.f.get_case, "fc-1", version=1), "INTEGRITY_ERROR")


if __name__ == "__main__":
    unittest.main()
