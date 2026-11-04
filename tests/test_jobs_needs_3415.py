"""3.4.15: 파일 저장소의 주인 영역이 자기 백업·복구 잡을 낼 자원 이름(JobsDeclaration.needs, RUNTIME R10.1)."""
from boundary_contracts import validator

def test_jobs_needs_file_stores():
    v = validator("JobsDeclaration")
    for n in ("models-data", "datasets-data", "gateway-data", "pki-ca"):
        assert not list(v.iter_errors({"jobs": [{"name": "backup", "argv": ["x"], "idempotent": True, "needs": [n]}]})), n
    assert list(v.iter_errors({"jobs": [{"name": "backup", "argv": ["x"], "idempotent": True, "needs": ["other-data"]}]}))
