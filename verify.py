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
neg("실패 사례 출처 시드에 seed_case_id 없음", "GeneratorSample", "GeneratorSample", lambda d: d.pop("seed_case_id"))
neg("시나리오 분리 미확인 데이터셋", "DatasetManifest", "DatasetManifest", lambda d: d.update(scenario_disjoint_across_splits=False))
neg("비식별 안 된 실패 사례", "FailureCase", "FailureCase", lambda d: d.update(deidentified=False))
neg("근거 없는 롤백 요청", "RollbackRequest", "RollbackRequest", lambda d: d.update(evidence_refs=[]))
neg("모델 패키지에 알 수 없는 상태 필드", "ModelPackageManifest", "ModelPackageManifest", lambda d: d.update(status="APPROVED"))
neg("알 수 없는 오류 코드", "BoundaryError", "BoundaryError", lambda d: d.update(code="WHATEVER"))
neg("적용된 롤백에 포인터 없음", "RollbackReceipt", "RollbackReceipt", lambda d: d.pop("active_pointer"))
neg("거부된 롤백에 사유 없음", "RollbackReceipt", "RollbackReceipt", lambda d: (d.update(status="REJECTED"), d.pop("active_pointer")))
neg("포인터 버전 0", "ActivePointer", "ActivePointer", lambda d: d.update(pointer_version=0))
# 확장 필드는 허용되어야 한다
d = ex("ReleaseManifest"); d["ext"] = {"model-lab": {"note": "x"}}
errs = list(val("ReleaseManifest").iter_errors(d)); print("OK  " if not errs else "FAIL", "ext 허용"); bad += bool(errs)
sys.exit(1 if bad else 0)
