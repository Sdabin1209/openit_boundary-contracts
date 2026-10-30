"""3.0.2: SurveyServiceEnv의 추론 연결은 SURVEY_INFERENCE_URL 또는 SURVEY_MODEL_BACKEND 중 하나(D62). 운영 배포는 원격 추론(URL)만 준다."""
import unittest

from boundary_contracts import validator


def errs(env):
    return [e.message for e in validator("SurveyServiceEnv").iter_errors(env)]


BASE = {"SURVEY_RELEASE_READER": "http", "SURVEY_RELEASE_READER_URL": "http://release-gate:8080",
        "SURVEY_TRACE_INGEST": "http", "SURVEY_TRACE_INGEST_URL": "http://ops-feedback-ingest:8080"}


class Env302(unittest.TestCase):
    def test_원격_추론만_줘도_된다(self):
        self.assertEqual(errs(dict(BASE, SURVEY_INFERENCE_URL="http://model-serving:8080")), [])

    def test_내장_백엔드만_줘도_된다(self):
        self.assertEqual(errs(dict(BASE, SURVEY_MODEL_BACKEND="fake")), [])

    def test_둘_다_없으면_거부(self):
        self.assertNotEqual(errs(dict(BASE)), [])

    def test_필수_이름(self):
        self.assertNotEqual(errs({"SURVEY_INFERENCE_URL": "http://x"}), [])


if __name__ == "__main__":
    unittest.main()
