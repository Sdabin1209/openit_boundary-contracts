import tempfile
import unittest
from pathlib import Path

from _fixtures import FILES_A, FILES_B, OTHER, READ, WRITE, example, make_server, release
from boundary_contracts import BoundaryError, directory_hash, sdk
from boundary_contracts.clients import HttpGateService, HttpReleaseReader
from _fixtures import APPROVER


class Releases(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.r = HttpReleaseReader(self.srv.url, READ)
        self.g = HttpGateService(self.srv.url, WRITE)  # 역할 operator

    def code(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception.code

    def test_읽기(self):
        self.assertIsNone(self.r.get_active_pointer())
        self.assertEqual(self.r.get_release("rel-0001")["release_id"], "rel-0001")
        items, nxt = self.r.list_releases()
        self.assertEqual([x["release_id"] for x in items], ["rel-0003", "rel-0002", "rel-0001"])
        self.assertEqual(self.r.get_decision("gd-2")["decision_id"], "gd-2")
        self.assertEqual(self.code(self.r.get_decision, "gd-9"), "NOT_FOUND")
        self.assertEqual(self.code(self.r.get_release, "rel-9"), "NOT_FOUND")

    def test_find_decisions는_최신부터이고_조건과_쪽을_쓴다(self):
        items, _ = self.r.find_decisions(submission_id="sub-1")
        self.assertEqual([d["decision_id"] for d in items], ["gd-3", "gd-1"])
        ref = example("GateDecision.pass")["subject"]["question_set"]
        self.assertEqual(len(self.r.find_decisions(question_set=ref)[0]), 3)
        self.assertEqual(self.r.find_decisions(question_set=dict(ref, version="zz"))[0], [])
        first, cur = self.r.find_decisions(limit=2)
        self.assertEqual((len(first), cur), (2, "2"))
        self.assertEqual([d["decision_id"] for d in self.r.find_decisions(cursor=cur, limit=2)[0]], ["gd-1"])

    def test_load_bundle(self):
        b = self.r.load_bundle("rel-0001", dest=self.tmp)
        self.assertIsInstance(b, sdk.ReleaseBundle)
        self.assertEqual(b.manifest["release_id"], "rel-0001")
        self.assertEqual(b.question_bank["version"], 3)
        self.assertEqual(set(b.adapters), {"LORA_A", "LORA_B"})
        self.assertEqual(directory_hash(b.adapters["LORA_A"]), b.manifest["adapters"]["LORA_A"]["adapter_hash"])
        self.assertEqual((b.adapters["LORA_B"] / "adapter_config.json").read_bytes(), FILES_B["adapter_config.json"])

    def test_PASS가_아닌_릴리스는_FAILED_PRECONDITION(self):
        self.assertEqual(self.code(self.r.load_bundle, "rel-0002", dest=self.tmp), "FAILED_PRECONDITION")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_번들_변조는_INTEGRITY_ERROR이고_지운다(self):
        s = self.srv.releases
        s["rel-0001"]["bank"]["questions"][0]["text"] = "변조"
        self.assertEqual(self.code(self.r.load_bundle, "rel-0001", dest=self.tmp), "INTEGRITY_ERROR")
        s["rel-0003"]["adapters"]["LORA_B"] = {"adapter_config.json": b"tampered"}
        self.assertEqual(self.code(self.r.load_bundle, "rel-0003", dest=self.tmp), "INTEGRITY_ERROR")
        s["rel-0003"] = release("rel-0003")
        s["rel-0003"]["manifest"]["created_at"] = "2027-01-01T00:00:00Z"  # content_hash 불일치
        self.assertEqual(self.code(self.r.load_bundle, "rel-0003", dest=self.tmp), "INTEGRITY_ERROR")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_번들의_시스템_프롬프트_해시가_다르면_INTEGRITY_ERROR(self):
        from conformance.servers import sealed
        rel = self.srv.releases["rel-0001"]
        m = {k: v for k, v in rel["manifest"].items() if k != "content_hash"}
        m["adapters"] = {r: dict(v) for r, v in m["adapters"].items()}
        m["adapters"]["LORA_A"]["system_prompt"] = {"path": "system_prompt.txt", "sha256": "sha256:" + "1" * 64}
        rel["manifest"] = sealed(m)
        self.assertEqual(self.code(self.r.load_bundle, "rel-0001", dest=self.tmp), "INTEGRITY_ERROR")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_위험한_번들_tar(self):
        from conformance.servers import make_tar
        self.srv.overrides["/v1/releases/rel-0001/bundle"] = (200, "application/x-tar", make_tar({"../x": b"1"}))
        self.assertEqual(self.code(self.r.load_bundle, "rel-0001", dest=self.tmp / "d"), "INTEGRITY_ERROR")
        self.srv.overrides["/v1/releases/rel-0001/bundle"] = (200, "application/x-tar", make_tar({"manifest.json": b"{}"}))
        self.assertEqual(self.code(self.r.load_bundle, "rel-0001", dest=self.tmp / "d"), "INTEGRITY_ERROR")

    def test_게이트_쓰기(self):
        subj = example("GateSubmission")["subject"]
        s1 = self.g.submit_candidate(subj, requested_by_role="operator")
        self.assertEqual(self.g.submit_candidate(subj, requested_by_role="operator"), s1)  # 멱등
        p = self.g.activate("rel-0001", requested_by_role="operator")
        self.assertEqual((p["release_id"], p["pointer_version"]), ("rel-0001", 1))
        self.assertEqual(self.g.activate("rel-0001", requested_by_role="operator"), p)
        self.assertEqual(self.r.get_active_pointer(), p)
        self.assertEqual(self.code(self.g.activate, "rel-0002", requested_by_role="operator"), "FAILED_PRECONDITION")
        self.assertEqual(self.code(self.g.activate, "rel-9", requested_by_role="operator"), "NOT_FOUND")

    def test_롤백(self):
        self.g.activate("rel-0001", requested_by_role="operator")
        self.g.activate("rel-0003", requested_by_role="operator")
        req = example("RollbackRequest")
        req.update(from_release_id="rel-0003", to_release_id="rel-0001", requested_by_role="operator")
        rc = self.g.request_rollback(req)
        self.assertEqual(rc["status"], "APPLIED")
        self.assertEqual(self.g.request_rollback(req), rc)
        self.assertEqual(self.code(self.g.request_rollback, {"request_id": "x"}), "INVALID_RECORD")

    def test_역할_불일치와_읽기_토큰은_PERMISSION_DENIED(self):
        self.assertEqual(self.code(self.g.activate, "rel-0001", requested_by_role="model-lab"), "PERMISSION_DENIED")
        ro = HttpGateService(self.srv.url, READ)
        self.assertEqual(self.code(ro.activate, "rel-0001", requested_by_role="reader"), "PERMISSION_DENIED")
        subj = example("GateSubmission")["subject"]
        self.assertEqual(self.code(ro.submit_candidate, subj, requested_by_role="reader"), "PERMISSION_DENIED")
        req = example("RollbackRequest")
        self.assertEqual(self.code(ro.request_rollback, req), "PERMISSION_DENIED")

    def test_응답_스키마_위반은_INTEGRITY_ERROR(self):
        self.srv.pointer = {"release_id": "rel-0001"}
        self.assertEqual(self.code(self.r.get_active_pointer), "INTEGRITY_ERROR")


if __name__ == "__main__":
    unittest.main()


class Approval(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.g = HttpGateService(self.srv.url, WRITE)
        self.a = HttpGateService(self.srv.url, APPROVER)
        self.sub = self.g.submit_candidate(example("GateDecision.pass")["subject"], requested_by_role="operator")["submission_id"]

    def test_보고서와_결정(self):
        self.assertEqual(self.a.get_review_report(self.sub)["submission_id"], self.sub)
        ok = self.a.decide(self.sub, "APPROVE", approver_id="trainer-1", approver_role="release-approver")
        self.assertEqual(ok["decision"], "APPROVE")

    def test_제출_목록과_조회(self):
        items, nxt = self.g.list_submissions(status="AWAITING_APPROVAL")
        self.assertEqual([x["submission_id"] for x in items], [self.sub])
        self.assertEqual(self.g.get_submission(self.sub)["status"], "AWAITING_APPROVAL")
        self.assertEqual(self.g.list_submissions(status="PASSED")[0], [])
        with self.assertRaises(BoundaryError) as cm:
            self.g.get_submission("sub-99")
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_반려는_사유가_필요하고_권한이_있어야_한다(self):
        with self.assertRaises(BoundaryError) as cm:
            self.a.decide(self.sub, "REJECT", approver_id="trainer-1", approver_role="release-approver")
        self.assertEqual(cm.exception.code, "INVALID_RECORD")
        with self.assertRaises(BoundaryError) as cm:
            self.g.decide(self.sub, "APPROVE", approver_id="x", approver_role="operator")
        self.assertEqual(cm.exception.code, "PERMISSION_DENIED")
        with self.assertRaises(BoundaryError) as cm:
            self.a.get_review_report("sub-99")
        self.assertEqual(cm.exception.code, "NOT_FOUND")
