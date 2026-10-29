"""클라이언트 시험의 공통 준비: 참조 서버와 올바른 레코드. 토큰은 시험용 가짜 값이다."""
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boundary_contracts import sha256_hash  # noqa: E402
from conformance.servers import ReferenceServer, adapter_digest, ref_of, sealed  # noqa: E402

READ, WRITE, OTHER = "fake-read-token", "fake-write-token", "fake-other-token"
APPROVER = "fake-approver-token"
TOKENS = {READ: "reader", WRITE: "operator", OTHER: "model-lab", APPROVER: "release-approver"}


def example(name):
    return copy.deepcopy(json.loads((ROOT / "examples" / f"{name}.json").read_text()))


def bank(n):
    return {"version": n, "questions": [{"question_id": f"q{n}", "text": "질문"}]}


PROMPT_A = "시험용 LoRA-A 시스템 프롬프트".encode()
PROMPT_B = "시험용 LoRA-B 시스템 프롬프트".encode()
FILES_A = {"adapter_config.json": b'{"r": 8}', "sub/weights.bin": b"\x00\x01\x02", "system_prompt.txt": PROMPT_A}
FILES_B = {"adapter_config.json": b'{"r": 4}', "system_prompt.txt": PROMPT_B}


def release(release_id, passed=True):
    b = bank(3)
    m = example("ReleaseManifest")
    m["release_id"] = release_id
    m["question_set"] = ref_of("qs-main", "3", b)
    for role, files in (("LORA_A", FILES_A), ("LORA_B", FILES_B)):
        m["adapters"][role]["adapter_hash"] = adapter_digest(files)
        m["adapters"][role]["system_prompt"] = {"path": "system_prompt.txt",
                                                "sha256": "sha256:" + hashlib.sha256(files["system_prompt.txt"]).hexdigest()}
    return {"manifest": sealed(m), "bank": b, "adapters": {"LORA_A": FILES_A, "LORA_B": FILES_B}, "pass": passed}


def package_manifest(files=FILES_A, version="1.2.0"):
    m = example("ModelPackageManifest")
    m["version"] = version
    m["adapter_hash"] = adapter_digest(files)
    m["system_prompt"] = {"path": "system_prompt.txt", "sha256": "sha256:" + hashlib.sha256(files["system_prompt.txt"]).hexdigest()}
    return sealed(m)


def decision(i, submission_id="sub-1", result="PASS"):
    d = example("GateDecision.pass")
    d["decision_id"] = f"gd-{i}"
    d["submission_id"] = submission_id
    return d


def case(case_id, version, status="PENDING"):
    c = example("FailureCase")
    c.update(case_id=case_id, version=version, review_status=status)
    return c


def make_server():
    s = ReferenceServer(TOKENS)
    approved = example("ReviewRecord")
    for n in (1, 2, 3):
        s.add_question_set("qs-main", bank(n), reviews=[approved] if n == 2 else [],
                           change=None if n == 1 else example("ChangeClassification"))
    s.add_question_set("qs-other", bank(1))
    for rid, ok in (("rel-0001", True), ("rel-0002", False), ("rel-0003", True)):
        s.releases[rid] = release(rid, ok)
        s.release_order.append(rid)
    s.decisions = [decision(1, "sub-1"), decision(2, "sub-2"), decision(3, "sub-1")]
    s.cases = [case("fc-1", 1), case("fc-1", 2, "CONFIRMED"), case("fc-2", 1)]
    s.deid_traces["tr-1"] = example("OpsFeedbackDeidentifiedTrace")   # 계약을 지키는 비식별 Trace(U45: 클라이언트가 스키마로 검증)
    return s
