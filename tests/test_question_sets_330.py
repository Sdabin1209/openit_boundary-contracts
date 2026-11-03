"""3.3.0 문진표 여러 개·세션별 선택(규칙 D104, 사용자 결정 2026-11-03): 건너뛰기 연산자, 공개 API 문진표 목록과 SESSION_START, 예시 검증."""
import json
import unittest
from pathlib import Path

from boundary_contracts import BoundaryError, validator
from boundary_contracts.action_rules import holds
from boundary_contracts.clients import HttpPublicApi
from conformance.servers import PublicApiReferenceServer

ROOT = Path(__file__).resolve().parents[1]
K1 = "fake-kiosk-1"


class Holds(unittest.TestCase):
    def test_six_operators(self):
        self.assertTrue(holds(0, "==", 0)); self.assertFalse(holds(False, "==", 0))      # bool != 수
        self.assertTrue(holds(1, "!=", 0)); self.assertTrue(holds(True, "!=", 1))
        self.assertTrue(holds(3, ">", 2)); self.assertFalse(holds(2, ">", 2))
        self.assertTrue(holds(2, ">=", 2)); self.assertTrue(holds(1, "<", 2)); self.assertTrue(holds(2, "<=", 2))
        self.assertFalse(holds("a", ">", 1)); self.assertFalse(holds(True, ">=", 0))        # 크기 비교는 수끼리만
        self.assertTrue(holds("soju", "==", "soju"))

    def test_flow_table_examples(self):
        v = validator("QuestionFlowTable")
        self.assertEqual(list(v.iter_errors(json.loads((ROOT / "examples" / "QuestionFlowTable.json").read_text()))), [])
        bad = json.loads((ROOT / "conformance" / "examples_invalid" / "QuestionFlowTable.bad-op.json").read_text())
        self.assertTrue(list(v.iter_errors(bad)))


class PublicApiQuestionSets(unittest.TestCase):
    def setUp(self):
        self.srv = PublicApiReferenceServer({K1: "kiosk-1"}).start()
        self.c = HttpPublicApi(self.srv.url, K1)

    def tearDown(self):
        self.srv.stop()

    def test_single_active_set_allows_omission(self):
        self.assertEqual([x["question_set_id"] for x in self.c.list_question_sets()], ["qs-main"])
        self.c.start_session("s1")
        self.assertEqual(self.srv.states["s1"]["question_set_id"], "qs-main")

    def test_two_active_sets_require_choice(self):
        self.srv.question_sets_active.append({"question_set_id": "qs-b", "title": "순서 B", "version": "1"})
        with self.assertRaises(BoundaryError) as cm:
            self.c.start_session("s1")
        self.assertEqual((cm.exception.code, cm.exception.details.get("reason")), ("INVALID_RECORD", "QUESTION_SET_REQUIRED"))
        with self.assertRaises(BoundaryError) as cm:
            self.c.start_session("s1", question_set_id="qs-none")
        self.assertEqual(cm.exception.details.get("reason"), "UNKNOWN_QUESTION_SET")
        self.c.start_session("s1", question_set_id="qs-b")
        self.assertEqual(self.srv.states["s1"]["question_set_id"], "qs-b")
        with self.assertRaises(BoundaryError):
            self.c.start_session("s2", question_set_id="bad id")


class Examples330(unittest.TestCase):
    def test_new_fields_validate(self):
        for name, ex in (("ReleaseManifest", "ReleaseManifest"), ("GateSubmissionRequest", "GateSubmissionRequest"),
                         ("DeviceConfig", "DeviceConfig.full"), ("KioskStartFragment", "KioskStartFragment.with-question-set")):
            d = json.loads((ROOT / "examples" / f"{ex}.json").read_text())
            self.assertEqual(list(validator(name).iter_errors(d)), [], name)
        m = json.loads((ROOT / "examples" / "ReleaseManifest.json").read_text())
        self.assertEqual([q["title"] for q in m["question_sets"]], ["건강검진 문진표", "음주 문진표"])
        m["question_set"] = m["question_sets"][0]
        self.assertTrue(list(validator("ReleaseManifest").iter_errors(m)))   # 옛 단수 필드는 거부


if __name__ == "__main__":
    unittest.main()
