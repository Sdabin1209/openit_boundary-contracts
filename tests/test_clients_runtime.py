import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from _fixtures import READ, TOKENS, WRITE, example  # noqa: E402
from boundary_contracts import BoundaryError  # noqa: E402
from boundary_contracts.clients import HttpModelRuntime, is_output_invalid  # noqa: E402
from conformance.servers import RuntimeReferenceServer  # noqa: E402


class Runtime(unittest.TestCase):
    def setUp(self):
        self.srv = RuntimeReferenceServer(TOKENS).start()
        self.addCleanup(self.srv.stop)
        self.srv.available.update({"rel-0001": "ok", "rel-slow": "loading", "rel-bad": "not_pass"})
        self.c = HttpModelRuntime(self.srv.url, WRITE)
        self.reader = HttpModelRuntime(self.srv.url, READ)

    def code(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception.code

    # ---- 적재 ----
    def test_적재는_멱등이고_LOADING_뒤_LOADED(self):
        self.assertEqual(self.c.get_release_state("rel-slow")["state"], "ABSENT")
        self.assertEqual(self.c.load_release("rel-slow")["state"], "LOADING")
        self.assertEqual(self.c.load_release("rel-slow")["state"], "LOADED")
        self.assertEqual(self.c.load_release("rel-slow")["state"], "LOADED")
        self.assertEqual(self.c.get_release_state("rel-slow")["state"], "LOADED")
        self.assertIn("rel-slow", self.c.info()["loaded"])

    def test_적재_오류(self):
        self.assertEqual(self.code(self.c.load_release, "rel-bad"), "FAILED_PRECONDITION")
        self.assertEqual(self.code(self.c.load_release, "rel-none"), "NOT_FOUND")
        self.assertEqual(self.code(self.reader.load_release, "rel-0001"), "PERMISSION_DENIED")
        self.assertEqual(self.code(self.c.load_release, "../x"), "INVALID_RECORD")

    # ---- extract (LoRA-A) ----
    def test_extract는_ActionExtraction을_돌려준다(self):
        self.c.load_release("rel-0001")
        r = self.c.extract("rel-0001", example("ActionExtractionInput.next"))
        self.assertEqual(r.output, example("ActionExtraction.next"))
        self.assertEqual((r.outcome, r.attempts, r.protections, r.is_fallback), ("ok", 1, {}, False))

    def test_flow를_주면_ExtractRequest로_보내고_서버가_규칙을_보증한다(self):
        # 기대: HTTP.md I9(2.2.0) — flow가 있으면 본문은 ExtractRequest, 규칙 위반 출력은 503 OUTPUT_INVALID
        from boundary_contracts.action_rules import item_of
        self.c.load_release("rel-0001")
        inp = example("ActionExtractionInput.next")
        good = example("ActionExtraction.reask")
        good["next_item"] = inp["question_id"]          # REASK의 next_item은 입력 question_id(규칙 명세)
        items = [inp["question_id"]] + [item_of(v["key"]) for v in good["values"]] + [item_of(t) for t in good.get("targets", [])]
        flow = {"order": list(dict.fromkeys(items)) + ["Q99"], "skips": []}
        self.srv.extract_fn = lambda req: good
        self.assertEqual(self.c.extract("rel-0001", inp, flow=flow).output, good)
        bad = dict(good, next_item="Q99")               # REASK인데 다른 문항: 규칙 위반 -> 서버가 내지 않는다
        self.srv.extract_fn = lambda req: bad
        with self.assertRaises(BoundaryError) as cm:
            self.c.extract("rel-0001", inp, flow=flow)
        self.assertTrue(is_output_invalid(cm.exception))
        # flow 없는 호환 본문은 규칙을 보지 않는다(형식만)
        self.assertEqual(self.c.extract("rel-0001", inp).output["next_item"], "Q99")

    def test_flow가_계약을_어기면_보내지_않는다(self):
        self.c.load_release("rel-0001")
        n = len(self.srv.requests)
        er = example("ExtractRequest")
        self.assertEqual(self.code(self.c.extract, "rel-0001", er["input"], flow={"order": []}), "INVALID_RECORD")
        self.assertEqual(len(self.srv.requests), n)

    def test_적재되지_않은_릴리스는_404(self):
        self.assertEqual(self.code(self.c.extract, "rel-0001", example("ActionExtractionInput.next")), "NOT_FOUND")
        self.assertEqual(self.code(self.c.respond, "rel-0001", example("ResponseRequest.start")), "NOT_FOUND")

    def test_extract_입력은_보내기_전에_검증한다(self):
        self.c.load_release("rel-0001")
        n = len(self.srv.requests)
        self.assertEqual(self.code(self.c.extract, "rel-0001", {"question_id": "Q1.D01"}), "INVALID_RECORD")
        self.assertEqual(self.code(self.c.extract, "rel-0001", example("ResponseRequest.start")), "INVALID_RECORD")
        self.assertEqual(len(self.srv.requests), n)

    def test_서버도_입력을_검증한다(self):
        self.c.load_release("rel-0001")
        with self.assertRaises(BoundaryError) as cm:
            self.c._json("POST", "/v1/releases/rel-0001/extract", body={"question_id": "Q1.D01"})
        self.assertEqual(cm.exception.code, "INVALID_RECORD")

    def test_서버_출력이_형식을_어기면_503_OUTPUT_INVALID(self):
        # D75: 서버는 값을 지어내지 않는다. 대체 출력 없이 UNAVAILABLE(재시도 가능)이다.
        self.c.load_release("rel-0001")
        bad = example("ActionExtraction.next")
        bad["reason"] = "MISSING"  # NEXT에는 reason이 없다
        self.srv.extract_fn = lambda req: bad
        with self.assertRaises(BoundaryError) as cm:
            self.c.extract("rel-0001", example("ActionExtractionInput.next"))
        self.assertEqual(cm.exception.code, "UNAVAILABLE")
        self.assertTrue(cm.exception.retryable)
        self.assertEqual(cm.exception.details["reason"], "OUTPUT_INVALID")
        self.assertTrue(is_output_invalid(cm.exception))
        self.srv.extract_fn = lambda req: example("ActionExtraction.next")  # 다음 호출은 정상(상태가 남지 않는다)
        self.assertEqual(self.c.extract("rel-0001", example("ActionExtractionInput.next")).outcome, "ok")

    def test_다른_UNAVAILABLE은_OUTPUT_INVALID가_아니다(self):
        self.assertFalse(is_output_invalid(BoundaryError("UNAVAILABLE", "x")))
        self.assertFalse(is_output_invalid(BoundaryError("NOT_FOUND", "x", {"reason": "OUTPUT_INVALID"})))

    def test_서버가_계약을_어긴_본문을_내면_클라이언트가_INTEGRITY_ERROR(self):
        self.c.load_release("rel-0001")
        path = "/v1/releases/rel-0001/extract"
        bad = example("ActionExtraction.next")
        bad["reason"] = "MISSING"
        bad2 = example("ActionExtraction.next")
        bad2["unknown_field"] = 1  # 모델 출력은 읽기 모드 완화를 하지 않는다
        for body in (bad, bad2):
            self.srv.overrides[path] = (200, "application/json", json.dumps(body).encode(), {"X-Openit-Outcome": "ok"})
            self.assertEqual(self.code(self.c.extract, "rel-0001", example("ActionExtractionInput.next")), "INTEGRITY_ERROR")

    # ---- respond (LoRA-B) ----
    def test_respond는_문장_그대로를_돌려준다(self):
        self.c.load_release("rel-0001")
        r = self.c.respond("rel-0001", example("ResponseRequest.start"))
        self.assertIsInstance(r.output, str)
        self.assertEqual(r.output, "네, 알겠습니다. 다음 질문을 드리겠습니다.")
        self.assertEqual(r.outcome, "ok")
        self.assertFalse(r.is_fallback)

    def test_대체_응답은_헤더로_알린다(self):
        self.c.load_release("rel-0001")
        self.srv.respond_fn = lambda req: ("다음 질문입니다.", "fallback")
        self.srv.attempts, self.srv.protections = 3, "G5:1,G2:2"
        r = self.c.respond("rel-0001", example("ResponseRequest.reask"))
        self.assertEqual((r.output, r.outcome, r.attempts, r.protections), ("다음 질문입니다.", "fallback", 3, {"G5": 1, "G2": 2}))
        self.assertTrue(r.is_fallback)

    def test_respond_잘못된_응답(self):
        self.c.load_release("rel-0001")
        path = "/v1/releases/rel-0001/respond"
        ok_h = {"X-Openit-Outcome": "ok"}
        cases = {
            "JSON으로 감쌈": (200, "application/json", b'{"response_text":"x"}', ok_h),
            "빈 문장": (200, "text/plain; charset=utf-8", b"", ok_h),
            "UTF-8 아님": (200, "text/plain; charset=utf-8", b"\xff\xfe", ok_h),
            "Outcome 없음": (200, "text/plain; charset=utf-8", "네".encode(), {}),
            "Outcome 값 이상": (200, "text/plain; charset=utf-8", "네".encode(), {"X-Openit-Outcome": "repaired"}),
            "Attempts 이상": (200, "text/plain; charset=utf-8", "네".encode(), {**ok_h, "X-Openit-Attempts": "0"}),
            "Protections 이상": (200, "text/plain; charset=utf-8", "네".encode(), {**ok_h, "X-Openit-Protections": "bad"}),
        }
        for label, resp in cases.items():
            self.srv.overrides[path] = resp
            self.assertEqual(self.code(self.c.respond, "rel-0001", example("ResponseRequest.start")), "INTEGRITY_ERROR", label)

    def test_respond_입력은_보내기_전에_검증한다(self):
        self.c.load_release("rel-0001")
        bad = example("ResponseRequest.start")
        bad["user_utterance"] = "START에는 없다"
        self.assertEqual(self.code(self.c.respond, "rel-0001", bad), "INVALID_RECORD")

    def test_토큰이_없거나_틀리면_403(self):
        self.assertEqual(self.code(HttpModelRuntime(self.srv.url, "wrong").load_release, "rel-0001"), "PERMISSION_DENIED")

    def test_읽기_토큰은_추론은_되지만_적재는_안_된다(self):
        self.c.load_release("rel-0001")
        r = self.reader.extract("rel-0001", example("ActionExtractionInput.next"))
        self.assertEqual(r.outcome, "ok")

    def test_추론은_부작용이_없다(self):
        self.c.load_release("rel-0001")
        a = self.c.extract("rel-0001", example("ActionExtractionInput.next"))
        b = self.c.extract("rel-0001", example("ActionExtractionInput.next"))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
