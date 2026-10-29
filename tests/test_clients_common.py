import http.server
import socket
import threading
import unittest

from _fixtures import OTHER, READ, TOKENS, WRITE, make_server
from boundary_contracts import BoundaryError, PIPELINE_SCHEMA_VERSION, sdk
from boundary_contracts.clients import (HttpFailureStore, HttpGateService, HttpModelRegistry, HttpQuestionReader,
                                        HttpReleaseReader, HttpStaffCall, HttpPublicApi, HttpTraceIngest)

PROTOCOLS = [(HttpQuestionReader, sdk.QuestionReader), (HttpModelRegistry, sdk.ModelRegistry),
             (HttpReleaseReader, sdk.ReleaseReader), (HttpGateService, sdk.GateService),
             (HttpTraceIngest, sdk.TraceIngest), (HttpFailureStore, sdk.FailureStore),
             (HttpStaffCall, sdk.StaffCall), (HttpPublicApi, sdk.PublicApi)]
SECRET = "fake-secret-token-9d1"
MAJOR = int(PIPELINE_SCHEMA_VERSION.split(".")[0])
NEXT_MINOR = "%d.%d" % (MAJOR, int(PIPELINE_SCHEMA_VERSION.split(".")[1]) + 1)  # 왜: 더 높은 MINOR를 상수에서 유도한다


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Common(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)

    def err(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception

    def test_Protocol_적합(self):
        for cls, proto in PROTOCOLS:
            with self.subTest(cls.__name__):
                self.assertIsInstance(cls(self.srv.url, READ), proto)

    def test_토큰_없음과_틀림은_PERMISSION_DENIED(self):
        for tok in ("", "fake-wrong-token"):
            e = self.err(HttpQuestionReader(self.srv.url, tok).list_ids)
            self.assertEqual(e.code, "PERMISSION_DENIED")
            self.assertNotIn("fake-wrong-token", str(e))

    def test_오류_코드_매핑(self):
        body = lambda code: ('{"pipeline_schema_version":"%s","code":"%s","message":"m","retryable":false}' % (PIPELINE_SCHEMA_VERSION, code)).encode()
        table = [(400, "INVALID_RECORD", "INVALID_RECORD"), (403, "PERMISSION_DENIED", "PERMISSION_DENIED"),
                 (401, "PERMISSION_DENIED", "PERMISSION_DENIED"), (404, "NOT_FOUND", "NOT_FOUND"),
                 (409, "CONFLICT", "CONFLICT"), (412, "FAILED_PRECONDITION", "FAILED_PRECONDITION"),
                 (422, "UNSUPPORTED_VERSION", "UNSUPPORTED_VERSION"), (422, "INTEGRITY_ERROR", "INTEGRITY_ERROR"),
                 (422, "NOT_FOUND", "INTEGRITY_ERROR"), (503, "UNAVAILABLE", "UNAVAILABLE"),
                 (404, "CONFLICT", "NOT_FOUND")]  # 상태가 우선(422만 본문 코드를 따른다)
        c = HttpQuestionReader(self.srv.url, READ)
        for status, code, want in table:
            with self.subTest(status=status, code=code):
                self.srv.overrides["/v1/question-sets"] = (status, "application/json", body(code))
                e = self.err(c.list_ids)
                self.assertEqual(e.code, want)
                self.assertEqual(e.retryable, want == "UNAVAILABLE")

    def test_5xx와_JSON이_아닌_응답은_UNAVAILABLE(self):
        c = HttpQuestionReader(self.srv.url, READ)
        for status, data in [(500, b"boom"), (502, b"<html>bad gateway</html>"), (404, b"<html>nginx</html>"),
                             (200, b"<html>not json</html>"), (409, b"{}"), (418, b'{"code":"NOT_FOUND","message":"x"}'),
                             (200, b"")]:
            with self.subTest(status=status):
                self.srv.overrides["/v1/question-sets"] = (status, "text/html", data)
                e = self.err(c.list_ids)
                self.assertEqual((e.code, e.retryable), ("UNAVAILABLE", True))
                self.assertNotIn("nginx", str(e))

    def test_서버가_보낸_메시지의_토큰은_가린다(self):
        c = HttpQuestionReader(self.srv.url, SECRET)
        body = ('{"pipeline_schema_version":"%s","code":"PERMISSION_DENIED","message":"bad %s","retryable":false}' % (PIPELINE_SCHEMA_VERSION, SECRET)).encode()
        self.srv.overrides["/v1/question-sets"] = (403, "application/json", body)
        e = self.err(c.list_ids)
        self.assertNotIn(SECRET, str(e) + repr(e.details) + e.message)

    def test_연결_거부는_UNAVAILABLE(self):
        c = HttpQuestionReader("http://127.0.0.1:%d" % free_port(), SECRET)
        e = self.err(c.list_ids)
        self.assertEqual(e.code, "UNAVAILABLE")
        self.assertNotIn(SECRET, str(e) + repr(e.details))

    def test_타임아웃은_UNAVAILABLE(self):
        self.srv.delay = 1.0
        c = HttpQuestionReader(self.srv.url, SECRET, timeout=0.2)
        e = self.err(c.list_ids)
        self.assertEqual(e.code, "UNAVAILABLE")
        self.assertNotIn(SECRET, str(e) + repr(e.details))

    def test_본문_도중_끊기면_UNAVAILABLE(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b'{"items":')
            def log_message(self, *a): pass
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(s.shutdown)
        self.addCleanup(s.server_close)
        e = self.err(HttpQuestionReader("http://127.0.0.1:%d" % s.server_address[1], READ).list_ids)
        self.assertEqual(e.code, "UNAVAILABLE")

    def test_리다이렉트를_따르지_않는다(self):
        self.srv.overrides["/v1/question-sets"] = (302, "text/plain", b"")
        self.assertEqual(self.err(HttpQuestionReader(self.srv.url, READ).list_ids).code, "UNAVAILABLE")

    def test_목록_형식_위반은_INTEGRITY_ERROR(self):
        c = HttpQuestionReader(self.srv.url, READ)
        for data in (b"[]", b'{"items": 3}', b'{"items": [1], "next_cursor": null}', b'{"items": [], "next_cursor": 5}'):
            self.srv.overrides["/v1/question-sets"] = (200, "application/json", data)
            self.assertEqual(self.err(c.list_ids).code, "INTEGRITY_ERROR", data)

    def test_item_null은_None(self):
        self.srv.overrides["/v1/active-pointer"] = (200, "application/json", b'{"item": null}')
        self.assertIsNone(HttpReleaseReader(self.srv.url, READ).get_active_pointer())

    def test_생성자_인자(self):
        with self.assertRaises(ValueError):
            HttpQuestionReader("ftp://x", READ)
        self.assertEqual(HttpQuestionReader(self.srv.url + "/", READ, 3.0)._timeout, 3.0)

    def test_토큰은_Authorization_헤더로만_가고_쓰기도_같다(self):
        HttpQuestionReader(self.srv.url, READ).list_ids()
        self.assertEqual(self.srv.requests[-1][2], "reader")
        self.assertNotIn(READ, self.srv.requests[-1][1])


if __name__ == "__main__":
    unittest.main()


class ReadMode(unittest.TestCase):
    """CONVENTIONS 1절: 읽는 쪽은 같은 MAJOR의 모르는 필드·열거값을 받아들이고, 쓰는 쪽은 엄격하다."""

    def setUp(self):
        from _fixtures import release
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.c = HttpReleaseReader(self.srv.url, READ)
        self.rel = self.srv.releases["rel-0001"]

    def err(self, fn, *a):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a)
        return cm.exception.code

    def reseal(self, **changes):
        from conformance.servers import sealed
        m = {k: v for k, v in self.rel["manifest"].items() if k != "content_hash"}
        m.update(changes)
        self.rel["manifest"] = sealed(m)

    def test_MINOR가_높고_모르는_필드가_있어도_읽는다(self):
        self.reseal(pipeline_schema_version=NEXT_MINOR, brand_new={"x": 1})
        r = self.c.get_release("rel-0001")
        self.assertEqual(r["brand_new"], {"x": 1})  # 보존

    def test_모르는_열거값을_읽는다(self):
        self.srv.pointer = dict(__import__("_fixtures").example("ActivePointer"), cause="SOMETHING_NEW")
        self.assertEqual(self.c.get_active_pointer()["cause"], "SOMETHING_NEW")

    def test_필수_누락과_타입_위반은_여전히_거부(self):
        self.reseal(pipeline_schema_version=NEXT_MINOR)
        m = dict(self.rel["manifest"]); m.pop("runtime_contract_version")
        self.rel["manifest"] = m
        self.assertEqual(self.err(self.c.get_release, "rel-0001"), "INTEGRITY_ERROR")
        self.reseal(runtime_contract_version="one")
        self.assertEqual(self.err(self.c.get_release, "rel-0001"), "INTEGRITY_ERROR")
        self.srv.pointer = dict(__import__("_fixtures").example("ActivePointer"), pointer_version="x")
        self.assertEqual(self.err(self.c.get_active_pointer), "INTEGRITY_ERROR")

    def test_MAJOR가_다르면_UNSUPPORTED_VERSION(self):
        for ver in (f"{MAJOR + 1}.0", f"{MAJOR - 1}.3"):  # 높은 MAJOR와, 폐기된 v1(1.3.3) 레코드 모두
            self.reseal(pipeline_schema_version=ver)
            self.assertEqual(self.err(self.c.get_release, "rel-0001"), "UNSUPPORTED_VERSION", ver)

    def test_모르는_필드까지_포함해_content_hash를_검증한다(self):
        self.reseal(pipeline_schema_version=NEXT_MINOR, brand_new="v")
        self.c.get_release("rel-0001")
        self.rel["manifest"]["brand_new"] = "tampered"
        self.assertEqual(self.err(self.c.get_release, "rel-0001"), "INTEGRITY_ERROR")

    def test_쓰기_본문은_여전히_엄격(self):
        from _fixtures import example
        req = dict(example("RollbackRequest"), surprise=1)
        self.assertEqual(self.err(HttpGateService(self.srv.url, WRITE).request_rollback, req), "INVALID_RECORD")
        env = dict(example("TraceEnvelope"), surprise=1)
        self.assertEqual(self.err(HttpTraceIngest(self.srv.url, WRITE).send, env), "INVALID_RECORD")


class TransportLimitTest(unittest.TestCase):
    """CONVENTIONS 9절(2.2.2): 413/414/431은 본문이 BoundaryError가 아니어도 INVALID_RECORD(재시도 안 함)."""
    def test_전송_한도_응답은_INVALID_RECORD(self):
        import io, urllib.error
        from boundary_contracts.clients._http import HttpClientBase as _B
        for st in (413, 414, 431):
            e = urllib.error.HTTPError("http://x/", st, "x", {}, io.BytesIO(b"Request Entity Too Large"))
            err = _B._map_error(object.__new__(_B), e)
            self.assertEqual(err.code, "INVALID_RECORD", st)
            self.assertFalse(err.retryable, st)


class _EarlyRejectServer:
    """본문을 읽지 않고 헤더만 본 뒤 413(또는 주어진 상태)을 보내고 닫는 서버. waitress가 본문 상한을 넘은 업로드에 하는 일과 같다(U29)."""
    def __init__(self, status=b"413 Request Entity Too Large", body=b"Request Entity Too Large"):
        self.sock = socket.socket(); self.sock.bind(("127.0.0.1", 0)); self.sock.listen(8)
        self.url = "http://127.0.0.1:%d" % self.sock.getsockname()[1]
        self.status, self.body = status, body
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += c.recv(4096)
            c.sendall(b"HTTP/1.1 " + self.status + b"\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(self.body) + self.body)
            c.close()   # 읽지 않은 본문이 남은 채 닫으면 커널이 RST를 보낸다

    def close(self):
        self.sock.close()


class WriteFailureTest(unittest.TestCase):
    """U29(2.5.0): 본문을 쓰다 연결이 끊겨도 서버가 먼저 보낸 응답을 읽는다. 413이면 INVALID_RECORD(재시도 안 함)."""
    def _post_big(self, url):
        from boundary_contracts.clients._http import HttpClientBase
        c = HttpClientBase(url, WRITE, timeout=5)
        with self.assertRaises(BoundaryError) as cm:
            c._json("POST", "/v1/x", body={"pad": "x" * (8 * 2**20)})
        return cm.exception

    def test_큰_본문의_413은_경쟁_없이_INVALID_RECORD(self):
        srv = _EarlyRejectServer()
        try:
            for _ in range(20):   # 경쟁 조건이라 여러 번 본다(옛 코드는 대부분 UNAVAILABLE)
                e = self._post_big(srv.url)
                self.assertEqual((e.code, e.details.get("http_status")), ("INVALID_RECORD", 413))
        finally:
            srv.close()

    def test_쓰기_실패_뒤_성공_응답은_믿지_않는다(self):
        srv = _EarlyRejectServer(status=b"200 OK", body=b"{}")
        try:
            e = self._post_big(srv.url)
            self.assertEqual(e.code, "UNAVAILABLE")   # 본문을 다 못 보냈는데 성공이라면 잘린 요청이 처리됐을 수 있다
        finally:
            srv.close()


class HttpStatusDetailTest(unittest.TestCase):
    """U21(2.5.0): HTTP 오류 응답에서 만든 오류는 details.http_status에 원래 상태를 남긴다(401 토큰 오류와 403 권한 오류 구분)."""
    def test_401과_403을_details로_구분한다(self):
        import io, json, urllib.error
        from boundary_contracts.clients._http import HttpClientBase as _B
        for st in (401, 403):
            body = json.dumps({"code": "PERMISSION_DENIED", "message": "no", "details": {"reason": "r"}}).encode()
            e = urllib.error.HTTPError("http://x/", st, "x", {}, io.BytesIO(body))
            b = object.__new__(_B); b._token = None
            err = _B._map_error(b, e)
            self.assertEqual((err.code, err.details["http_status"], err.details["reason"]), ("PERMISSION_DENIED", st, "r"))
