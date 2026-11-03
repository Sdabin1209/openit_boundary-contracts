"""3.4.4 RUNTIME R9.2: 잡 선언의 실행 시간 상한(timeout_seconds)은 선택이고, 있으면 1 이상의 정수다."""
import pytest
from boundary_contracts import validator

BASE = {"name": "collect", "argv": ["python", "-m", "x", "collect"], "idempotent": True}


def _doc(**extra):
    return {"jobs": [dict(BASE, **extra)]}


def test_without_timeout_is_valid():
    validator("JobsDeclaration").validate(_doc())


def test_positive_integer_timeout_is_valid():
    validator("JobsDeclaration").validate(_doc(timeout_seconds=600))


@pytest.mark.parametrize("bad", [0, -1, 1.5, "600", None])
def test_invalid_timeout_is_rejected(bad):
    assert not validator("JobsDeclaration").is_valid(_doc(timeout_seconds=bad))
