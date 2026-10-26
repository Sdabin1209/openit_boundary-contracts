"""v2 모델 입출력 스키마가 거부해야 하는 변형 목록. verify.py와 tests/test_v2_schemas.py가 함께 쓴다.

각 항목은 (설명, 스키마 이름, 바탕 예시 이름, 변형 함수)이고, 바탕 예시를 변형하면 스키마가 거부해야 한다.
"""
import copy
import json
import os

_E = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples")


def _ex(name):
    with open(f"{_E}/{name}.json", encoding="utf-8") as f:
        return json.load(f)


A, B = "ActionExtraction", "ResponseRequest"

CASES = [
    ("알 수 없는 action", A, "ActionExtraction.reask", lambda d: d.update(action="START")),
    ("NEXT에 reason", A, "ActionExtraction.next", lambda d: d.update(reason="MISSING")),
    ("REASK에 targets 없음", A, "ActionExtraction.reask", lambda d: d.pop("targets")),
    ("REASK에 CONFIRM 사유", A, "ActionExtraction.reask", lambda d: d.update(reason="CONFLICT_WITH_PREVIOUS")),
    ("MISSING인데 save true", A, "ActionExtraction.reask",
     lambda d: [v.update(save=True) for v in d["values"] if v["status"] == "MISSING"]),
    ("ANSWERED인데 save false", A, "ActionExtraction.reask",
     lambda d: [v.update(save=False) for v in d["values"] if v["status"] == "ANSWERED"]),
    ("키 형식 위반", A, "ActionExtraction.reask", lambda d: d["values"][0].update(key="술.종류")),
    ("next_item 형식 위반", A, "ActionExtraction.reask", lambda d: d.update(next_item="다음")),
    ("OUT_OF_SCHEMA에 note 없음", A, "ActionExtraction.redirect", lambda d: d.pop("note")),
    ("note가 OUT_OF_SCHEMA 밖", A, "ActionExtraction.reask", lambda d: d.update(note="x")),
    ("REDIRECT에 값 있음", A, "ActionExtraction.redirect",
     lambda d: d.update(values=copy.deepcopy(_ex("ActionExtraction.reask")["values"]))),
    ("모르는 필드", A, "ActionExtraction.reask", lambda d: d.update(evidence=[])),
    ("START에 user_utterance", B, "ResponseRequest.start", lambda d: d.update(user_utterance="x")),
    ("END에 text", B, "ResponseRequest.end", lambda d: d["next"].update(text="x")),
    ("CONFIRM의 known이 비어 있지 않음", B, "ResponseRequest.confirm", lambda d: d.update(known="x")),
    ("CONFIRM에 previous 없음", B, "ResponseRequest.confirm", lambda d: d.pop("previous")),
    ("REASK에 SAME 아님", B, "ResponseRequest.reask", lambda d: d["next"].update(type="NEXT")),
    ("HOLD에 hold 없음", B, "ResponseRequest.hold", lambda d: d.pop("hold")),
    ("ask가 NEXT에", B, "ResponseRequest.start", lambda d: d.update(ask="x")),
    ("샘플 seed_case_id 없음(A)", "ActionExtractionSample", "ActionExtractionSample", lambda d: d.update(origin="FAILURE_CASE_SEED")),
    ("샘플 seed_case_id 없음(B)", "ResponseSample", "ResponseSample", lambda d: d.update(origin="FAILURE_CASE_SEED")),
    ("샘플 input이 B 형식", "ActionExtractionSample", "ActionExtractionSample", lambda d: d.update(input=_ex("ResponseRequest.start"))),
]
