"""A disabled test-backend flag is legal for vllm, never for fake/mimic."""
import json
from pathlib import Path
import pytest
from boundary_contracts import validator

BASE = json.loads((Path(__file__).resolve().parents[1] / 'examples/ModelServingEnv.json').read_text())


def test_vllm_accepts_an_explicitly_empty_fake_permission_flag():
    assert validator('ModelServingEnv').is_valid({**BASE, 'MODEL_RUNTIME_ALLOW_FAKE': ''})


@pytest.mark.parametrize('backend', ['fake', 'mimic'])
def test_test_backend_still_requires_explicit_permission(backend):
    check = validator('ModelServingEnv')
    assert not check.is_valid({**BASE, 'MODEL_RUNTIME_BACKEND': backend, 'MODEL_RUNTIME_ALLOW_FAKE': ''})
    assert check.is_valid({**BASE, 'MODEL_RUNTIME_BACKEND': backend, 'MODEL_RUNTIME_ALLOW_FAKE': '1'})
