"""2.4.0 값 규칙(apply_value_rules, U32·U33) 시험.

기대값은 구현에서 가져오지 않았다. 학습 데이터셋(`~/WS/dataset/data/final/lora_a_train.jsonl`, 10/29 02:26 빌드)의
실제 정답을 옮겨 적었고, 정답이 없는 R1은 정규화기 원본(`openit-normalizer/normalizer/normalize.py` R1)의 동작을 적었다.
모델이 틀린 출력(규칙에 걸리는 값을 저장하는 NEXT)을 넣으면, 그 상황의 데이터셋 정답과 같은 모양이 나와야 한다.
"""
import copy
import unittest

from boundary_contracts import validator
from boundary_contracts.action_rules import apply_value_rules, check_action_extraction, load_rules

FIELDS = {"fields": [
    {"slot": "Q10.days", "data_type": "integer", "unit": "day/week", "minimum": 0, "maximum": 7},
    {"slot": "Q9_2.duration_minutes", "data_type": "integer", "unit": "minute", "minimum": 0},
    {"slot": "Q7.does_not_drink", "data_type": "boolean"},
    {"slot": "Q7.frequency", "data_type": "number", "exclusive_minimum": 0},
    {"slot": "Q7.unit", "data_type": "option", "options": ["week", "month", "year"]},
    {"slot": "Q7_1.amount", "data_type": "number", "minimum": 0, "repeat_keys": ["soju", "beer", "spirits", "makgeolli", "wine"]},
    {"slot": "Q7_1.unit", "data_type": "option", "options": ["glass", "bottle", "can", "cc"], "repeat_keys": ["soju", "beer", "spirits", "makgeolli", "wine"]},
    {"slot": "Q7_2.amount", "data_type": "number", "minimum": 0, "repeat_keys": ["soju", "beer", "spirits", "makgeolli", "wine"]},
    {"slot": "Q7_2.unit", "data_type": "option", "options": ["glass", "bottle", "can", "cc"], "repeat_keys": ["soju", "beer", "spirits", "makgeolli", "wine"]},
    {"slot": "Q4_1.daily_count", "data_type": "number", "minimum": 0},
]}
FLOW = {"order": ["Q7", "Q7_1", "Q7_2", "Q8_1", "Q9_2", "Q10"],
        "skips": [{"slot": "Q7.does_not_drink", "op": "==", "value": True, "skip_item": "Q7_1"},
                  {"slot": "Q7.does_not_drink", "op": "==", "value": True, "skip_item": "Q7_2"}]}


def inp(q, state=None):
    return {"question_id": q, "current_question": "질문", "user_utterance": "답", "state": state or {}}


def v(key, value, status="ANSWERED", save=True, precision="exact"):
    return {"key": key, "value": value, "status": status, "save": save, "precision": precision}


def nxt(values, next_item):
    return {"action": "NEXT", "values": values, "next_item": next_item}  # NEXT에는 reason·targets 칸이 없다(ActionExtraction 스키마)


def apply(i, o):
    return apply_value_rules(i, o, FIELDS, FLOW)


class DatasetLabelShapes(unittest.TestCase):
    def test_out_of_range_matches_dataset_label(self):
        # 데이터셋: Q10 "일주일 중 근력 운동하는 날은 여덟 일입니다" -> 정답
        want = {"action": "REASK", "next_item": "Q10", "reason": "OUT_OF_RANGE", "targets": ["Q10.days"],
                "values": [{"key": "Q10.days", "precision": "unspecified", "save": False, "status": "UNCLEAR", "value": None}]}
        got, viol, applied = apply(inp("Q10"), nxt([v("Q10.days", 8)], "END"))
        self.assertEqual(viol, [])
        self.assertEqual(applied, ["OUT_OF_RANGE"])
        self.assertEqual({k: got[k] for k in want}, want)

    def test_count_exceeds_days_matches_dataset_label(self):
        # 데이터셋: Q7 "일주일에 열 번씩 마셨습니다" -> does_not_drink는 저장 그대로, 횟수·기간은 비우고 다시 묻는다
        want_values = [{"key": "Q7.does_not_drink", "precision": "exact", "save": True, "status": "ANSWERED", "value": False},
                       {"key": "Q7.frequency", "precision": "unspecified", "save": False, "status": "UNCLEAR", "value": None},
                       {"key": "Q7.unit", "precision": "unspecified", "save": False, "status": "UNCLEAR", "value": None}]
        o = nxt([v("Q7.does_not_drink", False), v("Q7.frequency", 10), v("Q7.unit", "week")], "Q7_1")
        got, viol, applied = apply(inp("Q7"), o)
        self.assertEqual((viol, applied), ([], ["COUNT_EXCEEDS_DAYS"]))
        self.assertEqual((got["action"], got["reason"], got["targets"], got["next_item"]),
                         ("REASK", "COUNT_EXCEEDS_DAYS", ["Q7.frequency", "Q7.unit"], "Q7"))
        self.assertEqual(got["values"], want_values)

    def test_max_below_usual_matches_dataset_label(self):
        # 데이터셋: Q7_2 "맥주 두 병 마셨어요", state 평소 맥주 4병 -> 값은 그대로 두고 CONFLICT로 확인
        state = {"Q7_1[beer].amount": {"value": 4, "status": "ANSWERED"}, "Q7_1[beer].unit": {"value": "bottle", "status": "ANSWERED"}}
        o = nxt([v("Q7_2[beer].amount", 2), v("Q7_2[beer].unit", "bottle")], "Q8_1")
        got, viol, applied = apply(inp("Q7_2", state), o)
        self.assertEqual((viol, applied), ([], ["CONFLICT_MAX_BELOW_USUAL"]))
        self.assertEqual((got["action"], got["reason"], got["targets"], got["next_item"]),
                         ("CONFIRM", "CONFLICT_MAX_BELOW_USUAL", ["Q7_2[beer].amount", "Q7_2[beer].unit"], "Q7_2"))
        self.assertEqual(got["values"], [
            {"key": "Q7_2[beer].amount", "precision": "exact", "save": False, "status": "CONFLICT", "value": 2},
            {"key": "Q7_2[beer].unit", "precision": "exact", "save": False, "status": "CONFLICT", "value": "bottle"}])

    def test_rewritten_outputs_pass_schema_and_action_rules(self):
        cases = [(inp("Q10"), nxt([v("Q10.days", 8)], "END")),
                 (inp("Q7"), nxt([v("Q7.does_not_drink", False), v("Q7.frequency", 10), v("Q7.unit", "week")], "Q7_1")),
                 (inp("Q7_2", {"Q7_1[beer].amount": {"value": 4, "status": "ANSWERED"}, "Q7_1[beer].unit": {"value": "bottle", "status": "ANSWERED"}}),
                  nxt([v("Q7_2[beer].amount", 2), v("Q7_2[beer].unit", "bottle")], "Q8_1"))]
        for i, o in cases:
            got, _, _ = apply(i, o)
            self.assertEqual(list(validator("ActionExtraction").iter_errors(got)), [])
            self.assertEqual(check_action_extraction(i, got, FLOW), [])


class NormalizerBehaviour(unittest.TestCase):
    def test_r1_frequency_corrects_flag_and_moves_to_next_item(self):
        # 정규화기 R1: 안 마심인데 횟수가 있으면 '마심'으로 고친다(정정, 어림). 건너뛰기가 풀려 다음 문항은 Q7_1
        o = nxt([v("Q7.does_not_drink", True), v("Q7.frequency", 2), v("Q7.unit", "week")], "Q8_1")
        got, viol, applied = apply(inp("Q7"), o)
        self.assertEqual((viol, applied), ([], ["R1_CORRECTED"]))
        self.assertEqual(got["values"][0], {"key": "Q7.does_not_drink", "value": False, "status": "CORRECTION", "save": True, "precision": "approximate"})
        self.assertEqual((got["action"], got["next_item"]), ("NEXT", "Q7_1"))

    def test_r1_amount_without_frequency_is_conflict(self):
        state = {"Q7_1[soju].amount": {"value": 2, "status": "ANSWERED"}, "Q7_1[soju].unit": {"value": "bottle", "status": "ANSWERED"}}
        got, viol, applied = apply(inp("Q7", state), nxt([v("Q7.does_not_drink", True)], "Q8_1"))
        self.assertEqual((viol, applied), ([], ["CONFLICT_DOES_NOT_DRINK"]))
        self.assertEqual((got["action"], got["next_item"]), ("CONFIRM", "Q7"))
        self.assertEqual(got["targets"], ["Q7.does_not_drink", "Q7_1[soju].amount", "Q7_1[soju].unit"])
        self.assertTrue(all(x["status"] == "CONFLICT" and x["save"] is False for x in got["values"]))

    def test_r3_compares_in_ml_across_units(self):
        # 평소 소주 1병(360mL), 최대 소주 5잔(250mL) -> 단위가 달라도 mL로 비교해 충돌
        state = {"Q7_1[soju].amount": {"value": 1, "status": "ANSWERED"}, "Q7_1[soju].unit": {"value": "bottle", "status": "ANSWERED"}}
        _, _, applied = apply(inp("Q7_2", state), nxt([v("Q7_2[soju].amount", 5), v("Q7_2[soju].unit", "glass")], "Q8_1"))
        self.assertEqual(applied, ["CONFLICT_MAX_BELOW_USUAL"])

    def test_r3_skips_unknown_volume(self):
        # 소주 캔은 환산표에 없다(정규화기 VOLUME_ML None) -> 비교하지 않는다
        state = {"Q7_1[soju].amount": {"value": 3, "status": "ANSWERED"}, "Q7_1[soju].unit": {"value": "can", "status": "ANSWERED"}}
        got, viol, applied = apply(inp("Q7_2", state), nxt([v("Q7_2[soju].amount", 1), v("Q7_2[soju].unit", "bottle")], "Q8_1"))
        self.assertEqual((viol, applied, got["action"]), ([], [], "NEXT"))

    def test_minutes_above_a_day_is_out_of_range(self):
        # 정규화기 MAX_MINUTES_PER_DAY 1440: 칸 규격에 maximum이 없어도 단위 상한으로 범위 밖
        got, _, applied = apply(inp("Q9_2"), nxt([v("Q9_2.duration_minutes", 1500)], "Q10"))
        self.assertEqual((applied, got["targets"]), (["OUT_OF_RANGE"], ["Q9_2.duration_minutes"]))


class NotRewritten(unittest.TestCase):
    def test_below_minimum_is_a_violation_not_a_rewrite(self):
        # 데이터셋에 음수 개비 수의 정답이 없다 -> 바꾸지 않고 위반(호출자는 OUTPUT_INVALID)
        o = nxt([v("Q4_1.daily_count", -3)], "Q5")
        got, viol, applied = apply(inp("Q4_1"), o)
        self.assertEqual(([x.code for x in viol], applied), (["VALUE_BELOW_MINIMUM"], []))
        self.assertEqual(got, o)

    def test_type_mismatch_is_a_violation(self):
        _, viol, _ = apply(inp("Q10"), nxt([v("Q10.days", 2.5)], "END"))
        self.assertEqual([x.code for x in viol], ["VALUE_TYPE_MISMATCH"])
        _, viol, _ = apply(inp("Q7"), nxt([v("Q7.unit", "day")], "Q7_1"))
        self.assertEqual([x.code for x in viol], ["VALUE_TYPE_MISMATCH"])

    def test_values_within_spec_are_untouched(self):
        o = nxt([v("Q10.days", 7)], "END")
        self.assertEqual(list(validator("ActionExtraction").iter_errors(o)), [])
        got, viol, applied = apply(inp("Q10"), o)
        self.assertEqual((got, viol, applied), (o, [], []))

    def test_input_output_not_mutated(self):
        o = nxt([v("Q10.days", 8)], "END")
        before = copy.deepcopy(o)
        apply(inp("Q10"), o)
        self.assertEqual(o, before)

    def test_unsaved_values_are_not_checked(self):
        o = nxt([v("Q10.days", None, status="UNKNOWN", save=False, precision="unspecified")], "END")
        self.assertEqual(apply(inp("Q10"), o)[1:], ([], []))


class Spec(unittest.TestCase):
    def test_rules_version_and_schema(self):
        r = load_rules()
        self.assertEqual(r["rules_version"], "2")
        self.assertEqual(list(validator("ActionExtractionRules").iter_errors(r)), [])

    def test_volume_table_matches_normalizer(self):
        # 정규화기 mappings.VOLUME_ML 값을 옮겨 적은 것
        vm = load_rules()["value_rules"]["max_below_usual"]["volume_ml"]
        self.assertEqual(vm["soju"], {"glass": 50, "bottle": 360, "can": None})
        self.assertEqual(vm["beer"], {"glass": 200, "bottle": 500, "can": 355})

    def test_field_spec_schema(self):
        self.assertEqual(list(validator("QuestionFieldSpec").iter_errors(FIELDS)), [])


if __name__ == "__main__":
    unittest.main()
