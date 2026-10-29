"""LoRA-A 출력 의미 규칙 해석기(ADR 0010) 시험.

1부: 규칙 명세 데이터의 형식과, 명세에서 직접 읽을 수 있는 규칙을 손으로 적은 사례로 확인한다.
     기대값은 이 파일에 적은 규칙 문장(IO_SPEC/INTERFACES I8의 서술)에서 왔고 구현에서 가져오지 않았다.
2부: 이전 구현(turn-engine validate_extraction)과의 차이 시험. 이전 구현을 쓸 수 있을 때만 돈다.
     이것은 '이전 구현과 같다'는 확인이지 규칙이 옳다는 증거가 아니다(옳음은 1부 사례가 본다).
"""
import json
import random
import unittest

from boundary_contracts import validator
from boundary_contracts.action_rules import check_action_extraction, item_of, load_rules, slot_of

FLOW = {
    "flow_id": "t", "order": ["Q1", "Q4", "Q4_1", "Q5", "Q8_1", "Q8_2", "Q9"],
    "skips": [{"slot": "Q4.answer", "op": "==", "value": False, "skip_item": "Q4_1"},
              {"slot": "Q8_1.days", "op": "==", "value": 0, "skip_item": "Q8_2"}],
}


def inp(q):
    return {"question_id": q, "current_question": "질문", "user_utterance": "답", "state": {}}


def val(key, status="ANSWERED", value=True, save=None):
    return {"key": key, "status": status, "value": value, "save": status in ("ANSWERED", "CORRECTION") if save is None else save}


def codes(i, o):
    return sorted({v.code for v in check_action_extraction(i, o, FLOW)})


class RulesSpecTest(unittest.TestCase):
    def test_spec_matches_its_schema(self):
        self.assertEqual(load_rules()["rules_version"], "2")

    def test_key_helpers(self):
        self.assertEqual(item_of("Q7[soju].amount"), "Q7")
        self.assertEqual(item_of("Q4_1.status"), "Q4_1")
        self.assertEqual(slot_of("Q7[soju].amount"), "Q7.amount")

    def test_valid_next(self):
        o = {"action": "NEXT", "values": [val("Q4.answer", value=True)], "next_item": "Q4_1"}
        self.assertEqual(codes(inp("Q4"), o), [])

    def test_skip_applies(self):
        o = {"action": "NEXT", "values": [val("Q4.answer", value=False)], "next_item": "Q5"}
        self.assertEqual(codes(inp("Q4"), o), [])

    def test_skipped_item_asked_is_skip_order_mismatch(self):
        o = {"action": "NEXT", "values": [val("Q4.answer", value=False)], "next_item": "Q4_1"}
        self.assertEqual(codes(inp("Q4"), o), ["SKIP_ORDER_MISMATCH"])

    def test_save_rule(self):
        o = {"action": "REASK", "values": [val("Q4.answer", status="UNCLEAR", value=True, save=False)], "next_item": "Q4"}
        self.assertEqual(codes(inp("Q4"), o), ["SAVE_RULE"])
        o = {"action": "REASK", "values": [val("Q4.answer", status="UNCLEAR", value=None, save=True)], "next_item": "Q4"}
        self.assertEqual(codes(inp("Q4"), o), ["SAVE_RULE"])
        o = {"action": "NEXT", "values": [val("Q4.answer", value=None)], "next_item": "Q4_1"}
        self.assertIn("SAVE_RULE", codes(inp("Q4"), o))

    def test_reask_must_stay(self):
        o = {"action": "REASK", "values": [val("Q4.answer", status="MISSING", value=None)], "next_item": "Q5"}
        self.assertEqual(codes(inp("Q4"), o), ["NEXT_ITEM_MISMATCH"])

    def test_confirm_next_is_target_item(self):
        o = {"action": "CONFIRM", "values": [val("Q1.x")], "targets": ["Q1.x"], "next_item": "Q1"}
        self.assertEqual(codes(inp("Q4"), o), [])
        o["next_item"] = "Q5"
        self.assertEqual(codes(inp("Q4"), o), ["NEXT_ITEM_MISMATCH"])

    def test_target_not_in_values(self):
        o = {"action": "CONFIRM", "values": [val("Q1.x")], "targets": ["Q1.y"], "next_item": "Q1"}
        self.assertIn("TARGET_NOT_IN_VALUES", codes(inp("Q4"), o))

    def test_unknown_item(self):
        o = {"action": "NEXT", "values": [val("Q99.answer")], "next_item": "Q4"}
        self.assertEqual(codes(inp("Q4"), o), ["UNKNOWN_ITEM"])
        o = {"action": "NEXT", "values": [val("Q4.answer")], "next_item": "Q77"}
        self.assertEqual(codes(inp("Q4"), o), ["UNKNOWN_ITEM"])

    def test_bad_input_raises(self):
        from boundary_contracts import BoundaryError
        with self.assertRaises(BoundaryError):
            check_action_extraction({"question_id": "bad"}, {"action": "NEXT", "values": [], "next_item": "Q4"}, FLOW)


try:
    from turn_engine.flow import QuestionFlowTable, SkipRule
    from turn_engine.validation import validate_extraction
except ImportError:  # 이전 구현이 없으면 2부는 건너뛴다
    validate_extraction = None


@unittest.skipIf(validate_extraction is None, "turn_engine 없음")
class DifferentialTest(unittest.TestCase):
    def test_same_rule_violations_as_turn_engine(self):
        table = QuestionFlowTable(FLOW["order"], [SkipRule(s["slot"], s["value"], s["skip_item"]) for s in FLOW["skips"]])
        rnd = random.Random(1029)
        items = FLOW["order"] + ["Q99"]
        slots = ["answer", "days", "x"]
        n_viol = 0
        for _ in range(4000):
            q = rnd.choice(FLOW["order"])
            vals = []
            for _k in range(rnd.randint(0, 3)):
                st = rnd.choice(["ANSWERED", "CORRECTION", "MISSING", "UNCLEAR", "UNKNOWN", "REJECTED"])
                vals.append({"key": f"{rnd.choice(items)}.{rnd.choice(slots)}", "status": st,
                             "value": rnd.choice([None, True, False, 0, 3, "a"]), "save": rnd.choice([True, False])})
            keys = [v["key"] for v in vals]
            out = {"action": rnd.choice(["NEXT", "CORRECT", "REASK", "CONFIRM", "HOLD", "SKIP", "REDIRECT"]),
                   "values": vals, "next_item": rnd.choice(items + ["END"])}
            if rnd.random() < 0.5:
                out["targets"] = [rnd.choice(keys + ["Q1.zz"]) for _ in range(rnd.randint(0, 2))] if keys else ["Q1.zz"]
            i = inp(q)
            old = sorted((v.code, v.path) for v in validate_extraction(i, out, table) if v.code != "OUTPUT_SCHEMA")
            new = sorted((v.code, v.path) for v in check_action_extraction(i, out, FLOW))
            self.assertEqual(old, new, json.dumps(out, ensure_ascii=False))
            n_viol += bool(new)
        self.assertGreater(n_viol, 500)  # 위반 사례가 충분히 섞였는지


if __name__ == "__main__":
    unittest.main()


class ExtractRequestTest(unittest.TestCase):
    def test_예시의_flow로_검사기가_돈다(self):
        ex = json.loads((__import__("pathlib").Path(__file__).resolve().parent.parent / "examples" / "ExtractRequest.json").read_text(encoding="utf-8"))
        self.assertEqual(list(validator("ExtractRequest").iter_errors(ex)), [])
        out = {"action": "REASK", "values": [], "next_item": ex["input"]["question_id"]}
        self.assertEqual(check_action_extraction(ex["input"], out, ex["flow"]), [])
