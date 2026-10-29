"""2.6.0: U43(영역이 시험 환경·시험 명령·잡 설정 변수를 선언) + U45(ListEnvelope items 원소 모양을 호출별 스키마에 맡김)."""
import unittest

from boundary_contracts import validator


def ok(name, rec):
    return not list(validator(name).iter_errors(rec))


class C260(unittest.TestCase):
    def test_SetupEnvReport_시험_명령(self):
        base = {"area": "kiosk-frontend", "status": "ok", "exit_code": 0, "seconds": 3}
        self.assertTrue(ok("SetupEnvReport", dict(base, environment={"kind": "node-modules", "path": "node_modules", "test_command": ["npm", "test"]})))
        self.assertFalse(ok("SetupEnvReport", base))                                   # 3.0.0: ok면 environment 필수
        self.assertTrue(ok("SetupEnvReport", dict(base, status="fail", exit_code=1)))  # 실패 보고에는 없어도 된다
        self.assertFalse(ok("SetupEnvReport", dict(base, environment={"kind": "node-modules", "path": "/abs", "test_command": ["npm", "test"]})))
        self.assertFalse(ok("SetupEnvReport", dict(base, environment={"kind": "python-venv", "path": ".venv", "test_command": []})))

    def test_잡_설정_환경_변수_이름(self):
        job = {"name": "run", "argv": ["python", "-m", "x", "run-once"], "idempotent": True}
        self.assertTrue(ok("JobsDeclaration", {"jobs": [dict(job, env=["DATASET_STORE_URL"], secret_files=["DATASET_TOKEN_FILE"])]}))
        self.assertFalse(ok("JobsDeclaration", {"jobs": [dict(job, env=["DATASET_TOKEN_FILE"])]}))   # 비밀은 secret_files로
        self.assertFalse(ok("JobsDeclaration", {"jobs": [dict(job, env=["lower"])]}))

    def test_목록_원소는_ID_문자열도_된다(self):
        self.assertTrue(ok("ListEnvelope", {"items": ["qs-main", "qs-2"], "next_cursor": None}))
        self.assertFalse(ok("ListEnvelope", {"items": [], "next_cursor": 5}))
        self.assertFalse(ok("ListEnvelope", {"items": []}))


if __name__ == "__main__":
    unittest.main()
