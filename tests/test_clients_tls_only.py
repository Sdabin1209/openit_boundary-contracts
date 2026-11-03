"""3.4.1(U99): 계약 클라이언트는 loopback 밖 평문 http:// 를 시작 시점에 거부한다."""
import unittest

from boundary_contracts.clients import require_tls_url
from boundary_contracts.clients._http import HttpClientBase


class TlsOnly(unittest.TestCase):
    def test_https_any_host_ok(self):
        for u in ("https://release-gate", "https://10.0.0.5:8443", "https://gate.example.org/x"):
            HttpClientBase(u, None)

    def test_loopback_http_ok(self):
        for u in ("http://127.0.0.1:8080", "http://localhost:1", "http://[::1]:9", "http://127.5.6.7"):
            HttpClientBase(u, None)

    def test_non_loopback_http_rejected(self):
        for u in ("http://release-gate:8080", "http://10.0.0.5:8080", "http://gpu-host", "http://localhost.evil.org"):
            with self.assertRaises(ValueError, msg=u):
                HttpClientBase(u, None)

    def test_public_function_same_rule(self):
        require_tls_url("https://x")
        require_tls_url("http://127.0.0.1:1")
        with self.assertRaises(ValueError):
            require_tls_url("http://model-serving:8080")

    def test_other_scheme_rejected(self):
        for u in ("ftp://x", "release-gate:8080", "file:///etc/passwd"):
            with self.assertRaises(ValueError, msg=u):
                HttpClientBase(u, None)


if __name__ == "__main__":
    unittest.main()
