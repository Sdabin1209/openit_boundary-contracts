"""계약 2.0.0의 모델 입출력 스키마(ActionExtraction 계열, ResponseRequest, ResponseText)와 v1 폐기 시험."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from boundary_contracts import validator  # noqa: E402
from negatives_v2 import CASES  # noqa: E402

V2_PAIRS = [  # (스키마, 예시 이름 접두)
    ("ActionExtractionInput", "ActionExtractionInput"), ("ActionExtraction", "ActionExtraction"),
    ("ActionExtractionSample", "ActionExtractionSample"), ("ResponseRequest", "ResponseRequest"),
    ("ResponseSample", "ResponseSample"),
]


def ex(name):
    return copy.deepcopy(json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8")))


class V2Schemas(unittest.TestCase):
    def test_예시는_모두_통과한다(self):
        n = 0
        for schema, prefix in V2_PAIRS:
            files = sorted(p.stem for p in (ROOT / "examples").glob(f"{prefix}*.json") if p.stem.split(".")[0] == prefix)
            self.assertTrue(files, schema)
            for f in files:
                self.assertEqual(list(validator(schema).iter_errors(ex(f))), [], f)
                n += 1
        self.assertGreaterEqual(n, 17)

    def test_ResponseText는_문자열이다(self):
        v = validator("ResponseText")
        self.assertEqual(list(v.iter_errors(json.loads((ROOT / "examples" / "ResponseText.json").read_text(encoding="utf-8")))), [])
        self.assertTrue(list(v.iter_errors({"response_text": "x"})))
        self.assertTrue(list(v.iter_errors("")))

    def test_위반_변형은_모두_거부된다(self):
        for label, schema, base, mutate in CASES:
            d = ex(base)
            mutate(d)
            self.assertTrue(list(validator(schema).iter_errors(d)), label)

    def test_데이터에_있는_새_reason_4종을_받아들인다(self):
        for reason in ("OTHER_BEVERAGE", "MISSING_NUMBER", "UNPARSED_VALUE", "INVALID_OPTION"):
            d = ex("ActionExtraction.reask")
            d["reason"] = reason
            self.assertEqual(list(validator("ActionExtraction").iter_errors(d)), [], reason)

    def test_괄호_없는_술_키를_받아들인다(self):
        d = ex("ActionExtraction.reask")
        key = "Q7_1.amount"
        d["values"] = [{"key": key, "value": None, "precision": "unspecified", "status": "MISSING", "save": False}]
        d["targets"] = [key]
        d["reason"] = "BEVERAGE_MISSING"
        self.assertEqual(list(validator("ActionExtraction").iter_errors(d)), [])
        d["values"][0]["key"] = "Q7_1[beer].amount"
        self.assertEqual(list(validator("ActionExtraction").iter_errors(d)), [])
        d["values"][0]["key"] = "Q7_1[whisky].amount"  # 종류 코드는 5종뿐
        self.assertTrue(list(validator("ActionExtraction").iter_errors(d)))

    def test_부분_선채움_문항으로의_NEXT를_받아들인다(self):
        d = ex("ActionExtraction.next")
        d["values"] = [
            {"key": "Q4.answer", "value": True, "precision": "exact", "status": "ANSWERED", "save": True},
            {"key": "Q4_1.status", "value": "former", "precision": "exact", "status": "ANSWERED", "save": True}]
        d["next_item"] = "Q4_1"
        self.assertEqual(list(validator("ActionExtraction").iter_errors(d)), [])

    def test_targets가_없을_때는_키가_없다(self):
        d = ex("ActionExtraction.next")
        d["targets"] = []
        self.assertTrue(list(validator("ActionExtraction").iter_errors(d)))  # 빈 배열이 아니라 키 자체를 뺀다

    def test_CONFIRM의_next_item은_입력_문항과_달라도_된다(self):
        d = ex("ActionExtraction.confirm")
        self.assertEqual(list(validator("ActionExtraction").iter_errors(d)), [])


class V1Retired(unittest.TestCase):
    def test_v1_샘플_스키마와_예시가_없다(self):
        for n in ("ParserSample", "GeneratorSample"):
            self.assertFalse((ROOT / "boundary_contracts" / "schemas" / f"{n}.schema.json").exists(), n)
            self.assertFalse((ROOT / "examples" / f"{n}.json").exists(), n)

    def test_v1_역할_이름은_거부된다(self):
        m = ex("DatasetManifest")
        m["files"][0]["role"] = "PARSER"
        self.assertTrue(list(validator("DatasetManifest").iter_errors(m)))
        m["files"][0]["role"] = "LORA_B"
        self.assertEqual(list(validator("DatasetManifest").iter_errors(m)), [])
        f = ex("FailureCase")
        f["expected_kind"] = "GENERATOR"
        self.assertTrue(list(validator("FailureCase").iter_errors(f)))

    def test_FailureCase_expected는_A는_객체_B는_문자열(self):
        f = ex("FailureCase")
        f["expected_kind"], f["expected"] = "LORA_A", ex("ActionExtraction.next")
        self.assertEqual(list(validator("FailureCase").iter_errors(f)), [])
        f["expected_kind"], f["expected"] = "LORA_B", "네, 알겠습니다."
        self.assertEqual(list(validator("FailureCase").iter_errors(f)), [])

    def test_저장소_문서에_v1_이름이_남지_않았다(self):
        # 마이그레이션 설명(CHANGELOG, V2_DRAFT)과 이 시험을 빼고, 스키마·코드·예시에 v1 이름이 없어야 한다.
        dead = ("ParserSample", "GeneratorSample", "ParserOutput", "GeneratorOutput", "UtteranceParserInput", "ResponseGeneratorInput")
        for base in (ROOT / "boundary_contracts", ROOT / "conformance", ROOT / "examples"):
            for p in base.rglob("*"):
                if p.is_file() and p.suffix in (".py", ".json") and "__pycache__" not in p.parts:
                    text = p.read_text(encoding="utf-8")
                    for w in dead:
                        self.assertNotIn(w, text, f"{p}: {w}")


if __name__ == "__main__":
    unittest.main()


class V21Additions(unittest.TestCase):
    """2.1.0 추가형 변경: 옛 레코드(새 필드 없음)도 통과하고, 새 필드는 열거를 지킨다."""

    def test_옛_StaffAlert와_SessionState는_그대로_통과(self):
        from boundary_contracts import validator
        a = {"alert_id": "al-1", "session_id": "s1", "kind": "RISK_STOP", "created_at": "2026-10-15T00:00:00Z", "status": "OPEN"}
        self.assertEqual(list(validator("StaffAlert").iter_errors(a)), [])
        self.assertEqual(list(validator("SessionState").iter_errors({"session_id": "s1", "state": "ACTIVE", "resume_text": None})), [])

    def test_pause_reason_열거(self):
        from boundary_contracts import validator
        for v in ("RISK", "REASK_LIMIT", "OTHER", None):
            self.assertEqual(list(validator("SessionState").iter_errors({"session_id": "s1", "state": "PAUSED_RISK", "resume_text": None, "pause_reason": v})), [])
        self.assertTrue(list(validator("SessionState").iter_errors({"session_id": "s1", "state": "PAUSED_RISK", "resume_text": None, "pause_reason": "X"})))
