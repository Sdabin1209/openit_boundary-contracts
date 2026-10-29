"""HTTP.md를 따르는 작은 참조 서버(표준 라이브러리 http.server). 적합성 시험용이며 서비스 구현이 아니다.

레코드는 메모리 딕셔너리에 넣어 둔다. 서버는 넣어 둔 내용을 검증하지 않고 그대로 낸다(일부러 틀린 내용을 넣어
클라이언트의 검증을 시험하려는 것이다). 토큰은 {토큰: 역할}이며 역할 "reader"는 읽기 전용이다.
`overrides[경로] = (상태, 콘텐츠 타입, 바이트[, 헤더 딕셔너리])`로 응답을 통째로 바꾸고, `delay`로 응답을 늦춘다.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from boundary_contracts import PIPELINE_SCHEMA_VERSION as V, BoundaryError, content_hash, sha256_hash
from boundary_contracts.clients.datasets import check_publish  # 서버가 클라이언트와 같은 검증 규칙을 쓴다

STATUS = {"INVALID_RECORD": 400, "PERMISSION_DENIED": 403, "NOT_FOUND": 404, "CONFLICT": 409,
          "FAILED_PRECONDITION": 412, "UNSUPPORTED_VERSION": 422, "INTEGRITY_ERROR": 422, "UNAVAILABLE": 503}
NOW = "2026-10-15T00:00:00Z"


def _example(name: str) -> dict:
    import os
    # 왜: 설치된 패키지에서도 읽히도록 conformance/examples(리포지토리 examples/의 심볼릭 링크)를 먼저 본다
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "examples", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _submission_view(x: dict) -> dict:
    return {"submission_id": x["submission_id"], "submitted_at": x["submitted_at"], "submitted_by_role": x["submitted_by_role"],
            "subject": x["subject"], "status": "AWAITING_APPROVAL", "decision_id": None, "approval_id": None,
            "release_id": None, "updated_at": x["submitted_at"]}


def adapter_digest(files: dict[str, bytes]) -> str:
    """canonical.directory_hash와 같은 값(메모리 파일 버전)."""
    return sha256_hash([{"path": p, "sha256": "sha256:" + hashlib.sha256(files[p]).hexdigest()} for p in sorted(files)])


def make_tar(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def ref_of(id_: str, version: str, obj) -> dict:
    return {"id": id_, "version": version, "content_hash": sha256_hash(obj)}


def sealed(rec: dict) -> dict:
    rec = dict(rec)
    rec["content_hash"] = content_hash(rec)
    return rec


class ReferenceServer:
    def __init__(self, tokens: dict[str, str]):
        self.tokens = tokens
        self.overrides: dict[str, tuple] = {}
        self.delay = 0.0
        self.question_sets: dict[str, list[dict]] = {}   # id -> [{"bank", "ref", "reviews", "change"}]
        self.packages: dict[tuple, dict] = {}            # (id, version) -> {"manifest", "files", "report"}
        self.eval_reports: dict[str, bytes] = {}
        self.datasets: dict[tuple, dict] = {}            # (id, version) -> {"manifest", "files": {path: bytes}}
        self.releases: dict[str, dict] = {}              # id -> {"manifest","bank","adapters":{role:{path:bytes}},"pass":bool}
        self.release_order: list[str] = []               # 오래된 것부터
        self.decisions: list[dict] = []                  # 오래된 것부터
        self.pointer: dict | None = None
        self.submissions: dict[str, dict] = {}
        self.receipts: dict[str, dict] = {}
        self.traces: dict[tuple, dict] = {}
        self.cases: list[dict] = []
        self.deid_traces: dict[str, dict] = {}
        self.requests: list[tuple] = []                  # (method, path+query, role)
        self._server = None

    # ---- 데이터 넣기 ----
    def add_question_set(self, id_: str, bank: dict, reviews=(), change=None) -> dict:
        versions = self.question_sets.setdefault(id_, [])
        ref = ref_of(id_, str(bank["version"]), bank)
        versions.append({"bank": bank, "ref": ref, "reviews": list(reviews), "change": change})
        return ref

    # ---- 수명 ----
    def start(self) -> "ReferenceServer":
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                outer._serve(self)

            do_POST = do_PUT = do_GET

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self._server.server_address[1]

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()

    # ---- 요청 처리 ----
    def _serve(self, h: BaseHTTPRequestHandler):
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else b""
        u = urlsplit(h.path)
        query = {k: v[-1] for k, v in parse_qs(u.query).items()}
        if self.delay:
            time.sleep(self.delay)
        auth = h.headers.get("Authorization", "")
        role = self.tokens.get(auth[7:]) if auth.startswith("Bearer ") else None
        dev = h.headers.get("X-Openit-Device")
        if role is None and dev and getattr(self, "trust_device_header", False) and _DEVICE_ID.match(dev):
            # 2.3.0(ADR 0012): 게이트웨이가 클라이언트 인증서로 확인한 기기 ID. 서비스는 이 헤더를 믿는다(게이트웨이 뒤 내부망 전제)
            role = "kiosk:" + dev
        self.requests.append((h.command, h.path, role))
        try:
            if u.path in self.overrides:
                status, ctype, data, *extra = self.overrides[u.path]
            elif u.path in ("/healthz", "/readyz"):
                status, ctype, data, extra = 200, "application/json", b'{"ok":true}', []
            else:
                if role is None:
                    raise BoundaryError("PERMISSION_DENIED", "토큰이 없거나 틀리다")
                status, ctype, data, *extra = self._route(h.command, unquote(u.path), query, body, role)
        except BoundaryError as e:
            status, ctype, data, extra = STATUS[e.code], "application/json", json.dumps(e.to_record(V)).encode(), []
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        for k, v in (extra[0] if extra else {}).items():  # 선택: 네 번째 요소 = 추가 응답 헤더
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        try:
            h.wfile.write(data)
        except OSError:  # 클라이언트가 먼저 끊었다(타임아웃 시험)
            pass

    @staticmethod
    def _j(obj, status=200):
        return status, "application/json", json.dumps(obj, ensure_ascii=False).encode()

    @staticmethod
    def _page(items: list, q: dict):
        try:
            limit, start = int(q.get("limit", 100)), int(q.get("cursor") or 0)
            assert 1 <= limit <= 500 and start >= 0
        except (ValueError, AssertionError):
            raise BoundaryError("INVALID_RECORD", "cursor 또는 limit이 잘못됐다") from None
        end = start + limit
        return ReferenceServer._j({"items": items[start:end], "next_cursor": str(end) if end < len(items) else None})

    def _route(self, method, path, q, body, role):
        def need_write():
            if role == "reader":
                raise BoundaryError("PERMISSION_DENIED", "읽기 토큰으로는 쓸 수 없다")

        def nf(what):
            return BoundaryError("NOT_FOUND", f"{what}이 없다")

        def m(pattern):
            return re.fullmatch(pattern, path)

        J = self._j
        if method == "GET":
            # I1
            if path == "/v1/question-sets":
                return self._page(sorted(self.question_sets), q)
            if g := m(r"/v1/question-sets/([^/]+)/versions"):
                return self._page([v["ref"] for v in self.question_sets.get(g[1], [])], q)
            if g := m(r"/v1/question-sets/([^/]+)/latest"):
                vs = self.question_sets.get(g[1], [])
                if q.get("reviewed_only") == "true":
                    vs = [v for v in vs if v["reviews"] and v["reviews"][-1]["decision"] == "APPROVED"
                          and v["reviews"][-1]["clinical_basis_approved"]]
                if not vs:
                    raise nf("문항 세트")
                return J(vs[-1]["ref"])
            if g := m(r"/v1/question-sets/([^/]+)/versions/([^/]+)(|/reviews|/change)"):
                v = next((v for v in self.question_sets.get(g[1], []) if v["ref"]["version"] == g[2]), None)
                if v is None:
                    raise nf("문항 세트 버전")
                if g[3] == "/reviews":
                    return self._page(v["reviews"], q)
                return J({"item": v["change"]}) if g[3] == "/change" else J(v["bank"])
            # I3
            if path == "/v1/packages":
                return self._page(sorted({k[0] for k in self.packages}), q)
            if g := m(r"/v1/packages/([^/]+)/versions"):
                return self._page([k[1] for k in self.packages if k[0] == g[1]], q)
            if g := m(r"/v1/packages/([^/]+)/versions/([^/]+)(|/adapter)"):
                p = self.packages.get((g[1], g[2]))
                if p is None:
                    raise nf("패키지")
                return (200, "application/x-tar", make_tar(p["files"])) if g[3] else J(p["manifest"])
            if g := m(r"/v1/eval-reports/([^/]+)"):
                if g[1] not in self.eval_reports:
                    raise nf("평가 보고서")
                return 200, "application/octet-stream", self.eval_reports[g[1]]
            # I2
            if path == "/v1/datasets":
                return self._page(sorted({k[0] for k in self.datasets}), q)
            if g := m(r"/v1/datasets/([^/]+)/versions"):
                return self._page([k[1] for k in self.datasets if k[0] == g[1]], q)
            if g := m(r"/v1/datasets/([^/]+)/versions/([^/]+)(|/files|/files/.+)"):
                d = self.datasets.get((g[1], g[2]))
                if d is None:
                    raise nf("데이터셋")
                if not g[3]:
                    return J(d["manifest"])
                if g[3] == "/files":
                    return 200, "application/x-tar", make_tar(d["files"])
                f = g[3][len("/files/"):]
                if f not in d["files"]:
                    raise nf("파일")
                return 200, "application/octet-stream", d["files"][f]
            # I4
            if path == "/v1/active-pointer":
                return J({"item": self.pointer})
            if path == "/v1/releases":
                return self._page([self.releases[r]["manifest"] for r in reversed(self.release_order)], q)
            if g := m(r"/v1/releases/([^/]+)(|/bundle)"):
                r = self.releases.get(g[1])
                if r is None:
                    raise nf("릴리스")
                if not g[2]:
                    return J(r["manifest"])
                if not r["pass"]:
                    raise BoundaryError("FAILED_PRECONDITION", "PASS가 아닌 릴리스")
                files = {"manifest.json": json.dumps(r["manifest"]).encode(), "question_bank.json": json.dumps(r["bank"]).encode()}
                for role_, fs in r["adapters"].items():
                    files.update({f"adapters/{role_}/{p}": d for p, d in fs.items()})
                return 200, "application/x-tar", make_tar(files)
            if path == "/v1/decisions":
                keys = {"question_set_id": ("question_set", "id"), "question_set_version": ("question_set", "version"),
                        "lora_a_id": ("lora_a", "id"), "lora_a_version": ("lora_a", "version"),
                        "lora_b_id": ("lora_b", "id"), "lora_b_version": ("lora_b", "version")}
                out = [d for d in reversed(self.decisions)
                       if all(d["subject"][keys[k][0]][keys[k][1]] == v for k, v in q.items() if k in keys)
                       and ("submission_id" not in q or d.get("submission_id") == q["submission_id"])]
                return self._page(out, q)
            if g := m(r"/v1/decisions/([^/]+)"):
                d = next((d for d in self.decisions if d["decision_id"] == g[1]), None)
                if d is None:
                    raise nf("판정")
                return J(d)
            # I7
            if g := m(r"/v1/cases/([^/]+)"):
                cs = [c for c in self.cases if c["case_id"] == g[1] and ("version" not in q or str(c["version"]) == q["version"])]
                if not cs:
                    raise nf("케이스")
                return J(max(cs, key=lambda c: c["version"]))
            if path == "/v1/submissions":
                items = [_submission_view(x) for x in self.submissions.values()]
                if "status" in q:
                    items = [x for x in items if x["status"] == q["status"]]
                return self._page(items[::-1], q)
            if g := m(r"/v1/submissions/([^/]+)"):
                v = [x for x in self.submissions.values() if x["submission_id"] == g[1]]
                if not v:
                    raise nf("제출")
                return J(_submission_view(v[0]))
            if g := m(r"/v1/submissions/([^/]+)/review-report"):
                if not any(x["submission_id"] == g[1] for x in self.submissions.values()):
                    raise nf("제출")
                return J(dict(_example("ReviewReport"), submission_id=g[1]))
            if path == "/v1/cases":
                cs = self.cases
                for k in ("review_status", "failure_type", "source_release_id"):
                    if k in q:
                        cs = [c for c in cs if c.get(k) == q[k]]
                if "updated_since" in q:
                    cs = [c for c in cs if c["created_at"] >= q["updated_since"]]
                if q.get("latest_only", "true") == "true":
                    latest = {}
                    for c in cs:
                        if c["case_id"] not in latest or c["version"] > latest[c["case_id"]]["version"]:
                            latest[c["case_id"]] = c
                    cs = list(latest.values())
                return self._page(cs, q)
            if g := m(r"/v1/deidentified-traces/([^/]+)"):
                if g[1] not in self.deid_traces:
                    raise nf("비식별 Trace")
                return J(self.deid_traces[g[1]])
            raise nf("경로")
        # 쓰기
        need_write()
        jb = lambda: self._body(body)
        if path == "/v1/packages":
            return self._publish(body)
        if path == "/v1/datasets":
            return self._publish_dataset(body)
        if path == "/v1/submissions":
            b = jb()
            self._same_role(b, role)
            key = sha256_hash(b["subject"])
            if key not in self.submissions:
                self.submissions[key] = {"pipeline_schema_version": V, "submission_id": f"sub-{len(self.submissions) + 1}",
                                         "submitted_at": NOW, "submitted_by_role": role, "subject": b["subject"]}
            return J(self.submissions[key], 202)
        if path == "/v1/approvals":
            b = jb()
            if role != "release-approver":
                raise BoundaryError("PERMISSION_DENIED", "release-approver만 결정할 수 있다")
            if not any(x["submission_id"] == b.get("submission_id") for x in self.submissions.values()):
                raise nf("제출")
            if b.get("decision") == "REJECT" and not b.get("reason"):
                raise BoundaryError("INVALID_RECORD", "반려에는 사유가 필요하다")
            a = dict(_example("GateApproval"), submission_id=b["submission_id"], decision=b["decision"],
                     approver_id=b["approver_id"], approver_role=role)
            if b.get("reason"):
                a["reason"] = b["reason"]
            return J(a, 201)
        if path == "/v1/activate":
            b = jb()
            self._same_role(b, role)
            r = self.releases.get(b.get("release_id"))
            if r is None:
                raise nf("릴리스")
            if not r["pass"]:
                raise BoundaryError("FAILED_PRECONDITION", "PASS가 아닌 릴리스")
            if not self.pointer or self.pointer["release_id"] != b["release_id"]:
                self.pointer = {"pipeline_schema_version": V, "release_id": b["release_id"], "activated_at": NOW,
                                "pointer_version": (self.pointer or {"pointer_version": 0})["pointer_version"] + 1,
                                "cause": "ACTIVATE"}
            return J(self.pointer)
        if path == "/v1/rollback":
            b = jb()
            self._same_role(b, role)
            if b["request_id"] not in self.receipts:
                ok = (self.pointer and self.pointer["release_id"] == b["from_release_id"]
                      and self.releases.get(b["to_release_id"], {}).get("pass"))
                rec = {"pipeline_schema_version": V, "request_id": b["request_id"], "decided_at": NOW,
                       "status": "APPLIED" if ok else "REJECTED"}
                if ok:
                    self.pointer = {"pipeline_schema_version": V, "release_id": b["to_release_id"], "activated_at": NOW,
                                    "pointer_version": self.pointer["pointer_version"] + 1, "cause": "ROLLBACK"}
                    rec["active_pointer"] = self.pointer
                else:
                    rec["reason"] = "조건 불충족"
                self.receipts[b["request_id"]] = rec
            return J(self.receipts[b["request_id"]])
        if path == "/v1/traces":
            b = jb()
            key = (b["session_id"], b["turn_id"])
            status = "DUPLICATE" if key in self.traces else "ACCEPTED"
            self.traces.setdefault(key, b)
            return J({"pipeline_schema_version": V, "session_id": key[0], "turn_id": key[1], "status": status,
                      "received_at": NOW})
        raise nf("경로")

    @staticmethod
    def _body(body):
        try:
            b = json.loads(body)
            assert isinstance(b, dict)
            return b
        except (ValueError, AssertionError):
            raise BoundaryError("INVALID_RECORD", "본문이 JSON 객체가 아니다") from None

    @staticmethod
    def _same_role(b, role):
        if b.get("requested_by_role") != role:
            raise BoundaryError("PERMISSION_DENIED", "요청한 역할이 토큰의 역할과 다르다")

    def _publish(self, body):
        try:
            with tarfile.open(fileobj=io.BytesIO(body), mode="r:") as tf:
                files = {m.name: tf.extractfile(m).read() for m in tf if m.isreg()}
            manifest = json.loads(files["manifest.json"])
        except (tarfile.TarError, KeyError, ValueError):
            raise BoundaryError("INVALID_RECORD", "publish 본문이 잘못됐다") from None
        adapter = {n[len("adapter/"):]: d for n, d in files.items() if n.startswith("adapter/")}
        if adapter_digest(adapter) != manifest.get("adapter_hash"):
            raise BoundaryError("INTEGRITY_ERROR", "어댑터 해시가 맞지 않는다")
        key = (manifest["package_id"], manifest["version"])
        old = self.packages.get(key)
        if old:
            if old["manifest"]["content_hash"] != manifest["content_hash"]:
                raise BoundaryError("CONFLICT", "같은 ID·버전에 다른 내용")
            return self._j(old["manifest"])
        self.packages[key] = {"manifest": manifest, "files": adapter}
        self.eval_reports[manifest["eval_report_ref"]] = files.get("eval_report", b"")
        return self._j(manifest, 201)


def _publish_dataset(self, body):
    from boundary_contracts import validator
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:") as tf:
            files = {m.name: tf.extractfile(m).read() for m in tf if m.isreg()}
        manifest = json.loads(files["manifest.json"])
    except (tarfile.TarError, KeyError, ValueError):
        raise BoundaryError("INVALID_RECORD", "publish 본문이 잘못됐다") from None
    if list(validator("DatasetManifest").iter_errors(manifest)):
        raise BoundaryError("INVALID_RECORD", "manifest가 DatasetManifest 스키마를 위반한다")
    if content_hash(manifest) != manifest["content_hash"]:
        raise BoundaryError("INTEGRITY_ERROR", "manifest의 content_hash가 내용과 다르다")
    data = {n[len("files/"):]: d for n, d in files.items() if n.startswith("files/")}
    if set(data) != {f["path"] for f in manifest["files"]}:
        raise BoundaryError("INVALID_RECORD", "파일 집합이 manifest와 다르다")
    check_publish(manifest, lambda p: data[p])
    key = (manifest["dataset_id"], manifest["version"])
    old = self.datasets.get(key)
    if old:
        if old["manifest"]["content_hash"] != manifest["content_hash"]:
            raise BoundaryError("CONFLICT", "같은 ID·버전에 다른 내용")
        return self._j(old["manifest"])
    self.datasets[key] = {"manifest": manifest, "files": data}
    return self._j(manifest, 201)


ReferenceServer._publish_dataset = _publish_dataset


class RuntimeReferenceServer(ReferenceServer):
    """HTTP.md I9(모델 추론 서버)를 따르는 참조 서버(계약 2.0.0). I1~I7 서버와 경로(`/v1/releases/{id}`)가 겹치므로 따로 띄운다.

    실제 모델은 없다. `extract_fn(요청 dict) -> dict`와 `respond_fn(요청 dict) -> (문장, outcome)`을 바꿔 끼워 동작을 정한다.
    기본값은 예시의 고정 출력이다. `extract_fn`의 출력이 `ActionExtraction`을 어기면 서버는 그대로 내지 않고 503 OUTPUT_INVALID(D75)를 낸다. 요청 본문은 서버가 스키마로 검증하고(400 INVALID_RECORD), 적재되지 않은 릴리스는 404다.
    `available[릴리스 ID]`는 PUT 때의 결과다: "ok"(200 LOADED), "loading"(첫 PUT은 202 LOADING, 다음부터 LOADED),
    "not_pass"(412), 없으면 404. 토큰 역할 "reader"는 PUT(적재)을 할 수 없고 추론 POST는 할 수 있다.
    """

    def __init__(self, tokens: dict[str, str]):
        super().__init__(tokens)
        self.available: dict[str, str] = {}
        self.loaded: set[str] = set()
        self._loading: set[str] = set()
        self.extract_fn = lambda req: _example("ActionExtraction.next")
        self.respond_fn = lambda req: ("네, 알겠습니다. 다음 질문을 드리겠습니다.", "ok")
        self.attempts = 1
        self.protections = ""

    def _headers(self, outcome: str) -> dict:
        h = {"X-Openit-Outcome": outcome, "X-Openit-Attempts": str(self.attempts)}
        if self.protections:
            h["X-Openit-Protections"] = self.protections
        return h

    def _checked(self, body: bytes, schema: str) -> dict:
        from boundary_contracts import validator
        b = self._body(body)
        if list(validator(schema).iter_errors(b)):
            raise BoundaryError("INVALID_RECORD", f"본문이 {schema} 스키마를 위반한다")
        return b

    def _route(self, method, path, q, body, role):
        J = self._j
        if path == "/v1/info" and method == "GET":
            return J({"service": "model-runtime-reference", "runtime_version": "0.0.0", "supported_contract_versions": [1],
                      "backend": "fake", "loaded": sorted(self.loaded), "serving_config_hash": {}})
        g = re.fullmatch(r"/v1/releases/([^/]+)(|/extract|/respond)", path)
        if not g:
            raise BoundaryError("NOT_FOUND", "경로가 없다")
        rid, op = g[1], g[2]
        if not op:
            if method == "PUT":
                if role == "reader":
                    raise BoundaryError("PERMISSION_DENIED", "읽기 토큰으로는 적재할 수 없다")
                mode = self.available.get(rid)
                if mode is None:
                    raise BoundaryError("NOT_FOUND", "릴리스가 없다")
                if mode == "not_pass":
                    raise BoundaryError("FAILED_PRECONDITION", "승인되지 않은 릴리스")
                if mode == "loading" and rid not in self._loading and rid not in self.loaded:
                    self._loading.add(rid)
                    return J({"release_id": rid, "state": "LOADING", "error": None}, 202)
                self.loaded.add(rid)
                return J({"release_id": rid, "state": "LOADED", "error": None})
            if method == "GET":
                state = "LOADED" if rid in self.loaded else "LOADING" if rid in self._loading else "ABSENT"
                return J({"release_id": rid, "state": state, "error": None})
            raise BoundaryError("NOT_FOUND", "경로가 없다")
        if method != "POST":
            raise BoundaryError("NOT_FOUND", "경로가 없다")
        if rid not in self.loaded:
            raise BoundaryError("NOT_FOUND", "적재되지 않은 릴리스")
        if op == "/extract":
            # 2.2.0: 본문은 ExtractRequest{input, flow} 또는 2.x 호환 ActionExtractionInput. 어느 쪽인지는 스키마로 판정한다
            from boundary_contracts import validator
            parsed = self._body(body)
            flow = None
            if isinstance(parsed, dict) and "flow" in parsed:
                full = self._checked(body, "ExtractRequest")
                req, flow = full["input"], full["flow"]
            else:
                req = self._checked(body, "ActionExtractionInput")
            out = self.extract_fn(req)
            bad = bool(list(validator("ActionExtraction").iter_errors(out)))
            if not bad and flow is not None:
                from boundary_contracts.action_rules import check_action_extraction
                bad = bool(check_action_extraction(req, out, flow))   # flow가 있으면 규칙 보증(HTTP.md I9)
            if bad:
                # D75: 값을 지어내지 않는다. 모델 출력이 끝내 형식을 못 지키면 503 UNAVAILABLE + details.reason=OUTPUT_INVALID
                raise BoundaryError("UNAVAILABLE", "모델 출력이 ActionExtraction 형식을 지키지 못했다",
                                    {"reason": "OUTPUT_INVALID", "attempts": self.attempts})
            return 200, "application/json", json.dumps(out, ensure_ascii=False).encode(), self._headers("ok")
        req = self._checked(body, "ResponseRequest")
        text, outcome = self.respond_fn(req)
        return 200, "text/plain; charset=utf-8", text.encode("utf-8"), self._headers(outcome)


class StaffCallReferenceServer(ReferenceServer):
    """PUBLIC_API.md G절(직원 호출 재알림·실패 기록, 계약 2.1.0)을 따르는 참조 서버. 다른 참조 서버와 경로가 겹치지 않지만 따로 띄운다.

    토큰 역할: "kiosk-1"·"kiosk-2"(기기별 키오스크), "staff". 세션은 만든 기기(`sessions[id] = 역할`)만 쓸 수 있다(다른 기기는 404, staff는 403).
    `add_alert(session_id, owner)`로 OPEN 알림을 넣는다. `deliver_fn()`은 재전달 결과('DELIVERED'|'DELIVERY_FAILED')를 정한다.
    `clock()`은 초 단위 시각(시험이 바꿔 끼운다). 간격·상한은 서비스 설정에 해당하는 값이며 계약이 아니다(기본 30초·10회, 측정 안 함).
    """

    def __init__(self, tokens: dict[str, str], retry_after_s: int = 30, max_retries: int = 10):
        super().__init__(tokens)
        self.retry_after_s, self.max_retries = retry_after_s, max_retries
        self.sessions: dict[str, str] = {}
        self.alerts: dict[str, dict] = {}
        self.deliver_fn = lambda: "DELIVERED"
        self.clock = time.monotonic
        self._last: dict[str, float] = {}
        self._seen: dict[tuple, tuple] = {}   # (kind, session_id, turn_id) -> (요청 지문, 응답)

    def add_alert(self, session_id: str, owner: str, *, delivery: str = "DELIVERY_FAILED", pause_reason: str = "RISK") -> dict:
        self.sessions[session_id] = owner
        a = {"alert_id": "al-" + session_id, "session_id": session_id, "kind": "RISK_STOP", "created_at": NOW, "status": "OPEN",
             "resolved_by_decision": None, "resolved_at": None, "pause_reason": pause_reason, "delivery_attempts": 1,
             "last_delivery_status": delivery}
        self.alerts[session_id] = a
        return a

    def _route(self, method, path, q, body, role):
        from boundary_contracts import validator
        if path == "/v1/staff/alerts" and method == "GET":  # 직원 콘솔 목록(StaffAlertPage). 최신부터
            if role != "staff":
                raise BoundaryError("PERMISSION_DENIED", "직원 토큰만 볼 수 있다")
            items = [a for a in reversed(list(self.alerts.values())) if "status" not in q or a["status"] == q["status"]]
            return self._page(items, q)
        g = re.fullmatch(r"/v1/sessions/([^/]+)/staff-call/(retry|report)", path)
        if not g or method != "POST":
            raise BoundaryError("NOT_FOUND", "경로가 없다")
        sid, op = g[1], g[2]
        if not role.startswith("kiosk"):
            raise BoundaryError("PERMISSION_DENIED", "키오스크 토큰만 호출할 수 있다")
        if self.sessions.get(sid) != role:
            raise BoundaryError("NOT_FOUND", "세션이 없다")  # 다른 기기의 세션도 404
        b = self._body(body)
        schema = "StaffCallRetryRequest" if op == "retry" else "StaffCallReport"
        if list(validator(schema).iter_errors(b)):
            raise BoundaryError("INVALID_RECORD", f"본문이 {schema} 스키마를 위반한다")
        alert = self.alerts.get(sid)
        key = (op, sid, b["turn_id"])
        if key in self._seen:
            fp, resp = self._seen[key]
            if fp != json.dumps(b, sort_keys=True):
                raise BoundaryError("CONFLICT", "같은 turn_id에 다른 내용", {"reason": "TURN_ID_REUSED"})
            return self._j(resp)
        if op == "report":
            if alert is None:
                raise BoundaryError("CONFLICT", "알림이 없다", {"reason": "NO_OPEN_ALERT"})
            alert["manual_notice_outcome"], alert["manual_notice_reported_at"] = b["outcome"], NOW
            self._seen[key] = (json.dumps(b, sort_keys=True), dict(alert))
            return self._j(alert)
        if alert is None or alert["status"] != "OPEN":
            raise BoundaryError("CONFLICT", "OPEN 알림이 없다", {"reason": "NO_OPEN_ALERT"})
        now = self.clock()
        wait = self.retry_after_s - (now - self._last[sid]) if sid in self._last else 0
        over = alert["delivery_attempts"] - 1 >= self.max_retries
        if over or wait > 0:
            n = self.retry_after_s if over else int(wait) + 1
            err = BoundaryError("UNAVAILABLE", "재알림이 너무 잦다", {"reason": "RETRY_LIMIT" if over else "INTERVAL", "retry_after_s": n})
            # PUBLIC_API.md G절: 상한 초과는 기다려도 풀리지 않으므로 Retry-After를 붙이지 않는다
            return 429, "application/json", json.dumps(err.to_record(V)).encode(), ({} if over else {"Retry-After": str(n)})
        self._last[sid] = now
        alert["delivery_attempts"] += 1
        alert["last_delivery_status"] = self.deliver_fn()
        resp = {"alert_id": alert["alert_id"], "staff_alert": alert["last_delivery_status"],
                "delivery_attempts": alert["delivery_attempts"], "retry_after_s": self.retry_after_s}
        self._seen[key] = (json.dumps(b, sort_keys=True), resp)
        return self._j(resp)


_DEVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SUBJECT_REF = re.compile(r"^[A-Za-z0-9._:/#=+-]{1,128}$")


class PublicApiReferenceServer(StaffCallReferenceServer):
    """PUBLIC_API.md 전체(I10) 중 화면 쪽 호출의 최소 모사: 세션 시작·발화·종료·상태·개입 결정. 직원 알림 목록과 재알림·실패 기록은
    부모 `StaffCallReferenceServer`가 이미 구현하므로 합쳐서 쓴다. 상태 기계(ACTIVE -> PAUSED_RISK -> ACTIVE|ENDED), turn_id 멱등,
    확정되지 않은 턴(NOT_COMMITTED)의 재처리, 기기 토큰 소유 확인(다른 기기 404, staff 403)을 모사한다.

    `turn_fn(utterance) -> (response_text, committed: bool, risk: bool)`로 서비스 판단을 대신한다(기본: 안내 문장, 확정, 위험 아님).
    `states[session_id]["inflight"]`에 turn_id를 넣으면 같은 turn_id가 처리 중인 것으로 보고 409 TURN_IN_PROGRESS를 낸다.
    모사하지 않는 것: 결과 조회(B), 직원 세션 조회(C), 위험 신호 입력(D), `X-Openit-User` 행위자 기록(E), 푸시/SSE.
    """

    def __init__(self, tokens: dict[str, str], retry_after_s: int = 30, max_retries: int = 10):
        super().__init__(tokens, retry_after_s, max_retries)
        self.states: dict[str, dict] = {}
        self.trust_device_header = True   # 2.3.0: 키오스크는 X-Openit-Device(게이트웨이 mTLS)로도 식별된다
        self.turn_fn = lambda utterance: ("다음 질문입니다.", True, False)
        self.processed: list[str] = []   # 실제로 처리한 turn_id(멱등 시험용)

    @staticmethod
    def _fi(text, session_id=None, committed=True, alert="NONE"):
        sig = None if committed else {"session_id": session_id, "write_committed": "NOT_COMMITTED", "staff_alert": alert}
        return {"response_text": text, "turn_failure_signal": sig}

    def _own(self, sid, role):
        if not role.startswith("kiosk"):
            raise BoundaryError("PERMISSION_DENIED", "키오스크 토큰만 호출할 수 있다")
        if self.sessions.get(sid) != role or sid not in self.states:
            raise BoundaryError("NOT_FOUND", "세션이 없다")  # 다른 기기의 세션도 404
        return self.states[sid]

    @staticmethod
    def _msg(b, sid, kind, extra=()):
        allowed = {"session_id", "kind", *extra}
        if set(b) - allowed or b.get("kind") != kind or b.get("session_id") != sid or not _SESSION_ID.match(str(sid)):
            raise BoundaryError("INVALID_RECORD", "본문이 FrontendMessage가 아니다")

    def _route(self, method, path, q, body, role):
        if path == "/v1/sessions" and method == "POST":
            if not role.startswith("kiosk"):
                raise BoundaryError("PERMISSION_DENIED", "키오스크 토큰만 호출할 수 있다")
            b = self._body(body)
            sid = b.get("session_id")
            self._msg(b, sid, "SESSION_START", ("subject_ref",))
            if "subject_ref" in b and not (isinstance(b["subject_ref"], str) and _SUBJECT_REF.match(b["subject_ref"])):
                raise BoundaryError("INVALID_RECORD", "subject_ref 형식이 아니다")
            if sid in self.states:
                raise BoundaryError("CONFLICT", "이미 있는 세션이다")
            self.sessions[sid] = role
            self.states[sid] = {"state": "ACTIVE", "resume_text": None, "pause_reason": None, "turns": {}, "inflight": set(),
                                "subject_ref": b.get("subject_ref")}
            return self._j(self._fi("안녕하세요. 문진을 시작하겠습니다."), 201)
        g = re.fullmatch(r"/v1/sessions/([^/]+)/(turns|end|state|intervention)", path)
        if not g:
            return super()._route(method, path, q, body, role)
        sid, op = g[1], g[2]
        if op == "intervention":
            if method != "POST":
                raise BoundaryError("NOT_FOUND", "경로가 없다")
            if role != "staff":
                raise BoundaryError("PERMISSION_DENIED", "직원 토큰만 호출할 수 있다")
            st = self.states.get(sid)
            if st is None:
                raise BoundaryError("NOT_FOUND", "세션이 없다")
            b = self._body(body)
            if set(b) != {"session_id", "decision", "turn_id"} or b["session_id"] != sid or b["decision"] not in ("RESUME", "END") \
                    or not isinstance(b["turn_id"], str) or not b["turn_id"]:
                raise BoundaryError("INVALID_RECORD", "본문이 InterventionDecision이 아니다")
            key = ("intervention", sid, b["turn_id"])
            if key in self._seen:
                fp, resp = self._seen[key]
                if fp != json.dumps(b, sort_keys=True):
                    raise BoundaryError("CONFLICT", "같은 turn_id에 다른 내용", {"reason": "TURN_ID_REUSED"})
                return self._j(resp)
            if st["state"] != "PAUSED_RISK":
                raise BoundaryError("CONFLICT", "멈추지 않은 세션이다")
            alert = self.alerts.get(sid)
            if alert:
                alert.update(status="RESOLVED", resolved_by_decision=b["decision"], resolved_at=NOW)
            if b["decision"] == "RESUME":
                st.update(state="ACTIVE", resume_text="이어서 문진을 진행하겠습니다.", pause_reason=None)
                resp = self._fi(st["resume_text"])
            else:
                st.update(state="ENDED", pause_reason=None)
                resp = self._fi(None)
            self._seen[("intervention", sid, b["turn_id"])] = (json.dumps(b, sort_keys=True), resp)
            return self._j(resp)
        st = self._own(sid, role)
        if op == "state":
            if method != "GET":
                raise BoundaryError("NOT_FOUND", "경로가 없다")
            out = {"session_id": sid, "state": st["state"], "resume_text": st["resume_text"]}
            if st["pause_reason"]:
                out["pause_reason"] = st["pause_reason"]
            return self._j(out)
        if method != "POST":
            raise BoundaryError("NOT_FOUND", "경로가 없다")
        b = self._body(body)
        if op == "end":
            self._msg(b, sid, "SESSION_END")
            st["state"] = "ENDED"  # 끝난 세션에 다시 종료해도 같은 결과(멱등)
            return self._j(self._fi(None))
        tid = b.pop("turn_id", None)  # turn_id는 API 봉투 필드다: 떼어 낸 나머지를 FrontendMessage로 본다
        self._msg(b, sid, "UTTERANCE", ("utterance",))
        if not isinstance(tid, str) or not tid or not isinstance(b.get("utterance"), str):
            raise BoundaryError("INVALID_RECORD", "turn_id 또는 utterance가 없다")
        fp = json.dumps(b, sort_keys=True, ensure_ascii=False)
        if tid in st["turns"]:  # 확정된 턴만 저장되어 있다
            sfp, resp = st["turns"][tid]
            if sfp != fp:
                raise BoundaryError("CONFLICT", "같은 turn_id에 다른 내용", {"reason": "TURN_ID_REUSED"})
            return self._j(resp)
        if tid in st["inflight"]:
            err = BoundaryError("CONFLICT", "같은 turn_id가 처리 중이다", {"reason": "TURN_IN_PROGRESS"})
            return 409, "application/json", json.dumps(err.to_record(V)).encode(), {"Retry-After": "1"}
        if st["state"] == "ENDED":
            raise BoundaryError("CONFLICT", "끝난 세션이다")
        text, committed, risk = self.turn_fn(b["utterance"])
        self.processed.append(tid)
        st["resume_text"] = None  # 다음 발화 턴이 접수되면 resume_text는 null이 된다
        alert_state = "NONE"
        if risk:
            st.update(state="PAUSED_RISK", pause_reason="RISK")
            self.add_alert(sid, role, delivery="DELIVERED")
            alert_state = "DELIVERED"
        resp = self._fi(text, sid, committed, alert_state)
        if committed:  # 확정되지 못한 턴은 결과를 고정하지 않아 재전송이 다시 처리된다(D86)
            st["turns"][tid] = (fp, resp)
        return self._j(resp)
