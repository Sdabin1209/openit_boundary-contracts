"""3.4.14: 공개 입구 호스트는 DNS 이름만(IP 리터럴 금지). 기본 기기 인증(mTLS)에서 Host 와 TLS SNI 가 같아야 하고(RFC 9110 421), SNI 에는 IP 리터럴을 쓸 수 없다(RFC 6066 3절)."""
from boundary_contracts import validator


def _errs(v):
    return [e.message for e in validator("PublicIngressEnv").iter_errors({"GATEWAY_HOSTS": v, "INGRESS_DEVICE_CA_FILE": "/etc/openit/device-ca.pem"})]


def test_dns_names_are_accepted():
    assert not _errs("kiosk.example.internal"), _errs("kiosk.example.internal")
    assert not _errs("kiosk.example.internal:8443, localhost:8443")


def test_ip_literals_are_rejected():
    assert _errs("127.0.0.1:8443")
    assert _errs("kiosk.example.internal, 10.0.0.5")
