"""U42(2.5.0): 영역 빌드 진입점 계약. deploy는 이 요청 한 벌만 넘기고 Dockerfile 인자 이름은 영역이 안다(구조 규칙 1)."""
import unittest

from boundary_contracts import validator


def ok(name, rec):
    return not list(validator(name).iter_errors(rec))


BASE = {"source_dir": "/w/survey-service", "revision": "4693a33", "versions": {"boundary": "v2.5.0"}, "image_tag": "deploy-build/survey-service:4693a33"}


class BuildImageRequestTest(unittest.TestCase):
    def test_turn_engine_없이도_된다(self):          # D109: turn-engine 폐기. 2.4까지는 필수였다
        self.assertTrue(ok("BuildImageRequest", BASE))

    def test_문진_스키마_버전과_라이브러리_소스(self):
        rec = dict(BASE, versions={"boundary": "v2.5.0", "survey_schema": "v1.2.0", "model_runtime": "v0.10.0"},
                   dependency_sources={"boundary": "/w/src/bc", "survey_schema": "/w/src/ss/schema"}, variant="gpu")
        self.assertTrue(ok("BuildImageRequest", rec))

    def test_모르는_키와_상대_경로는_거부(self):
        self.assertFalse(ok("BuildImageRequest", dict(BASE, build_args={"X": "1"})))     # 인자 이름을 deploy가 넘기는 길을 막는다
        self.assertFalse(ok("BuildImageRequest", dict(BASE, dependency_sources={"boundary": "../boundary-contracts"})))
        self.assertFalse(ok("BuildImageRequest", dict(BASE, versions={"boundary": "v2.5.0", "langgraph": "v1.0.0"})))

    def test_boundary는_필수(self):
        self.assertFalse(ok("BuildImageRequest", dict(BASE, versions={"survey_schema": "v1.2.0"})))


if __name__ == "__main__":
    unittest.main()
