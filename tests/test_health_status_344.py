"""3.4.4 RUNTIME R5.1: /healthz·/readyz 본문의 공통 최소 모양(HealthStatus)."""
import pytest
from boundary_contracts import validator

V = validator("HealthStatus")


@pytest.mark.parametrize("body", [
    {"status": "ok"}, {"status": "ready", "database": "postgresql"}, {"status": "not_ready"},
    {"status": "shutting_down"}, {"status": "not ready"}, {"status": "not-ready"},
    {"ready": True, "problems": []},   # SurveyReadyz 모양(status 없음)
])
def test_accepted(body):
    V.validate(body)


@pytest.mark.parametrize("body", [{}, [], "ok", None, {"status": "OK"}, {"status": "degraded"}])
def test_rejected(body):
    assert not V.is_valid(body)


def test_area_readyz_examples_also_pass_common_shape():
    """영역별 준비 확인 예시가 모두 공통 HealthStatus 도 통과한다(두 계약이 어긋나지 않는다)."""
    import json
    from boundary_contracts import schema_dir
    root = schema_dir().parent.parent / "examples"
    names = sorted(p for p in root.glob("*.json") if "Readyz" in p.name)
    assert len(names) >= 9
    for p in names:
        V.validate(json.loads(p.read_text(encoding="utf-8")))


@pytest.mark.parametrize("schema", ["GateReadyz", "OpsFeedbackReadyz"])
def test_area_readyz_accepts_canonical_not_ready(schema):
    """3.4.5: 영역 준비 확인 스키마가 정본 not_ready 를 막지 않는다(R5.1 은 두 스키마를 함께 통과하라고 한다)."""
    import json
    s = json.dumps(validator(schema).schema)
    assert "not_ready" in s
