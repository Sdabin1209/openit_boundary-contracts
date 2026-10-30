"""3.0.3(U53), 3.1.0: HttpGateService.decide()는 계약 ApprovalRequest 그대로 보낸다.
본문에 approver_id가 없고(D88: 신원은 X-Openit-User로만), report_hash는 review-report의 X-Openit-Report-Hash 값을 그대로 쓴다."""
import unittest

from _fixtures import APPROVER, WRITE, example, make_server
from boundary_contracts import BoundaryError, sha256_hash, validator
from boundary_contracts.clients import HttpGateService


class Decide303(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.a = HttpGateService(self.srv.url, APPROVER)

    def _sub(self):
        g = HttpGateService(self.srv.url, WRITE)
        return g.submit_candidate(example("GateDecision.pass")["subject"], requested_by_role="operator")["submission_id"]

    def test_본문은_ApprovalRequest이고_해시는_머리글_값(self):
        sub = self._sub()
        sent = []
        orig = self.a._json
        self.a._json = lambda m, p, query=None, body=None: (sent.append((m, p, body)), orig(m, p, query, body))[1]
        rep, h = self.a.get_review_report_with_hash(sub)
        self.assertEqual(h, sha256_hash(rep))
        ok = self.a.decide(sub, "APPROVE", approver_role="release-approver", report_hash=h)
        self.assertEqual(ok["decision"], "APPROVE")
        body = [b for m, p, b in sent if p == "/v1/approvals"][0]
        self.assertNotIn("approver_id", body)
        self.assertEqual(list(validator("ApprovalRequest").iter_errors(body)), [])
        self.assertEqual(body["report_hash"], sha256_hash(self.a.get_review_report(sub)))

    def test_승인자는_user_머리글로(self):
        sub = self._sub()
        a = HttpGateService(self.srv.url, APPROVER, user="approver-kim")
        ok = a.decide(sub, "APPROVE", approver_role="release-approver", report_hash=a.get_review_report_with_hash(sub)[1])
        self.assertEqual(ok["approver_id"], "approver-kim")

    def test_report_hash_없이는_결정할_수_없다(self):
        with self.assertRaises(TypeError):
            self.a.decide(self._sub(), "APPROVE", approver_role="release-approver")

    def test_낡은_보고서_해시는_CONFLICT(self):
        sub = self._sub()
        with self.assertRaises(BoundaryError) as cm:
            self.a.decide(sub, "APPROVE", approver_role="release-approver", report_hash=sha256_hash({"다른": "보고서"}))
        self.assertEqual(cm.exception.code, "CONFLICT")


if __name__ == "__main__":
    unittest.main()
