"""Token subjects and certificate names use the same hostname contract."""
import pytest
from boundary_contracts import validator


@pytest.mark.parametrize("name", ["survey-service", "host.docker.internal", "inference.example.org", "1-inference.example", "a" * 63, ".".join(["a" * 63] * 3 + ["b" * 59])])   # 251바이트: 토큰 파일 <이름>.ott 가 NAME_MAX 255 안(3.6.5)
def test_dns_hosts_are_valid_for_both_pki_roles(name):
    v = validator("StepCaEnv")
    v.validate({"STEP_ROLE": "cert", "STEP_CERT_NAME": name})
    v.validate({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": name + " release-gate"})


@pytest.mark.parametrize("name", ["", "bad_name", "-host", "host-", ".host", "host..example", "host.", "a" * 64, ".".join(["a" * 63] * 4), ".".join(["a" * 63] * 3 + ["b" * 61]), "../host", "host\n", "host\r", "host other", "한글.example"])
def test_invalid_subject_is_rejected_for_both_roles(name):
    v = validator("StepCaEnv")
    assert not v.is_valid({"STEP_ROLE": "cert", "STEP_CERT_NAME": name})
    if name != "host other":  # This is a valid two-name token list.
        assert not v.is_valid({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": name})


@pytest.mark.parametrize("names", [" host", "host ", "host  other", "host\tother", "host\nother"])
def test_token_list_has_unambiguous_separators(names):
    assert not validator("StepCaEnv").is_valid({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": names})


def test_token_name_length_fits_the_token_file_name():
    """3.6.5: 이름은 토큰 파일 <이름>.ott 의 이름이기도 하다. 251바이트까지(NAME_MAX 255 - '.ott'), 252바이트는 거부한다."""
    from boundary_contracts import validator
    v = validator("StepCaEnv")
    def name(n):   # 63바이트 라벨들로 n 바이트 이름
        labels, left = [], n
        while left > 0:
            k = min(63, left if len(labels) == 0 or left <= 63 else 63)
            if left - k == 1: k -= 1   # 점 다음 라벨이 비지 않게
            labels.append("a" * k); left -= k + 1
        return ".".join(labels)
    assert len(name(251)) == 251 and len(name(252)) == 252
    assert not list(v.iter_errors({"STEP_ROLE": "cert", "STEP_CERT_NAME": name(251)}))
    assert list(v.iter_errors({"STEP_ROLE": "cert", "STEP_CERT_NAME": name(252)}))
    assert list(v.iter_errors({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": "a " + name(252)}))
    assert len((name(251) + ".ott").encode()) == 255
