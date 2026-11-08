#!/usr/bin/env python3
"""schemas/ 의 모든 스키마가 Draft 2020-12 로 유효하고, 모든 examples/ 가 대응 스키마를 통과하며, 위반 예시가 거부되는지 검사한다."""
import copy, glob, json, os, sys, jsonschema
from boundary_contracts import format_checker as _bc_format_checker  # 형식(format) 검증기가 없으면 조용히 넘기지 않고 실패한다(계약 3.5.0)
here = os.path.dirname(os.path.abspath(__file__)); base = "file://" + here + "/schemas/"
common = json.load(open(here + "/schemas/_common.schema.json"))
from boundary_contracts import validator
from boundary_contracts.http_contracts import HttpContract, catalog


def val(name):
    return validator(name)
def ex(name): return json.load(open(f"{here}/examples/{name}.json"))
bad = 0
names = sorted(os.path.basename(p)[:-12] for p in glob.glob(here + "/schemas/*.schema.json") if not os.path.basename(p).startswith("_"))
for n in names:
    files = sorted(os.path.basename(p)[:-5] for p in glob.glob(f"{here}/examples/{n}*.json") if os.path.basename(p)[:-5].split(".")[0] == n)
    if not files: print("FAIL 예시 없음:", n); bad += 1
    for f in files:
        errs = [e.message for e in val(n).iter_errors(ex(f))]
        print("OK  " if not errs else "FAIL", f, errs); bad += bool(errs)
def neg(label, schema, base_ex, mutate):
    global bad
    d = copy.deepcopy(ex(base_ex)); mutate(d)
    rejected = bool(list(val(schema).iter_errors(d)))
    print("OK  " if rejected else "FAIL", "거부되어야 함:", label); bad += (not rejected)
neg("주입 파일을 시작 프로세스가 아닌 쪽이 연다", "ContainerInputs", "ContainerInputs", lambda d: d["roles"]["default"]["files"][0].update(opened_by="dropped-user"))
neg("사용자를 이름으로 적음", "ContainerInputs", "ContainerInputs", lambda d: d["roles"]["default"]["process"].update(uid="app"))
neg("쓰기 경로가 상대 경로", "ContainerInputs", "ContainerInputs", lambda d: d["roles"]["default"]["writable"][0].update(path="data"))
neg("역할 변수가 없는데 역할이 둘", "ContainerInputs", "ContainerInputs", lambda d: d["roles"].update(extra=d["roles"]["default"]))
neg("이미지 라벨에 주입 선언 없음", "ImageLabels", "ImageLabels", lambda d: d.pop("io.openit.inputs"))
neg("PASS인데 release_id 없음", "GateDecision", "GateDecision.pass", lambda d: d.pop("release_id"))
neg("PASS인데 FAIL 검사 포함", "GateDecision", "GateDecision.pass", lambda d: d["checks"][0].update(result="FAIL"))
neg("REJECT인데 release_id 있음", "GateDecision", "GateDecision.reject", lambda d: d.update(release_id="x"))
neg("버전 형식 위반", "ReleaseManifest", "ReleaseManifest", lambda d: d.update(pipeline_schema_version="1"))
neg("content_hash 형식 위반", "ReleaseManifest", "ReleaseManifest", lambda d: d["lora_a"].update(content_hash="abc"))
neg("릴리스 ID 없는 봉투", "TraceEnvelope", "TraceEnvelope", lambda d: d.pop("release_id"))
neg("승인 아닌 검수에 사유 없음", "ReviewRecord", "ReviewRecord", lambda d: d.update(decision="REJECTED"))
neg("변경 종류 비어 있음", "ChangeClassification", "ChangeClassification", lambda d: d.update(change_kinds=[]))
neg("실패 사례 출처 시드에 seed_case_id 없음", "ResponseSample", "ResponseSample", lambda d: (d.update(origin="FAILURE_CASE_SEED"), d.pop("seed_case_id", None)))
neg("시나리오 분리 미확인 데이터셋", "DatasetManifest", "DatasetManifest", lambda d: d.update(scenario_disjoint_across_splits=False))
neg("비식별 안 된 실패 사례", "FailureCase", "FailureCase", lambda d: d.update(deidentified=False))
neg("근거 없는 롤백 요청", "RollbackRequest", "RollbackRequest", lambda d: d.update(evidence_refs=[]))
neg("모델 패키지에 알 수 없는 상태 필드", "ModelPackageManifest", "ModelPackageManifest", lambda d: d.update(status="APPROVED"))
neg("REJECT인데 reject_codes 없음", "GateDecision", "GateDecision.reject", lambda d: d.pop("reject_codes"))
neg("PASS에 SKIPPED 검사 포함", "GateDecision", "GateDecision.pass", lambda d: d["checks"][0].update(result="SKIPPED"))
neg("PASS인데 reject_codes 있음", "GateDecision", "GateDecision.pass", lambda d: d.update(reject_codes=["CHECK_FAILED"]))
neg("adapters에 LORA_B 없음", "ReleaseManifest", "ReleaseManifest", lambda d: d["adapters"].pop("LORA_B"))
# 지표 이름 레지스트리: 예시 보고서의 지표 이름이 ACTIVE이고, 폐기 이름을 넣으면 거부되는지, METRICS.md 표가 생성물과 같은지
sys.path.insert(0, here)
import subprocess
from boundary_contracts import metric_name_problems
for _k in ("EvaluationReport", "ReviewReport"):
    _p = metric_name_problems(ex(_k)); print("OK  " if not _p else "FAIL", f"{_k} 지표 이름은 ACTIVE", _p); bad += bool(_p)
_d = ex("EvaluationReport"); _d["metrics"][0]["name"] = "risk_signal_recall"
_p = metric_name_problems(_d); print("OK  " if _p else "FAIL", "폐기 지표 이름은 거부"); bad += not _p
_r = subprocess.run([sys.executable, here + "/tools/gen_metrics_md.py", "--check"])
print("OK  " if _r.returncode == 0 else "FAIL", "METRICS.md 표는 metrics.json에서 생성한 것과 같다"); bad += _r.returncode != 0
neg("알 수 없는 오류 코드", "BoundaryError", "BoundaryError", lambda d: d.update(code="WHATEVER"))
neg("적용된 롤백에 포인터 없음", "RollbackReceipt", "RollbackReceipt", lambda d: d.pop("active_pointer"))
neg("거부된 롤백에 사유 없음", "RollbackReceipt", "RollbackReceipt", lambda d: (d.update(status="REJECTED"), d.pop("active_pointer")))
neg("포인터 버전 0", "ActivePointer", "ActivePointer", lambda d: d.update(pointer_version=0))
# 확장 필드는 허용되어야 한다
d = ex("ReleaseManifest"); d["ext"] = {"model-lab": {"note": "x"}}
errs = list(val("ReleaseManifest").iter_errors(d)); print("OK  " if not errs else "FAIL", "ext 허용"); bad += bool(errs)
# 외부 데이터는 설치된 소유자 스키마로만 검증한다. 누락은 검증 실패다.
_tt = validator("TraceEnvelope")
from boundary_contracts.schema_sources import external_schema
_survey_turn = external_schema("https://openit.example/survey/v1/TurnTrace.json")
errs = list(jsonschema.Draft202012Validator(_survey_turn, format_checker=_bc_format_checker(_survey_turn)).iter_errors(ex("TraceEnvelope")["trace"]))
print("OK  " if not errs else "FAIL", "TraceEnvelope.trace는 설치된 TurnTrace를 통과")
bad += bool(errs)
for service in catalog()["services"]:
    HttpContract(service).lint()
    print("OK  ", service, "HTTP 계약 참조가 모두 해석된다")
d = ex("FailureCase"); d.pop("question_set", None); d.pop("expected_kind"); d.pop("reviewed_input"); d["expected"] = ex("ActionExtraction.next")
errs = [e.message for e in val("FailureCase").iter_errors(d)]; print("OK  " if not errs else "FAIL", "expected_kind 없는 옛 FailureCase도 expected 가 ActionExtraction 이면 유효", errs); bad += bool(errs)
neg("expected_kind 없는 FailureCase 의 expected 객체가 ActionExtraction 이 아님(3.7.0)", "FailureCase", "FailureCase", lambda d: (d.pop("expected_kind"), d.pop("reviewed_input"), d.update(expected={})))
neg("LORA_A 인데 expected 가 ActionExtraction 이 아님(3.7.0)", "FailureCase", "FailureCase", lambda d: d.update(expected={"x": 1}))
neg("LORA_B 인데 reviewed_input 이 ResponseRequest 가 아님(3.7.0)", "FailureCase", "FailureCase", lambda d: d.update(expected_kind="LORA_B", expected="네."))
neg("reviewed_input 만 있고 expected_kind·expected 둘 다 없음(판별 불가)", "FailureCase", "FailureCase", lambda d: d.pop("expected_kind"))
d = ex("FailureCase"); d.pop("expected_kind"); d["expected"] = "네, 알겠습니다."; d["reviewed_input"] = ex("ResponseRequest.start")
errs = [e.message for e in val("FailureCase").iter_errors(d)]; print("OK  " if not errs else "FAIL", "kind 없는 옛 레코드: expected 문자열이면 LORA_B 로 판별해 reviewed_input ResponseRequest 허용", errs); bad += bool(errs)
neg("kind 없는 옛 레코드: expected 문자열인데 reviewed_input 이 ActionExtractionInput", "FailureCase", "FailureCase", lambda d: (d.pop("expected_kind"), d.update(expected="네.")))
neg("백업 실패인데 error 없음(3.7.0)", "BackupJobResult", "BackupJobResult", lambda d: (d.update(status="failed", snapshot_id=None, bytes=0), d.pop("error", None)))
neg("백업 오류 코드가 BoundaryError 밖(INTERNAL, 3.7.0)", "BackupJobResult", "BackupJobResult", lambda d: d.update(status="failed", snapshot_id=None, bytes=0, error={"code": "INTERNAL", "message": "x", "retryable": False}))
for _bad in ("https://:", "https://[]", "https://host:bad", "https://host:99999", "http://host", "https://host?x=1"):
    neg(f"HttpClientSettings base_url 거부: {_bad}", "_common#/$defs/HttpClientSettings", "GateJobConfig", lambda d, b=_bad: (d.clear(), d.update(kind="http", base_url=b, token_secret="T")))
neg("HttpClientSettings token_secret 끝 개행", "_common#/$defs/HttpClientSettings", "GateJobConfig", lambda d: (d.clear(), d.update(kind="http", base_url="https://release-gate", token_secret="TOKEN\n")))
neg("CommonEnv 접두사 오타 OPENIT_EGRESS_PR0XY(3.7.0)", "CommonEnv", "CommonEnv", lambda d: d.update(OPENIT_EGRESS_PR0XY="x"))
neg("AdminConsoleEnv 접두사 오타 ADMIN_H0ST(3.7.0)", "AdminConsoleEnv", "AdminConsoleEnv", lambda d: d.update(ADMIN_H0ST="x"))
neg("DATASET_STORE_PORT 99999(3.7.0)", "DatasetStoreEnv", "DatasetStoreEnv", lambda d: d.update(DATASET_STORE_PORT="99999"))
neg("백업 오류 UNAVAILABLE 인데 retryable false(3.7.0)", "BackupJobResult", "BackupJobResult", lambda d: d.update(status="failed", snapshot_id=None, bytes=0, error={"code": "UNAVAILABLE", "message": "x", "retryable": False}))
neg("검수 거부인데 reason 없음(3.7.0)", "AuthoringRequests#/$defs/AddReviewRequest", "AuthoringRequests.AddReviewRequest", lambda d: (d.update(decision="REJECTED", clinical_basis_approved=False), d.pop("reason", None)))
for _bad in ("https://:", "https://host:bad", "https://host:99999", "https://identity.example/sub"):
    neg(f"IDENTITY_PUBLIC_URL 거부(HttpsOrigin): {_bad}", "IdentityEnv", "IdentityEnv", lambda d, b=_bad: d.update(IDENTITY_PUBLIC_URL=b))
for _bad in ("http://release-gate:8080", "https://release-gate/v1", "https://release-gate?x=1"):
    neg(f"서비스 주소 거부(ServiceUrl, R1.1): {_bad}", "SurveyServiceEnv", "SurveyServiceEnv", lambda d, b=_bad: d.update(SURVEY_RELEASE_READER_URL=b))
neg("PASS 인데 HUMAN_APPROVAL 검사 없음(3.7.0)", "GateDecision", "GateDecision.pass", lambda d: d.update(checks=[c for c in d["checks"] if c["kind"] != "HUMAN_APPROVAL"]))
neg("PASS 인데 CONTRACT_COMPAT 만(3.7.0)", "GateDecision", "GateDecision.pass", lambda d: d.update(checks=[{"kind": "CONTRACT_COMPAT", "result": "PASS"}]))
neg("PASS 인데 approval_id 없음(3.7.0)", "GateDecision", "GateDecision.pass", lambda d: d.pop("approval_id", None))
neg("시험용 memory 저장소는 설정에서 거부(4.0.0)", "SyntheticDefs#/$defs/Store", "SyntheticDefs.Store.file", lambda d: (d.clear(), d.update(kind="memory")))
neg("prune dry-run 인데 freed_bytes 값(4.0.0)", "GateJobResult", "GateJobResult.prune-dry-run", lambda d: (d.clear(), d.update(job="prune", status="ok", applied=False, bundle_release_ids=[], submission_ids=[], freed_bytes=-1, attempts_purged=None)))
neg("affected_slots 점 없는 값(4.0.0 SlotRefString)", "ChangeClassification", "ChangeClassification", lambda d: d.update(affected_slots=["Q1"]))
neg("KioskFrontendEnv 접두사 오타 KIOSK_HSOT(4.0.0)", "KioskFrontendEnv", "KioskFrontendEnv", lambda d: d.update(KIOSK_HSOT="127.0.0.1"))
import json as _json
_rules = _json.load(open(here + "/boundary_contracts/data/action_extraction_rules.json"))
for _label, _mut in (("모르는 action NOPE 로 규칙을 비움", lambda r: r["next_item"]["by_action"].__setitem__(0, {"actions": ["NOPE"], "next_item_is": "flow_next", "base_item": "last_in_flow_order_among_values_and_targets"})),
                     ("NEXT 가 규칙 두 개에 걸림", lambda r: r["next_item"]["by_action"][0]["actions"].append("NEXT")),
                     ("flow_next 규칙에 base_item 없음", lambda r: r["next_item"]["by_action"][2].pop("base_item"))):
    _r = copy.deepcopy(_rules); _mut(_r)
    _rej = bool(list(val("ActionExtractionRules").iter_errors(_r))); print("OK  " if _rej else "FAIL", "거부되어야 함(4.0.0):", _label); bad += not _rej
neg("서비스 주소 호스트 254자(RFC 1035, 4.0.0)", "SurveyServiceEnv", "SurveyServiceEnv", lambda d: d.update(SURVEY_RELEASE_READER_URL="https://" + ".".join(["a" * 63] * 4)))
neg("failure_type 끝 개행", "FailureCase", "FailureCase", lambda d: d.update(failure_type="UNCLASSIFIED\n"))
neg("failure_type 에 공백(3.7.0 FailureType)", "FailureCase", "FailureCase", lambda d: d.update(failure_type="a b"))
neg("CaseReviewRequest LORA_A 인데 expected 가 ActionExtraction 이 아님(3.7.0)", "CaseReviewRequest", "CaseReviewRequest.confirmed-lora-a", lambda d: d.update(expected={"x": 1}))
neg("푸시 구독 본문의 expirationTime(닫힌 본문, 3.7.0 하나로 합침)", "PublicApiRequests#/$defs/PushSubscribeBody", "PushSubscriptionRequest", lambda d: d.update(expirationTime=None))
neg("푸시 endpoint 가 .internal 호스트(3.7.0 하나로 합침)", "PushSubscriptionRequest", "PushSubscriptionRequest", lambda d: d.update(endpoint="https://push.corp.internal/x"))
d = ex("ModelPackageManifest"); d["base_model"]["id"] = "org/name-with.slash_1"
errs = [e.message for e in val("ModelPackageManifest").iter_errors(d)]; print("OK  " if not errs else "FAIL", "슬래시가 든 기반 모델 이름 허용", errs); bad += bool(errs)
neg("빈 기반 모델 이름", "ModelPackageManifest", "ModelPackageManifest", lambda d: d["base_model"].update(id=""))
d = ex("ModelPackageManifest"); d["base_model"]["id"] = "base-model"
errs = [e.message for e in val("ModelPackageManifest").iter_errors(d)]; print("OK  " if not errs else "FAIL", "Id 형식 기반 모델 이름도 유효", errs); bad += bool(errs)
neg("모델 패키지에 시스템 프롬프트 없음", "ModelPackageManifest", "ModelPackageManifest", lambda d: d.pop("system_prompt"))
neg("프롬프트 경로가 상위 디렉터리", "ModelPackageManifest", "ModelPackageManifest", lambda d: d["system_prompt"].update(path="../p.txt"))
neg("프롬프트 경로가 절대 경로", "ModelPackageManifest", "ModelPackageManifest", lambda d: d["system_prompt"].update(path="/etc/p.txt"))
neg("프롬프트 해시 형식 위반", "ModelPackageManifest", "ModelPackageManifest", lambda d: d["system_prompt"].update(sha256="abc"))
neg("반려 승인에 사유 없음", "GateApproval", "GateApproval", lambda d: d.update(decision="REJECT"))
neg("측정값에 표본 수 없음", "EvaluationReport", "EvaluationReport", lambda d: d["metrics"][0].pop("n"))
neg("평가 보고서에 임계치 키(스키마가 모르는 필드)는 쓰기에서 거부", "EvaluationReport", "EvaluationReport", lambda d: d["metrics"][0].update(threshold=0.9))
neg("v1 역할 PARSER(DatasetManifest)", "DatasetManifest", "DatasetManifest", lambda d: d["files"][0].update(role="PARSER"))
neg("v1 expected_kind GENERATOR(FailureCase)", "FailureCase", "FailureCase", lambda d: d.update(expected_kind="GENERATOR"))
neg("재알림에 turn_id 없음", "StaffCallRetryRequest", "StaffCallRetryRequest", lambda d: d.pop("turn_id"))
neg("재알림에 자유 문장 필드", "StaffCallRetryRequest", "StaffCallRetryRequest", lambda d: d.update(note="x"))
neg("실패 기록의 outcome 값 위반", "StaffCallReport", "StaffCallReport", lambda d: d.update(outcome="MAYBE"))
neg("재알림 응답에 retry_after_s 없음", "StaffCallRetryResult", "StaffCallRetryResult", lambda d: d.pop("retry_after_s"))
neg("StaffAlertPage 항목의 새 필드도 열거를 지킨다", "StaffAlertPage", "StaffAlertPage", lambda d: d["items"][1].update(manual_notice_outcome="MAYBE"))
neg("StaffAlertPage 항목의 모르는 필드는 쓰기에서 거부", "StaffAlertPage", "StaffAlertPage", lambda d: d["items"][0].update(extra=1))
neg("StaffAlert 전달 횟수가 음수", "StaffAlert", "StaffAlert", lambda d: d.update(delivery_attempts=-1))
# v2 모델 입출력(ActionExtraction 계열, ResponseRequest, ResponseText)이 위반을 거부하는지. 같은 검사를 tests/test_v2_schemas.py가 한 번 더 한다.
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, "tools")); from negatives_v2 import CASES as _V2
for label, schema, base_ex, mutate in _V2:
    neg(label, schema, base_ex, mutate)
v = val("ResponseText"); r = bool(list(v.iter_errors({"response_text": "x"}))); print("OK  " if r else "FAIL", "거부되어야 함: 응답이 JSON 객체"); bad += (not r)
removed = [n for n in ("ParserSample", "GeneratorSample") if os.path.exists(f"{here}/schemas/{n}.schema.json")]
print("OK  " if not removed else "FAIL", "v1 스키마 ParserSample/GeneratorSample는 없다", removed); bad += bool(removed)
# 5.0.0: 같은 이름(_id) 다른 정의 점검(D117). 허용 목록과 근거는 tools/id_defs_allowlist.json
_r = subprocess.run([sys.executable, here + "/tools/check_id_defs.py"])
print("OK  " if _r.returncode == 0 else "FAIL", "같은 이름의 ID 칸은 한 정의를 참조한다(tools/check_id_defs.py)"); bad += _r.returncode != 0
sys.exit(1 if bad else 0)
