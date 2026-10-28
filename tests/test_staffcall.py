import unittest

from _fixtures import READ
from boundary_contracts import BoundaryError, validator
from boundary_contracts.clients import HttpStaffCall
from conformance.servers import StaffCallReferenceServer

K1, K2, STAFF = "fake-kiosk-1", "fake-kiosk-2", "fake-staff"


class StaffCall(unittest.TestCase):
    def setUp(self):
        self.srv = StaffCallReferenceServer({K1: "kiosk-1", K2: "kiosk-2", STAFF: "staff"}, retry_after_s=30, max_retries=2).start()
        self.addCleanup(self.srv.stop)
        self.t = [1000.0]
        self.srv.clock = lambda: self.t[0]
        self.srv.add_alert("s1", "kiosk-1")
        self.c = HttpStaffCall(self.srv.url, K1)

    def err(self, fn, *a):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a)
        return cm.exception

    def test_재알림은_같은_alert_id로_횟수를_늘린다(self):
        r = self.c.retry("s1", "t1")
        self.assertEqual((r["alert_id"], r["staff_alert"], r["delivery_attempts"], r["retry_after_s"]), ("al-s1", "DELIVERED", 2, 30))
        self.assertEqual(self.srv.alerts["s1"]["last_delivery_status"], "DELIVERED")

    def test_같은_turn_id는_멱등(self):
        a = self.c.retry("s1", "t1")
        self.assertEqual(self.c.retry("s1", "t1"), a)
        self.assertEqual(self.srv.alerts["s1"]["delivery_attempts"], 2)

    def test_간격_하한은_429와_retry_after(self):
        self.c.retry("s1", "t1")
        e = self.err(self.c.retry, "s1", "t2")
        self.assertEqual(e.code, "UNAVAILABLE")
        self.assertEqual(e.details["reason"], "TOO_SOON")
        self.assertGreater(e.details["retry_after_s"], 0)
        self.t[0] += 31
        self.assertEqual(self.c.retry("s1", "t2")["delivery_attempts"], 3)

    def test_횟수_상한(self):
        for i in range(2):
            self.c.retry("s1", f"t{i}")
            self.t[0] += 31
        self.assertEqual(self.err(self.c.retry, "s1", "tx").details["reason"], "RETRY_LIMIT")

    def test_OPEN_알림이_없으면_409(self):
        self.srv.alerts["s1"]["status"] = "RESOLVED"
        e = self.err(self.c.retry, "s1", "t1")
        self.assertEqual((e.code, e.details["reason"]), ("CONFLICT", "NO_OPEN_ALERT"))

    def test_전달_실패도_결과로_돌려준다(self):
        self.srv.deliver_fn = lambda: "DELIVERY_FAILED"
        self.assertEqual(self.c.retry("s1", "t1")["staff_alert"], "DELIVERY_FAILED")

    def test_실패_기록(self):
        a = self.c.report("s1", "NOT_NOTIFIED", "r1")
        self.assertEqual((a["manual_notice_outcome"], a["status"]), ("NOT_NOTIFIED", "OPEN"))
        self.assertTrue(a["manual_notice_reported_at"])
        self.assertEqual(list(validator("StaffAlert").iter_errors(a)), [])
        self.assertEqual(self.c.report("s1", "NOT_NOTIFIED", "r1"), a)  # 멱등
        self.assertEqual(self.err(self.c.report, "s1", "STAFF_NOTIFIED_MANUALLY", "r1").code, "CONFLICT")
        self.assertEqual(self.c.report("s1", "STAFF_NOTIFIED_MANUALLY", "r2")["manual_notice_outcome"], "STAFF_NOTIFIED_MANUALLY")

    def test_다른_기기와_직원은_거부(self):
        self.assertEqual(self.err(HttpStaffCall(self.srv.url, K2).retry, "s1", "t").code, "NOT_FOUND")
        self.assertEqual(self.err(HttpStaffCall(self.srv.url, K2).report, "s1", "NOT_NOTIFIED", "t").code, "NOT_FOUND")
        self.assertEqual(self.err(HttpStaffCall(self.srv.url, STAFF).retry, "s1", "t").code, "PERMISSION_DENIED")
        self.assertEqual(self.err(HttpStaffCall(self.srv.url, "bad").retry, "s1", "t").code, "PERMISSION_DENIED")
        self.assertEqual(self.err(self.c.retry, "nope", "t").code, "NOT_FOUND")

    def test_본문_검증(self):
        self.assertEqual(self.err(self.c.report, "s1", "MAYBE", "t").code, "INVALID_RECORD")  # 클라이언트 사전 검증
        e = self.err(self.c._json, "POST", "/v1/sessions/s1/staff-call/retry", None, {"turn_id": "t", "free_text": "x"})
        self.assertEqual(e.code, "INVALID_RECORD")  # 서버 검증: 자유 문장 필드 거부

    def test_모르는_pause_reason_값도_읽는다(self):
        self.srv.alerts["s1"]["pause_reason"] = "SOMETHING_NEW"
        self.assertEqual(self.c.report("s1", "NOT_NOTIFIED", "r9")["pause_reason"], "SOMETHING_NEW")

    def test_JSON_본문이_아니면_400(self):
        self.assertEqual(self.err(self.c._json, "POST", "/v1/sessions/s1/staff-call/report", None, [1]).code, "INVALID_RECORD")


if __name__ == "__main__":
    unittest.main()
