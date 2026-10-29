"""2.8.0(U48): survey-service 위험 규칙 파일 형식을 계약으로. deploy가 시험용 규칙을 만들 때 영역 내부를 읽지 않게."""
import unittest

from boundary_contracts import validator


def ok(rec):
    return not list(validator("SurveyRiskRulesFile").iter_errors(rec))


R = {"id": "r1", "description": "d", "match": {"any_of": [{"contains": "가슴"}]}}


class U48(unittest.TestCase):
    def test_정상(self):
        self.assertTrue(ok({"version": "1", "rules": [R], "_comment": "x"}))
        self.assertTrue(ok({"version": "1", "rules": [dict(R, match={"any_of": [{"regex": "a+"}]})]}))

    def test_거부(self):
        self.assertFalse(ok({"version": "1", "rules": []}))                                     # 빈 목록
        self.assertFalse(ok({"version": " ", "rules": [R]}))                                     # 빈 version
        self.assertFalse(ok({"version": "1", "rules": [dict(R, id="-bad")]}))                    # id 형식
        self.assertFalse(ok({"version": "1", "rules": [dict(R, match={"any_of": [{"contains": "a", "regex": "b"}]})]}))  # 둘 다
        self.assertFalse(ok({"version": "1", "rules": [dict(R, match={"any_of": [{"contains": "x" * 501}]})]}))
        self.assertFalse(ok({"version": "1", "rules": [R], "extra": 1}))                          # 모르는 키


if __name__ == "__main__":
    unittest.main()
