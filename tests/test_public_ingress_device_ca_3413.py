"""3.4.13: 키오스크 기기 mTLS(PUBLIC_API F절, 기본 기기 인증)를 켜는 입력이 PublicIngressEnv 에 있다(platform 담당이 찾은 빈칸)."""
from boundary_contracts import load_schema, validator


def test_device_ca_input_exists_with_default_path():
    p = load_schema("PublicIngressEnv")["properties"]
    assert p["INGRESS_DEVICE_CA_FILE"]["default"] == "/etc/openit/device-ca.pem"


def test_device_ca_is_required_so_kiosk_default_auth_is_never_silently_off():
    assert "INGRESS_DEVICE_CA_FILE" in load_schema("PublicIngressEnv")["required"]
    errs = [e.message for e in validator("PublicIngressEnv").iter_errors({"GATEWAY_HOSTS": "kiosk.example.internal"})]
    assert any("INGRESS_DEVICE_CA_FILE" in m for m in errs), errs
