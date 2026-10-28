import copy
import json
import os
import subprocess
import sys
import unittest

import boundary_contracts
from boundary_contracts import metrics, metric_name_problems, validator

from _fixtures import example

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = {"ratio", "count", "ms", "score"}
GROUPS = {"SAFETY", "ACCURACY", "PROTECTION", "ROBUSTNESS", "COVERAGE", "REGRESSION", "OTHER"}


class Metrics(unittest.TestCase):
    def test_레지스트리_형태(self):
        reg = metrics()
        self.assertGreater(len(reg), 20)
        for n, m in reg.items():
            self.assertEqual(m["name"], n)
            self.assertIn(m["unit"], UNITS, n)  # EvaluationReport unit 열거
            self.assertIn(m["group"], GROUPS, n)
            self.assertIn(m["status"], ("ACTIVE", "DEPRECATED"), n)
            self.assertIn(m["applies_to"], ("A", "B", "both"), n)
            self.assertIn(m["higher_is_better"], (True, False, None), n)
            if m["status"] == "ACTIVE":
                self.assertIsNone(m["replaced_by"], n)
            for r in (m["replaced_by"] or ()):
                self.assertEqual(reg[r]["status"], "ACTIVE", f"{n} -> {r}")

    def test_읽기_전용(self):
        with self.assertRaises(TypeError):
            metrics()["action_accuracy"]["unit"] = "ms"
        with self.assertRaises(TypeError):
            metrics()["new"] = {}

    def test_폐기_이름(self):
        reg = metrics()
        for n in ("risk_signal_recall", "risk_signal_false_alarm", "intent_accuracy", "item_precision", "item_recall",
                  "target_accuracy", "risk_notice_verbatim_rate", "slot_coverage"):
            self.assertEqual(reg[n]["status"], "DEPRECATED", n)

    def test_예시_보고서의_지표_이름은_ACTIVE(self):
        self.assertEqual(metric_name_problems(example("EvaluationReport")), [])
        self.assertEqual(metric_name_problems(example("ReviewReport")), [])

    def test_폐기_이름을_넣으면_거부(self):  # 부정 시험: 예시를 일부러 망가뜨린다
        for kind, key in (("EvaluationReport", "metrics"), ("ReviewReport", "comparisons")):
            d = copy.deepcopy(example(kind))
            d[key][0]["name"] = "risk_signal_recall"
            self.assertEqual(metric_name_problems(d), [("risk_signal_recall", "DEPRECATED")])
            d[key][0]["name"] = "made_up_metric"
            self.assertEqual(metric_name_problems(d), [("made_up_metric", "UNKNOWN")])
            self.assertEqual(list(validator(kind).iter_errors(d)), [])  # 스키마는 자유 문자열이라 통과: 이름 검사는 레지스트리 몫

    def test_METRICS_md는_레지스트리에서_생성한_것과_같다(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_metrics_md.py"), "--check"])
        self.assertEqual(r.returncode, 0, "python3 tools/gen_metrics_md.py 를 실행해 METRICS.md를 다시 생성하라")

    def test_패키지_데이터에_들어_있다(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            self.assertIn('"metrics.json"', f.read())
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(boundary_contracts.__file__), "metrics.json")))
