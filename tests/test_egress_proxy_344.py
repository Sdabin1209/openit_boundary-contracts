"""3.4.4 CONVENTIONS 13절·RUNTIME R1.8: 영역의 출력은 자기 영역 게이트웨이(CONNECT 터널)를 지난다."""
import socket
import threading

import pytest

from boundary_contracts import BoundaryError
from boundary_contracts.clients import HttpReleaseReader, egress_proxy_from, require_egress_proxy


class _ConnectRecorder:
    """CONNECT 요청 줄을 기록하고 403 으로 거절하는 최소 프록시(받는 쪽이 허용 목록 밖일 때의 게이트웨이와 같다)."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.lines = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.sock.accept()
        with conn:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            self.lines.append(data.split(b"\r\n", 1)[0].decode())
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")


def test_calls_go_through_own_gateway_as_connect_tunnel():
    proxy = _ConnectRecorder()
    c = HttpReleaseReader("https://release-gate:8443", "t", timeout=5, egress_proxy=f"http://127.0.0.1:{proxy.port}")
    with pytest.raises(BoundaryError) as e:
        c.get_active_pointer()
    assert proxy.lines == ["CONNECT release-gate:8443 HTTP/1.1"]
    assert e.value.code == "PERMISSION_DENIED"     # 허용 목록 밖: 정책 거절, 재시도 안 함(R1.8, 검토 B-23)
    assert e.value.retryable is False
    assert e.value.details["reason"] == "EGRESS_DENIED"


def test_own_gateway_unreachable_is_unavailable():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    c = HttpReleaseReader("https://release-gate:8443", "t", timeout=2, egress_proxy=f"http://127.0.0.1:{port}")
    with pytest.raises(BoundaryError) as e:
        c.get_active_pointer()
    assert e.value.code == "UNAVAILABLE"      # R3.21


@pytest.mark.parametrize("bad", ["https://127.0.0.1:3128", "http://gateway:3128", "http://10.0.0.1:3128",
                                 "http://127.0.0.1", "http://127.0.0.1:3128/x", "socks5://127.0.0.1:1080"])
def test_egress_proxy_must_be_loopback_http_with_port(bad):
    with pytest.raises(ValueError):
        require_egress_proxy(bad)
    with pytest.raises(ValueError):
        HttpReleaseReader("https://release-gate:8443", "t", egress_proxy=bad)


def test_from_environ_reads_only_the_named_key():
    assert egress_proxy_from({}) is None
    assert egress_proxy_from({"OPENIT_EGRESS_PROXY": ""}) is None
    assert egress_proxy_from({"OPENIT_EGRESS_PROXY": "http://127.0.0.1:3128", "HTTPS_PROXY": "http://x:1"}) == "http://127.0.0.1:3128"
    with pytest.raises(ValueError):
        egress_proxy_from({"OPENIT_EGRESS_PROXY": "http://proxy.example:3128"})
