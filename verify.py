#!/usr/bin/env python3
"""schemas/ 의 모든 스키마가 Draft 2020-12 로 유효하고, 모든 examples/ 가 대응 스키마를 통과하며, 위반 예시가 거부되는지 검사한다."""
import copy, glob, json, os, sys, jsonschema
here = os.path.dirname(os.path.abspath(__file__)); base = "file://" + here + "/schemas/"
common = json.load(open(here + "/schemas/_common.schema.json"))
def val(name):
    s = json.load(open(f"{here}/schemas/{name}.schema.json")); jsonschema.Draft202012Validator.check_schema(s)
    return jsonschema.Draft202012Validator(s, resolver=jsonschema.RefResolver(base, s, store={base + "_common.schema.json": common, base + "ActivePointer.schema.json": json.load(open(here + "/schemas/ActivePointer.schema.json"))}))
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
neg("알 수 없는 오류 코드", "BoundaryError", "BoundaryError", lambda d: d.update(code="WHATEVER"))
neg("적용된 롤백에 포인터 없음", "RollbackReceipt", "RollbackReceipt", lambda d: d.pop("active_pointer"))
neg("거부된 롤백에 사유 없음", "RollbackReceipt", "RollbackReceipt", lambda d: (d.update(status="REJECTED"), d.pop("active_pointer")))
neg("포인터 버전 0", "ActivePointer", "ActivePointer", lambda d: d.update(pointer_version=0))
# 확장 필드는 허용되어야 한다
d = ex("ReleaseManifest"); d["ext"] = {"model-lab": {"note": "x"}}
errs = list(val("ReleaseManifest").iter_errors(d)); print("OK  " if not errs else "FAIL", "ext 허용"); bad += bool(errs)
# 문진 스키마가 같은 워크스페이스에 있으면 TraceEnvelope.trace를 TurnTrace로 검증한다.
survey = os.path.join(here, "..", "survey-service", "schema", "schemas", "TurnTrace.json")
if os.path.exists(survey):
    _tt = json.load(open(survey)); _tt.pop("$id", None)  # 상대 $id는 참조 해석을 깨뜨린다
    tt = jsonschema.Draft202012Validator(_tt)
    errs = [e.message for e in tt.iter_errors(ex("TraceEnvelope")["trace"])]
    print("OK  " if not errs else "FAIL", "TraceEnvelope.trace는 TurnTrace를 통과", errs[:2]); bad += bool(errs)
else:
    print("건너뜀: 문진 스키마가 없어 TraceEnvelope.trace를 TurnTrace로 검증하지 않음")
d = ex("FailureCase"); d.pop("question_set", None); d.pop("expected_kind"); d["expected"] = {}
errs = [e.message for e in val("FailureCase").iter_errors(d)]; print("OK  " if not errs else "FAIL", "expected_kind 없는 FailureCase도 유효(권장일 뿐)", errs); bad += bool(errs)
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
neg("StaffAlert 전달 횟수가 음수", "StaffAlert", "StaffAlert", lambda d: d.update(delivery_attempts=-1))
# v2 모델 입출력(ActionExtraction 계열, ResponseRequest, ResponseText)이 위반을 거부하는지. 같은 검사를 tests/test_v2_schemas.py가 한 번 더 한다.
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, "tools")); from negatives_v2 import CASES as _V2
for label, schema, base_ex, mutate in _V2:
    neg(label, schema, base_ex, mutate)
v = val("ResponseText"); r = bool(list(v.iter_errors({"response_text": "x"}))); print("OK  " if r else "FAIL", "거부되어야 함: 응답이 JSON 객체"); bad += (not r)
removed = [n for n in ("ParserSample", "GeneratorSample") if os.path.exists(f"{here}/schemas/{n}.schema.json")]
print("OK  " if not removed else "FAIL", "v1 스키마 ParserSample/GeneratorSample는 없다", removed); bad += bool(removed)
sys.exit(1 if bad else 0)
