import unittest

from boundary_contracts import BoundaryError, validator
from boundary_contracts.clients import HttpPublicApi, HttpStaffCall
from conformance.servers import PublicApiReferenceServer

K1, K2, STAFF = "fake-kiosk-1", "fake-kiosk-2", "fake-staff"


class PublicApi(unittest.TestCase):
    def setUp(self):
        self.srv = PublicApiReferenceServer({K1: "kiosk-1", K2: "kiosk-2", STAFF: "staff"}).start()
        self.addCleanup(self.srv.stop)
        self.c = HttpPublicApi(self.srv.url, K1)
        self.other = HttpPublicApi(self.srv.url, K2)
        self.staff = HttpPublicApi(self.srv.url, STAFF)

    def err(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception

    def test_세션_흐름과_상태(self):
        r = self.c.start_session("s1", subject_ref="visit#123")
        self.assertTrue(r["response_text"])
        self.assertIsNone(r["turn_failure_signal"])
        self.assertEqual(self.srv.states["s1"]["subject_ref"], "visit#123")
        self.assertEqual(self.c.send_utterance("s1", "아니요", "t1")["response_text"], "다음 질문입니다.")
        st = self.c.get_state("s1")
        self.assertEqual(list(validator("SessionState").iter_errors(st)), [])
        self.assertEqual(st["state"], "ACTIVE")
        self.assertIsNone(self.c.end_session("s1")["response_text"])
        self.assertEqual(self.c.get_state("s1")["state"], "ENDED")
        self.assertTrue(self.c.healthz())

    def test_같은_turn_id는_한_번만_처리(self):
        self.c.start_session("s1")
        a = self.c.send_utterance("s1", "네", "t1")
        self.assertEqual(self.c.send_utterance("s1", "네", "t1"), a)
        self.assertEqual(self.srv.processed, ["t1"])
        self.assertEqual(self.err(self.c.send_utterance, "s1", "다른 말", "t1").code, "CONFLICT")

    def test_확정되지_못한_턴은_같은_turn_id로_다시_처리(self):
        self.c.start_session("s1")
        self.srv.turn_fn = lambda u: (None, False, False)
        r = self.c.send_utterance("s1", "네", "t1")
        self.assertEqual(r["turn_failure_signal"]["write_committed"], "NOT_COMMITTED")
        self.srv.turn_fn = lambda u: ("다음 질문입니다.", True, False)
        r = self.c.send_utterance("s1", "네", "t1")
        self.assertIsNone(r["turn_failure_signal"])
        self.assertEqual(self.srv.processed, ["t1", "t1"])

    def test_처리_중인_turn_id는_409_TURN_IN_PROGRESS(self):
        self.c.start_session("s1")
        self.srv.states["s1"]["inflight"].add("t1")
        e = self.err(self.c.send_utterance, "s1", "네", "t1")
        self.assertEqual((e.code, e.details["reason"]), ("CONFLICT", "TURN_IN_PROGRESS"))

    def test_끝난_세션에_발화는_409(self):
        self.c.start_session("s1")
        self.c.end_session("s1")
        self.assertEqual(self.err(self.c.send_utterance, "s1", "네", "t1").code, "CONFLICT")

    def test_기기_토큰_소유_확인(self):
        self.c.start_session("s1")
        self.assertEqual(self.err(self.other.get_state, "s1").code, "NOT_FOUND")       # 다른 기기는 404
        self.assertEqual(self.err(self.other.send_utterance, "s1", "네", "t1").code, "NOT_FOUND")
        self.assertEqual(self.err(self.staff.get_state, "s1").code, "PERMISSION_DENIED")  # 직원 토큰은 403
        self.assertEqual(self.err(self.c.get_state, "nope").code, "NOT_FOUND")
        self.assertEqual(self.err(self.c.start_session, "s1").code, "CONFLICT")
        self.assertEqual(self.err(HttpPublicApi(self.srv.url, "fake-wrong").get_state, "s1").code, "PERMISSION_DENIED")

    def test_입력_검사(self):
        self.assertEqual(self.err(self.c.start_session, "bad id!").code, "INVALID_RECORD")
        self.assertEqual(self.err(self.c.start_session, "s1", subject_ref="한글").code, "INVALID_RECORD")
        self.assertEqual(self.err(self.c.send_utterance, "s1", "네", "").code, "INVALID_RECORD")
        self.assertEqual(self.err(self.c.intervene, "s1", "MAYBE", "t").code, "INVALID_RECORD")

    def test_위험_정지와_개입_결정(self):
        self.c.start_session("s1")
        self.srv.turn_fn = lambda u: ("잠시 기다려 주세요.", True, True)
        r = self.c.send_utterance("s1", "가슴이 아파요", "t1")
        self.assertEqual(r["response_text"], "잠시 기다려 주세요.")
        st = self.c.get_state("s1")
        self.assertEqual((st["state"], st["pause_reason"]), ("PAUSED_RISK", "RISK"))
        self.assertEqual(self.err(self.c.intervene, "s1", "RESUME", "i0").code, "PERMISSION_DENIED")  # 키오스크 토큰은 403
        out = self.staff.intervene("s1", "RESUME", "i1")
        self.assertTrue(out["response_text"])
        self.assertEqual(self.staff.intervene("s1", "RESUME", "i1"), out)  # 같은 turn_id 재전송
        st = self.c.get_state("s1")
        self.assertEqual((st["state"], st["resume_text"] is not None), ("ACTIVE", True))
        self.assertEqual(self.srv.alerts["s1"]["status"], "RESOLVED")
        self.srv.turn_fn = lambda u: ("다음 질문입니다.", True, False)
        self.c.send_utterance("s1", "네", "t2")
        self.assertIsNone(self.c.get_state("s1")["resume_text"])  # 다음 발화가 접수되면 null
        self.assertEqual(self.err(self.staff.intervene, "s1", "END", "i2").code, "CONFLICT")  # 멈추지 않은 세션

    def test_직원_알림_재알림이_같은_서버에서_동작(self):
        self.c.start_session("s1")
        self.srv.turn_fn = lambda u: ("잠시만요.", True, True)
        self.c.send_utterance("s1", "x", "t1")
        r = HttpStaffCall(self.srv.url, K1).retry("s1", "r1")
        self.assertEqual(r["alert_id"], "al-s1")


class DeviceHeader(unittest.TestCase):
    """2.3.0(ADR 0012): 키오스크는 게이트웨이가 확인한 X-Openit-Device로 식별된다. 기대값은 PUBLIC_API.md F절."""
    def setUp(self):
        self.srv = PublicApiReferenceServer({STAFF: "staff"}).start()
        self.a = HttpPublicApi(self.srv.url, device_id="kiosk-a")
        self.b = HttpPublicApi(self.srv.url, device_id="kiosk-b")

    def tearDown(self):
        self.srv.stop()

    def test_기기_헤더로_세션을_쓴다(self):
        self.a.start_session("s1")
        self.assertEqual(self.a.get_state("s1")["state"], "ACTIVE")
        self.assertEqual(self.srv.requests[-1][2], "kiosk:kiosk-a")   # 토큰 없이 기기 헤더로 식별됐다

    def test_다른_기기는_404(self):
        self.a.start_session("s1")
        with self.assertRaises(BoundaryError) as cm:
            self.b.get_state("s1")
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_자격이_없으면_거부(self):
        with self.assertRaises(BoundaryError) as cm:
            HttpPublicApi(self.srv.url).start_session("s1")
        self.assertEqual(cm.exception.code, "PERMISSION_DENIED")

    def test_기기_ID_형식(self):
        with self.assertRaises(ValueError):
            HttpPublicApi(self.srv.url, device_id="bad id")
