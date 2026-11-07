"""3.7.0 비식별 뷰(생성물): 저장본이 생성물과 같고, 자유 문장·모르는 키·허용 경로 밖 원문·가명 아닌 식별자를 거부한다(2026-11-07 Codex 반례)."""
import copy
import json
import pathlib
import subprocess
import sys
import unittest

from boundary_contracts import validator

ROOT = pathlib.Path(__file__).resolve().parents[1]


def ex(name):
    return json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))


def errs(schema, doc):
    return list(validator(schema).iter_errors(doc))


class DeidView(unittest.TestCase):
    def test_저장본은_생성물과_같다(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools/gen_deid_view.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_예시는_통과(self):
        for n in ("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace.failure-signal", "OpsFeedbackReviewTrace", "OpsFeedbackReviewTrace.utterance"):
            self.assertEqual(errs(n.split(".")[0], ex(n)), [], n)

    def bad(self, schema, base, mutate, why):
        d = copy.deepcopy(ex(base)); mutate(d)
        self.assertTrue(errs(schema, d), "거부되어야 함: " + why)

    def test_자유_객체에_문장(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d["extract_input"]["state"].update(note="홍길동 010-1234-5678"), "extract_input.state 는 비워진다")

    def test_마스킹_칸에_원문(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d["extract_input"].update(user_utterance="두통이 있어요"), "자유 문자열은 [MASKED]")

    def test_모르는_안쪽_키(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d["extract_input"].update(extra="x"), "모르는 키는 제거된다")

    def test_식별자는_가명만(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d.update(session_id="sess-raw-1"), "session_id 는 의사 식별자")
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d.update(session_id="[MASKED]"), "session_id 는 마스킹하지 않는다(조회·삭제 키)")

    def test_keep_키는_패턴(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d["extract_input"].update(question_id="홍길동 문항"), "question_id 는 식별자 모양 또는 [MASKED]")

    def test_건수_맵_키(self):
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d.update(extract_protections={"홍길동": 1}), "건수 맵 키 패턴")
        self.bad("OpsFeedbackDeidentifiedTrace", "OpsFeedbackDeidentifiedTrace", lambda d: d.update(extract_protections={"R1": -1}), "건수는 0 이상")

    def test_검토_사본_원문은_두_경로만(self):
        self.bad("OpsFeedbackReviewTrace", "OpsFeedbackReviewTrace", lambda d: d["log_entry"]["input"].update(utterance="고혈압 진단은 받았는데"), "log_entry.input.utterance 는 원문 허용 경로가 아니다")
        d = ex("OpsFeedbackReviewTrace.utterance"); d["extract_input"]["user_utterance"] = "가" * 1001
        self.assertTrue(errs("OpsFeedbackReviewTrace", d), "원문 상한 1000자")

    def test_비식별_뷰는_원문을_전혀_허용하지_않는다(self):
        self.assertTrue(errs("OpsFeedbackDeidentifiedTrace", ex("OpsFeedbackReviewTrace.utterance")), "검토 사본의 원문은 비식별 뷰에서 거부")


if __name__ == "__main__":
    unittest.main()
