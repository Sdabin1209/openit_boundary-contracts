"""3.1.1: 참조 서버가 계약 규칙대로 응답한다 — 토큰 오류 401(D106), 승인에 X-Openit-User 없으면 401, 승인 멱등(200 / 409 ALREADY_DECIDED)."""
import unittest

from _fixtures import APPROVER, WRITE, example, make_server
from boundary_contracts import BoundaryError
from boundary_contracts.clients import HttpGateService


class Ref311(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.sub = HttpGateService(self.srv.url, WRITE).submit_candidate(example("GateDecision.pass")["subject"], requested_by_role="operator")["submission_id"]

    def _err(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception

    def test_토큰이_틀리면_401(self):
        e = self._err(HttpGateService(self.srv.url, "wrong-token").get_submission, self.sub)
        self.assertEqual((e.code, e.details.get("http_status")), ("PERMISSION_DENIED", 401))

    def test_승인에_사람_머리글이_없으면_401(self):
        a = HttpGateService(self.srv.url, APPROVER)
        h = a.get_review_report_with_hash(self.sub)[1]
        e = self._err(a.decide, self.sub, "APPROVE", approver_role="release-approver", report_hash=h)
        self.assertEqual(e.details.get("http_status"), 401)

    def test_승인은_멱등이다(self):
        a = HttpGateService(self.srv.url, APPROVER, user="approver-1")
        h = a.get_review_report_with_hash(self.sub)[1]
        first = a.decide(self.sub, "APPROVE", approver_role="release-approver", report_hash=h)
        self.assertEqual(a.decide(self.sub, "APPROVE", approver_role="release-approver", report_hash=h), first)
        e = self._err(a.decide, self.sub, "REJECT", approver_role="release-approver", report_hash=h, reason="다른 결정")
        self.assertEqual((e.code, e.details.get("reason")), ("CONFLICT", "ALREADY_DECIDED"))


if __name__ == "__main__":
    unittest.main()
