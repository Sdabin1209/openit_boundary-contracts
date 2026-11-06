"""Token subjects and certificate names use the same hostname contract."""
import pytest
from boundary_contracts import validator


@pytest.mark.parametrize("name", ["survey-service", "host.docker.internal", "inference.example.org", "1-inference.example", "a" * 63, ".".join(["a" * 63] * 3 + ["b" * 61])])
def test_dns_hosts_are_valid_for_both_pki_roles(name):
    v = validator("StepCaEnv")
    v.validate({"STEP_ROLE": "cert", "STEP_CERT_NAME": name})
    v.validate({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": name + " release-gate"})


@pytest.mark.parametrize("name", ["", "bad_name", "-host", "host-", ".host", "host..example", "host.", "a" * 64, ".".join(["a" * 63] * 4), "../host", "host\n", "host\r", "host other", "한글.example"])
def test_invalid_subject_is_rejected_for_both_roles(name):
    v = validator("StepCaEnv")
    assert not v.is_valid({"STEP_ROLE": "cert", "STEP_CERT_NAME": name})
    if name != "host other":  # This is a valid two-name token list.
        assert not v.is_valid({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": name})


@pytest.mark.parametrize("names", [" host", "host ", "host  other", "host\tother", "host\nother"])
def test_token_list_has_unambiguous_separators(names):
    assert not validator("StepCaEnv").is_valid({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": names})
