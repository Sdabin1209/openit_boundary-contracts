#!/usr/bin/env python3
"""[초안 v2] 새 스키마가 위반을 거부하는지 확인한다(verify.py는 건드리지 않는다)."""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from boundary_contracts.schemas_api import validator
E = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples")
ex = lambda n: json.load(open(f"{E}/{n}.json"))
bad = 0
def neg(label, schema, base, mut):
    global bad
    d = copy.deepcopy(ex(base)); mut(d)
    r = bool(list(validator(schema).iter_errors(d))); bad += not r
    print("OK  " if r else "FAIL", "거부되어야 함:", label)
A, B = "ActionExtraction", "ResponseRequest"
neg("알 수 없는 action", A, "ActionExtraction.reask", lambda d: d.update(action="START"))
neg("NEXT에 reason", A, "ActionExtraction.next", lambda d: d.update(reason="MISSING"))
neg("REASK에 targets 없음", A, "ActionExtraction.reask", lambda d: d.pop("targets"))
neg("REASK에 CONFIRM 사유", A, "ActionExtraction.reask", lambda d: d.update(reason="CONFLICT_WITH_PREVIOUS"))
neg("MISSING인데 save true", A, "ActionExtraction.reask", lambda d: [v.update(save=True) for v in d["values"] if v["status"] == "MISSING"])
neg("ANSWERED인데 save false", A, "ActionExtraction.reask", lambda d: [v.update(save=False) for v in d["values"] if v["status"] == "ANSWERED"])
neg("키 형식 위반", A, "ActionExtraction.reask", lambda d: d["values"][0].update(key="술.종류"))
neg("next_item 형식 위반", A, "ActionExtraction.reask", lambda d: d.update(next_item="다음"))
neg("OUT_OF_SCHEMA에 note 없음", A, "ActionExtraction.redirect", lambda d: d.pop("note"))
neg("note가 OUT_OF_SCHEMA 밖", A, "ActionExtraction.reask", lambda d: d.update(note="x"))
neg("REDIRECT에 값 있음", A, "ActionExtraction.redirect", lambda d: d.update(values=copy.deepcopy(ex("ActionExtraction.reask")["values"])))
neg("모르는 필드", A, "ActionExtraction.reask", lambda d: d.update(evidence=[]))
neg("START에 user_utterance", B, "ResponseRequest.start", lambda d: d.update(user_utterance="x"))
neg("END에 text", B, "ResponseRequest.end", lambda d: d["next"].update(text="x"))
neg("CONFIRM의 known이 비어 있지 않음", B, "ResponseRequest.confirm", lambda d: d.update(known="x"))
neg("CONFIRM에 previous 없음", B, "ResponseRequest.confirm", lambda d: d.pop("previous"))
neg("REASK에 SAME 아님", B, "ResponseRequest.reask", lambda d: d["next"].update(type="NEXT"))
neg("HOLD에 hold 없음", B, "ResponseRequest.hold", lambda d: d.pop("hold"))
neg("ask가 NEXT에", B, "ResponseRequest.start", lambda d: d.update(ask="x"))
v = validator("ResponseText"); r = bool(list(v.iter_errors({"response_text": "x"}))); bad += not r; print("OK  " if r else "FAIL", "거부되어야 함: 응답이 JSON 객체")
neg("샘플 seed_case_id 없음", "ActionExtractionSample", "ActionExtractionSample", lambda d: d.update(origin="FAILURE_CASE_SEED"))
neg("샘플 input이 B 형식", "ActionExtractionSample", "ActionExtractionSample", lambda d: d.update(input=ex("ResponseRequest.start")))
sys.exit(1 if bad else 0)
