"""HTTP 클라이언트의 공통 부분: 요청, 오류 매핑, 목록, 레코드 검증, tar 처리. 표준 라이브러리만 쓴다."""
from __future__ import annotations

import http.client
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..canonical import content_hash as _content_hash, directory_hash, sha256_hash
from ..errors import CODES, BoundaryError
from ..schemas_api import PIPELINE_SCHEMA_VERSION, schema_dir, validator

_STATUS_CODE = {400: "INVALID_RECORD", 401: "PERMISSION_DENIED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND",
                409: "CONFLICT", 412: "FAILED_PRECONDITION", 429: "UNAVAILABLE", 503: "UNAVAILABLE"}
_TRANSPORT_LIMIT = (413, 414, 431)   # RFC 9110 15.5.14·15.5.15, RFC 6585 5
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_ERROR_BODY = 64 * 1024
_MAX_MESSAGE = 300
TAR_TYPE = "application/x-tar"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # 토큰이 다른 곳으로 따라가지 않게 한다
        return None


@lru_cache(maxsize=None)
def _validator(name: str):
    return validator(name)


def _relax(node):
    """읽기 모드 스키마(CONVENTIONS 1절 3항): 모르는 필드를 허용하고 열거값은 문자열 형태만 본다. const·필수·타입·패턴은 그대로."""
    if isinstance(node, list):
        return [_relax(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "additionalProperties" and v is False:
            continue
        if k == "enum" and isinstance(v, list) and all(isinstance(x, str) or x is None for x in v) and any(isinstance(x, str) for x in v):
            out["type"] = ["string", "null"] if None in v else "string"  # 왜: null을 허용하는 열거(pause_reason 등)도 모르는 값은 받아들인다
            continue
        out[k] = _relax(v)
    return out


@lru_cache(maxsize=None)
def _reader(name: str):
    import jsonschema
    base = schema_dir().as_uri() + "/"
    store = {base + p.name: _relax(json.loads(p.read_text(encoding="utf-8"))) for p in schema_dir().glob("*.schema.json")}
    schema = store[base + name + ".schema.json"]
    return jsonschema.Draft202012Validator(schema, resolver=jsonschema.RefResolver(base, schema, store=store))


def integrity(message: str, **details) -> BoundaryError:
    return BoundaryError("INTEGRITY_ERROR", message, details or None)


def check_ref(ref: Any, what: str = "ref") -> dict:
    """ArtifactRef 형태 검사(요청에 쓰는 것은 INVALID_RECORD가 아니라 호출자 오류이므로 ValueError가 아닌 BoundaryError)."""
    if (not isinstance(ref, dict) or set(ref) != {"id", "version", "content_hash"}
            or not isinstance(ref["id"], str) or not _ID.match(ref["id"]) or len(ref["id"]) > 128
            or not isinstance(ref["version"], str) or not ref["version"]
            or not isinstance(ref["content_hash"], str) or not _HASH.match(ref["content_hash"])):
        raise BoundaryError("INVALID_RECORD", f"{what}가 ArtifactRef 형식이 아니다")
    return ref


def check_id(value: Any, what: str = "id") -> str:
    """경로에 쓰는 식별자(CONVENTIONS 2·10절). 어기면 INVALID_RECORD."""
    if not isinstance(value, str) or len(value) > 128 or not _ID.match(value):
        raise BoundaryError("INVALID_RECORD", f"{what}가 Id 형식이 아니다")
    return value


def check_str(x: Any) -> None:
    if not isinstance(x, str):
        raise integrity("목록 항목이 문자열이 아니다")


def check_record(schema: str, rec: Any, *, hashed: bool = False) -> dict:
    """응답 레코드를 스키마로 검증한다. 위반은 서버 결함이므로 INTEGRITY_ERROR."""
    if not isinstance(rec, dict):
        raise integrity(f"{schema} 응답이 객체가 아니다")
    ver = rec.get("pipeline_schema_version")
    if isinstance(ver, str) and re.match(r"^\d+\.\d+$", ver) and ver.split(".")[0] != PIPELINE_SCHEMA_VERSION.split(".")[0]:
        raise BoundaryError("UNSUPPORTED_VERSION", f"{schema}의 계약 MAJOR가 다르다: {ver}")
    errs = sorted(_reader(schema).iter_errors(rec), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        raise integrity(f"{schema} 응답이 스키마를 위반한다", path="/".join(map(str, e.path)), reason=e.message[:200])
    if hashed and _content_hash(rec) != rec["content_hash"]:
        raise integrity(f"{schema}의 content_hash가 내용과 다르다")
    return rec


def check_outgoing(schema: str, rec: Any) -> dict:
    """보내는 레코드를 스키마로 검증한다(CONVENTIONS 4절). 위반은 INVALID_RECORD."""
    errs = list(_validator(schema).iter_errors(rec)) if isinstance(rec, dict) else ["객체가 아니다"]
    if errs:
        raise BoundaryError("INVALID_RECORD", f"{schema}가 스키마를 위반한다")
    return rec


def safe_member_path(name: str) -> tuple[str, ...]:
    if (not name or "\x00" in name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name)
            or ".." in name.split("/")):
        raise integrity("tar에 허용되지 않는 경로가 있다")
    return tuple(p for p in name.split("/") if p not in ("", "."))


def extract_tar(src, dest: Path, max_bytes: int) -> None:
    """src(파일 객체)의 비압축 tar를 dest에 푼다. 일반 파일과 디렉터리만 허용한다. 위반은 INTEGRITY_ERROR."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=src, mode="r:") as tf:
            members, total, seen = [], 0, set()
            for m in tf:  # 풀기 전에 전부 훑어 검사한다
                parts = safe_member_path(m.name)
                if not (m.isreg() or m.isdir()):
                    raise integrity("tar에 일반 파일·디렉터리가 아닌 항목(링크, 특수 파일)이 있다")
                if not parts:
                    if m.isdir():
                        continue
                    raise integrity("tar에 빈 경로가 있다")
                if parts in seen:
                    raise integrity("tar에 중복된 경로가 있다")
                seen.add(parts)
                total += m.size if m.isreg() else 0
                if total > max_bytes or len(members) >= 200_000:
                    raise integrity("tar가 크기 상한을 넘는다")
                members.append((m, parts))
            for m, parts in members:
                target = dest.joinpath(*parts)
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as r, open(target, "xb") as w:
                    shutil.copyfileobj(r, w, 1 << 20)
    except (tarfile.TarError, OSError, EOFError) as e:
        raise integrity("tar를 읽거나 풀 수 없다", reason=type(e).__name__) from None


def build_tar(entries: dict[str, bytes | Path]) -> tempfile._TemporaryFileWrapper:
    """{tar 안의 경로: 바이트 또는 파일 경로}로 임시 파일 tar를 만든다(결정적: 시각·소유자 고정)."""
    out = tempfile.TemporaryFile()
    with tarfile.open(fileobj=out, mode="w:", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(entries):
            v = entries[name]
            info = tarfile.TarInfo(name)
            info.mode = 0o644
            if isinstance(v, bytes):
                info.size = len(v)
                tf.addfile(info, io.BytesIO(v))
            else:
                info.size = Path(v).stat().st_size
                with open(v, "rb") as f:
                    tf.addfile(info, f)
    out.seek(0)
    return out


class _ReadAfterWriteFailure:
    """본문을 쓰다 연결이 끊겨도(EPIPE·ECONNRESET) 서버가 먼저 보낸 응답을 읽는다(U29, 2.5.0).
    waitress 같은 서버는 본문 상한을 넘은 요청에 본문을 읽지 않고 413을 보낸 뒤 닫는다. 표준 라이브러리 클라이언트는
    쓰기 오류에서 바로 멈춰 413을 못 보고 UNAVAILABLE(재시도)로 읽었다. RFC 9112 9.5: 본문을 보내는 클라이언트는
    보내는 동안 오류 응답을 살펴야 한다. Expect: 100-continue는 waitress 3.0.2가 상한 초과에도 100을 먼저 보내
    소용없음을 측정했다(2026-10-30 gpu-dev, 30회 중 30회)."""
    _send_error: Optional[BaseException] = None

    def send(self, data):
        if self._send_error is not None:
            return                       # 이미 끊겼다: 나머지 본문은 버리고 응답 읽기로 간다
        try:
            super().send(data)
        except (BrokenPipeError, ConnectionResetError) as e:
            self._send_error = e

    def getresponse(self):
        r = super().getresponse()        # 응답도 못 읽으면 여기서 OSError가 나고 UNAVAILABLE이 된다
        if self._send_error is not None and r.status < 400:
            r.close()                    # 본문을 다 못 보냈는데 성공이라면 잘린 요청이 처리됐을 수 있다: 믿지 않는다
            raise self._send_error
        return r


class _HTTPConnection(_ReadAfterWriteFailure, http.client.HTTPConnection):
    pass


class _HTTPSConnection(_ReadAfterWriteFailure, http.client.HTTPSConnection):
    pass


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSConnection, req, context=self._context)


class HttpClientBase:
    """생성자는 base_url, token, timeout만 받는다. 환경 변수는 읽지 않는다. 재시도는 호출자가 UNAVAILABLE일 때만 한다."""
    max_tar_bytes = 8 * 2**30      # 풀기 전 총 크기 상한(인스턴스나 서브클래스에서 바꾼다)
    max_body_bytes = 256 * 2**20   # JSON·바이트 응답 상한

    def __init__(self, base_url: str, token: Optional[str], timeout: float = 10.0, *, user: Optional[str] = None):
        """user: 사람 행위자의 인증된 ID를 `X-Openit-User`로 싣는다(3.1.0, D88·HTTP.md I5). 게이트웨이를 거치면 게이트웨이가 인증 계정으로 덮어쓰고,
        게이트웨이 뒤 내부망에서 서비스를 직접 부르는 도구(시험·운영)만 이 값을 쓴다. 이 헤더가 필요한 쓰기(승인·활성화·롤백·검토)가 비공개 속성 없이 부를 수 있게 한다."""
        if urllib.parse.urlsplit(base_url).scheme not in ("http", "https"):
            raise ValueError("base_url은 http:// 또는 https://로 시작해야 한다")
        self._base = base_url.rstrip("/")
        self._token = token
        self._headers: dict[str, str] = {}   # 하위 클래스가 더하는 고정 헤더(예: 내부망의 X-Openit-Device, 2.3.0)
        if user is not None:
            check_id(user, "user")
            self._headers["X-Openit-User"] = user
        self._timeout = timeout
        # ProxyHandler({}): 환경 변수의 프록시를 읽지 않는다
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect, _HTTPHandler, _HTTPSHandler)

    # ---- 요청 ----
    def _scrub(self, text: str) -> str:
        if self._token:
            text = text.replace(self._token, "***")
        return text[:_MAX_MESSAGE]

    def _unavailable(self, message: str, **details) -> BoundaryError:
        return BoundaryError("UNAVAILABLE", self._scrub(message), details or None)

    @staticmethod
    def _q(*parts: str) -> str:
        return "/".join(urllib.parse.quote(str(p), safe="") for p in parts)

    def _open(self, method: str, path: str, query: Optional[dict], data, ctype: Optional[str], accept: str):
        q = {k: v for k, v in (query or {}).items() if v is not None}
        url = self._base + path + ("?" + urllib.parse.urlencode(q) if q else "")
        headers = {"Accept": accept, **self._headers}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        if ctype:
            headers["Content-Type"] = ctype
        if hasattr(data, "read"):
            data.seek(0, 2)
            headers["Content-Length"] = str(data.tell())
            data.seek(0)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            return self._opener.open(req, timeout=self._timeout)
        except urllib.error.HTTPError as e:
            raise self._map_error(e) from None
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as e:
            raise self._unavailable("서비스에 연결하지 못했다", reason=type(e).__name__) from None

    def _map_error(self, e: urllib.error.HTTPError) -> BoundaryError:
        status = e.code
        try:
            raw = e.read(_MAX_ERROR_BODY)
        except Exception:
            raw = b""
        finally:
            e.close()
        if status >= 500 and status != 503:
            return self._unavailable(f"서버 오류 {status}", status=status)
        if status in _TRANSPORT_LIMIT:
            # 전송 계층 한도(본문·요청 줄·헤더가 너무 큼)는 HTTP 서버가 앱을 부르기 전에 낸다(waitress 등, 본문이 BoundaryError가 아닐 수 있다).
            # 같은 요청을 다시 보내도 같으므로 재시도하지 않는다(CONVENTIONS 9절, 2.2.2).
            return BoundaryError("INVALID_RECORD", f"요청이 서버의 전송 한도를 넘었다({status})", {"http_status": status})
        try:
            body = json.loads(raw)
            ok = isinstance(body, dict) and body.get("code") in CODES and isinstance(body.get("message"), str)
        except ValueError:
            ok = False
        if not ok:
            return self._unavailable(f"본문이 BoundaryError가 아닌 응답 {status}", status=status)
        code = _STATUS_CODE.get(status)
        if status == 422:
            code = body["code"] if body["code"] in ("UNSUPPORTED_VERSION", "INTEGRITY_ERROR") else "INTEGRITY_ERROR"
        if code is None:
            return self._unavailable(f"예상 밖의 상태 {status}", status=status)
        # U21(2.5.0): 원래 HTTP 상태를 남긴다. 401(토큰 오류)과 403(권한 오류)이 같은 PERMISSION_DENIED라 운영 로그에서 구분하려면 필요하다
        details = dict(body["details"]) if isinstance(body.get("details"), dict) else {}
        details["http_status"] = status
        ra = _retry_after(e.headers.get("Retry-After") if e.headers else None)
        if ra is not None and status in (409, 429, 503):   # 3.1.2: PUBLIC_API 23~32행 "Retry-After를 따른다" — 머리글 값을 details.retry_after_s로 호출자에게 넘긴다(이전엔 읽지 않았다)
            details["retry_after_s"] = ra
        return BoundaryError(code, self._scrub(body["message"]), details)

    def _read(self, resp, limit: int) -> bytes:
        try:
            data = resp.read(limit + 1)
        except (OSError, http.client.HTTPException) as e:
            raise self._unavailable("응답을 읽지 못했다", reason=type(e).__name__) from None
        finally:
            resp.close()
        if len(data) > limit:
            raise integrity("응답이 크기 상한을 넘는다")
        return data

    def _json(self, method: str, path: str, query: Optional[dict] = None, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        resp = self._open(method, path, query, data, "application/json" if data is not None else None, "application/json")
        raw = self._read(resp, self.max_body_bytes)
        try:
            return json.loads(raw)
        except ValueError:
            raise self._unavailable("JSON이 아닌 응답", status=resp.status) from None

    def _bytes(self, path: str) -> bytes:
        return self._read(self._open("GET", path, None, None, None, "application/octet-stream"), self.max_body_bytes)

    # ---- 레코드와 목록 ----
    def _record(self, path: str, schema: str, query: Optional[dict] = None, *, hashed: bool = False) -> dict:
        return check_record(schema, self._json("GET", path, query), hashed=hashed)

    def _optional(self, path: str, schema: str) -> Optional[dict]:
        body = self._json("GET", path)
        if not isinstance(body, dict) or set(body) != {"item"}:
            raise integrity("{\"item\": ...} 형식이 아니다")
        return None if body["item"] is None else check_record(schema, body["item"])

    def _page(self, path: str, cursor: Optional[str], limit: int, extra: Optional[dict] = None, schema: Optional[str] = None,
              item_check=None) -> tuple[list, Optional[str]]:
        body = self._json("GET", path, {**(extra or {}), "cursor": cursor, "limit": limit})
        check_record("ListEnvelope", body)              # U45(2.6.0): 손 검사 대신 계약 스키마(items 원소 모양은 호출별 스키마가 본다)
        items = body["items"]
        for it in items:
            if schema:
                check_record(schema, it)
            elif item_check:
                item_check(it)
        return items, body.get("next_cursor")

    def _all(self, path: str, **kw) -> list:
        out, cur = [], None
        while True:
            items, cur = self._page(path, cur, 500, **kw)
            out += items
            if cur is None:
                return out

    # ---- tar ----
    def _download_tar(self, path: str, dest: Path, tmp_root: Path) -> None:
        """tar를 받아 dest(없어야 한다)에 푼다. 실패하면 dest를 남기지 않는다."""
        tmp_root.mkdir(parents=True, exist_ok=True)
        resp = self._open("GET", path, None, None, None, TAR_TYPE)
        try:
            with tempfile.TemporaryFile(dir=tmp_root) as spool:
                n, cap = 0, self.max_tar_bytes + (16 << 20)
                try:
                    for chunk in iter(lambda: resp.read(1 << 20), b""):
                        n += len(chunk)
                        if n > cap:
                            raise integrity("tar 응답이 크기 상한을 넘는다")
                        spool.write(chunk)
                except (OSError, http.client.HTTPException) as e:
                    raise self._unavailable("응답을 읽지 못했다", reason=type(e).__name__) from None
                spool.seek(0)
                extract_tar(spool, dest, self.max_tar_bytes)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        finally:
            resp.close()

    @staticmethod
    def _place(staged: Path, final: Path) -> None:
        if final.exists():
            shutil.rmtree(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, final)


def verify_dir(path: Path, expected: str, what: str) -> None:
    if directory_hash(path) != expected:
        raise integrity(f"{what}의 해시가 맞지 않는다")


def verify_json_hash(value: Any, expected: str, what: str) -> None:
    try:
        ok = sha256_hash(value) == expected
    except ValueError:
        ok = False
    if not ok:
        raise integrity(f"{what}의 해시가 맞지 않는다")


def verify_system_prompt(adapter_dir: Path, ref: dict) -> None:
    """어댑터 디렉터리 안의 시스템 프롬프트 파일(SystemPromptRef)이 있고 해시가 맞는지 본다(D75)."""
    from ..canonical import file_hash
    f = adapter_dir.joinpath(*ref["path"].split("/"))
    if not f.is_file() or file_hash(f) != ref["sha256"]:
        raise integrity("시스템 프롬프트 파일이 없거나 system_prompt.sha256과 다르다")


def _retry_after(v) -> Optional[int]:
    """Retry-After 머리글(RFC 9110 10.2.3)의 초 값. HTTP 날짜 형식은 시계에 기대므로 받지 않는다(서버들은 초로 낸다). 0~3600초 밖·형식 오류는 무시."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 3600 else None
