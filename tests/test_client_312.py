"""3.1.2 클라이언트 수정: Retry-After 머리글을 details.retry_after_s로 넘긴다, 제출 목록이 봉투(ListEnvelope)를 계약으로 본다."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from boundary_contracts import BoundaryError
from boundary_contracts.clients import HttpGateService
from boundary_contracts.clients.staffcall import HttpStaffCall


def _serve(status, body, headers=None):
    class H(BaseHTTPRequestHandler):
        def _go(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        do_GET = do_POST = _go

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


ERR = {"pipeline_schema_version": 1, "code": "UNAVAILABLE", "message": "잠시 뒤", "retryable": True}


class RetryAfter(unittest.TestCase):
    def test_retry_after_header_reaches_details(self):
        srv, url = _serve(429, ERR, {"Retry-After": "7"})
        try:
            with self.assertRaises(BoundaryError) as cm:
                HttpStaffCall(url, "tok-FAKE").retry("s1", "t1")
            self.assertEqual(cm.exception.code, "UNAVAILABLE")
            self.assertEqual(cm.exception.details.get("retry_after_s"), 7)
        finally:
            srv.shutdown()

    def test_bad_retry_after_is_ignored(self):
        srv, url = _serve(503, ERR, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        try:
            with self.assertRaises(BoundaryError) as cm:
                HttpStaffCall(url, "tok-FAKE").retry("s1", "t1")
            self.assertNotIn("retry_after_s", cm.exception.details or {})
        finally:
            srv.shutdown()


class ListSubmissions(unittest.TestCase):
    def test_non_object_body_is_boundary_error_not_attribute_error(self):
        srv, url = _serve(200, ["not", "an", "envelope"])
        try:
            with self.assertRaises(BoundaryError):
                HttpGateService(url, "tok-FAKE").list_submissions()
        finally:
            srv.shutdown()

    def test_bad_envelope_is_rejected(self):
        srv, url = _serve(200, {"items": [], "next_cursor": ""})
        try:
            with self.assertRaises(BoundaryError):
                HttpGateService(url, "tok-FAKE").list_submissions()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
