#!/usr/bin/env python3
"""비식별 뷰 스키마 생성기(3.7.0): 문진 스키마 TurnTrace(판 1)와 공개 규칙(boundary_contracts/data/deid_rules.json)에서
OpsFeedbackDeidentifiedTrace·OpsFeedbackReviewTrace 를 만든다. 사용: gen_deid_view.py [--check]

왜 생성기인가: 비식별 뷰는 TurnTrace 의 모든 위치에 대해 '비식별기가 낼 수 있는 값'을 정해야 한다. 손으로 쓰면 TurnTrace 를 복사하게 되고
(문진 스키마는 survey-service 소유, 사본 금지) 안쪽을 object 로만 두면 자유 문장이 통과한다(2026-11-07 Codex 반례). 생성물은 저장본과 같아야 한다(--check, 시험).

출력 집합 = 계약이 허용하는 모든 정책(OpsFeedbackJobConfig.deid)으로 비식별기가 낼 수 있는 값을 위치마다 독립으로 모은 안전한 상위 집합이다(가지 선택·정책 사이 상관관계는 반영하지 않으므로 정확한 합집합이라고 부르지 않는다). 비식별기의 걷기 순서를 그대로 옮긴다:
 1) $ref 를 따라간 위치: 정책 mask_defs/drop_defs 로 통째 [MASKED]/[DROPPED] 가 될 수 있다(최상위·가명 키 제외). 키 마스킹·자유 문자열은 [MASKED] 만.
 2) oneOf/anyOf: 가지 하나를 골라 그 가지로 걷는다 → 가지별 결과의 anyOf. (비식별기의 가지 선택은 첫 일치이며, 입력은 TraceEnvelope 가 TurnTrace 로 검증한다)
 3) const/enum: 값 그대로(키 마스킹이 적용되지 않는다).
 4) 키가 있는 위치(최상위 아님): 정책 mask_value_keys 로 [MASKED] 가 될 수 있다.
 5) 값별: null 그대로 / 문자열: session_id·turn_id 는 의사 식별자만, keep 키는 그 패턴 또는 [MASKED], 그 밖은 [MASKED]만 /
    bool 그대로 / 숫자: 그대로 또는 null(mask_number_keys) / 배열: items 없으면 [], 있으면 원소마다(제거는 [MASKED]) /
    객체: properties 없으면 {}(건수 맵 조건이면 건수 맵도), 있으면 그 키만(모르는 키 제거), required 는 원본과 같다(입력은 TurnTrace 로 먼저 검증되므로 알려진 키는 지워지지 않는다).
 후처리: pause_reason 네 경로, 검토 사본의 원문 두 경로(규칙 파일). 비식별기는 마지막에 출력이 이 스키마를 지키는지 검사하고 어기면 사례를 만들지 않는다(fail-closed).
 원본의 allOf·if·not·pattern 등은 비식별기가 보지 않으므로 생성기도 보지 않는다.
"""
import copy
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCH = ROOT / "boundary_contracts/schemas"
RULES = json.loads((ROOT / "boundary_contracts/data/deid_rules.json").read_text(encoding="utf-8"))
SURVEY_VERSION = 1

R = {"$ref": "#/$defs/Redacted"}      # 정의 마스킹(mask_defs [MASKED] / drop_defs [DROPPED])
M = {"$ref": "#/$defs/Masked"}        # 키 마스킹·자유 문자열·패턴 불일치: [MASKED] 만
P = {"$ref": "#/$defs/Pseudonym"}


def anyof(alts):
    out, seen = [], set()
    for a in alts:
        k = json.dumps(a, sort_keys=True)
        if k not in seen:
            seen.add(k); out.append(a)
    return out[0] if len(out) == 1 else {"anyOf": out}


class Gen:
    def __init__(self, survey, review):
        self.defs = survey["$defs"]
        self.review = review
        self.pause = {tuple(p) for p in RULES["pause_reason"]["paths"]}
        self.utter = {tuple(p) for p in RULES["review_utterance"]["paths"]}
        self.ref_names, self.count_keys = set(), set()   # 정책이 고를 수 있는 정의 이름·건수 맵 키(OpsFeedbackJobConfig.deid 의 목록으로 생성)

    def resolve(self, node):
        names = []
        while isinstance(node, dict) and "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            names.append(name); node = self.defs[name]
        return node, names

    def string(self, key):
        if key in RULES["pseudonym"]["keys"]:
            return P
        if key in RULES["keep_patterns"]:
            return anyof([{"type": "string", "pattern": "^(?:" + RULES["keep_patterns"][key] + ")$(?![\\s\\S])"}, M])
        return M

    def count_map(self, node):
        ap = node.get("additionalProperties")
        if not isinstance(ap, dict):
            return False
        ap, _ = self.resolve(ap)
        return ap.get("type") == "integer"

    def t(self, node, key, path, root=False):
        node, names = self.resolve(node)
        if not root:
            self.ref_names.update(names)
        alts = []
        ident = key in RULES["pseudonym"]["keys"]   # 가명 키는 정책이 mask_defs·mask_value_keys 로 가릴 수 없다(OpsFeedbackJobConfig.deid 가 막는다)
        if names and not root and not ident:
            alts.append(R)                                   # 1) mask_defs/drop_defs
        for comb in ("oneOf", "anyOf"):
            if comb in node:                                 # 2) 가지
                return anyof(alts + [self.t(b, key, path) for b in node[comb]])
        if "const" in node:
            return anyof(alts + [{"const": node["const"]}])  # 3)
        if "enum" in node:
            return anyof(alts + [{"enum": node["enum"]}])
        if key and not root and not ident:
            alts.append(M)                                   # 4) mask_value_keys([MASKED] 만)
        types = node.get("type")
        types = [types] if isinstance(types, str) else (types or ["null", "boolean", "number", "string", "array", "object"])   # type 없는 노드는 일반 의미대로 모든 타입(Codex)
        for ty in types:
            if ty == "null":
                alts.append({"type": "null"})
            elif ty == "boolean":
                alts.append({"type": "boolean"})
            elif ty in ("integer", "number"):
                alts.append({"type": ty}); alts.append({"type": "null"})   # mask_number_keys
            elif ty == "string":
                alts.append(self.string(key))
            elif ty == "array":
                items = node.get("items") if isinstance(node.get("items"), dict) else None
                alts.append({"type": "array", "maxItems": 0} if items is None else {"type": "array", "items": self.t(items, key, path + ("[]",))})   # 원소 제거(_DROP→MASK)는 유효 입력에서 생기지 않는다
            elif ty == "object":
                props = node.get("properties")
                if not props:
                    alts.append({"type": "object", "maxProperties": 0})
                    if self.count_map(node) and key:
                        self.count_keys.add(key)
                        alts.append({"$ref": "#/$defs/CountMap"})
                else:
                    out = {}
                    for k, v in props.items():
                        sub = path + (k,)
                        if self.review and sub in self.utter:
                            out[k] = anyof([self.t(v, k, sub), {"type": "string", "minLength": 1, "maxLength": RULES["review_utterance"]["max_chars"]}])
                        elif k == "pause_reason" and path in self.pause:
                            continue                                  # 네 경로는 후처리가 정한다(아래). 그 밖의 위치는 일반 걷기(Codex: PauseEntry.pause_reason 보존)
                        else:
                            out[k] = self.t(v, k, sub)
                    if path in self.pause:
                        out["pause_reason"] = {"enum": RULES["pause_reason"]["values"]}
                    o = {"type": "object", "additionalProperties": False, "properties": out}
                    req = [r for r in node.get("required", []) if r in out and not (r == "pause_reason" and path in self.pause)]
                    if req:
                        o["required"] = req   # 유효 입력(TraceEnvelope→TurnTrace)에서 알려진 키는 지워지지 않는다(값이 토큰·null 로 바뀔 뿐). 어기면 비식별기가 사례를 만들지 않는다
                    alts.append(o)
        return anyof(alts)


def hoist(schema, defs):
    """같은 부분 스키마가 여러 번 나오면 $defs 로 올린다(읽기 쉽게, 의미는 같다)."""
    counts = {}

    def count(x, schema=True):
        if isinstance(x, dict):
            k = json.dumps(x, sort_keys=True)
            if schema and len(k) > 200:
                counts[k] = counts.get(k, 0) + 1
            for kk, v in x.items():
                if kk == "properties":
                    for pv in v.values(): count(pv)      # 속성 이름 맵 자체는 스키마가 아니다
                else:
                    count(v)
        elif isinstance(x, list):
            for v in x: count(v)
    count(schema)
    names = {}
    for k, n in sorted(counts.items(), key=lambda t: (-len(t[0]), t[0])):
        if n > 1:
            names[k] = "G" + hashlib.sha256(k.encode()).hexdigest()[:10]

    def rep(x, top=False):
        if isinstance(x, dict):
            k = json.dumps(x, sort_keys=True)
            if not top and k in names:
                if names[k] not in defs:
                    defs[names[k]] = None
                    defs[names[k]] = rep(json.loads(k), top=True)
                return {"$ref": "#/$defs/" + names[k]}
            return {kk: ({pk: rep(pv) for pk, pv in v.items()} if kk == "properties" else rep(v)) for kk, v in x.items()}
        if isinstance(x, list):
            return [rep(v) for v in x]
        return x
    return rep(schema, top=True)


LAST = {}


def config_fragment(text):
    """OpsFeedbackJobConfig 의 생성 부분: 정책이 고를 수 있는 정의 이름(mask_defs·drop_defs)과 건수 맵 키(keep_count_map_keys). 원본에서 도출한다."""
    import collections
    d = json.loads(text, object_pairs_hook=collections.OrderedDict)
    names = sorted(LAST["ref_names"] - set(RULES["pseudonym"].get("defs", ["SessionId"])))
    d["$defs"]["DeidDefName"] = {"enum": names, "description": f"문진 스키마 TurnTrace v{SURVEY_VERSION} 에서 $ref 로 도달하는 정의 이름(가명 키의 SessionId 제외). 생성: tools/gen_deid_view.py"}
    d["$defs"]["DeidCountMapKey"] = {"enum": sorted(LAST["count_keys"]), "description": "건수 맵으로 남길 수 있는 키(properties 없고 additionalProperties 가 integer 인 위치의 키). 생성: tools/gen_deid_view.py"}
    deid = d["$defs"]["Deid"]["properties"]
    for k in ("mask_defs", "drop_defs"):
        deid[k] = {"type": "array", "uniqueItems": True, "items": {"$ref": "#/$defs/DeidDefName"}, "description": "문진 스키마 TurnTrace 의 정의 이름. 그 정의를 거친 위치를 통째로 " + ("[MASKED]" if k == "mask_defs" else "[DROPPED]") + " 로 바꾼다"}
    deid["keep_count_map_keys"] = {"type": "array", "uniqueItems": True, "items": {"$ref": "#/$defs/DeidCountMapKey"}}
    return json.dumps(d, ensure_ascii=False, indent=1) + "\n"


def build(name, review):
    import survey_schema
    survey = survey_schema.load_schema("TurnTrace", SURVEY_VERSION)
    current = json.loads((SCH / f"{name}.schema.json").read_text(encoding="utf-8"))
    gen = Gen(survey, review)
    body = gen.t({"$ref": "#/$defs/TurnTrace"}, "", (), root=True)
    LAST.update(ref_names=gen.ref_names, count_keys=gen.count_keys)
    defs = {}
    body = hoist(body, defs)
    tok = RULES["tokens"]
    fixed = {
        "Redacted": {"enum": [tok["masked"], tok["dropped"]], "description": "정의 마스킹 결과(mask_defs [MASKED], drop_defs [DROPPED]). 소비자는 내용으로 쓰지 않는다"},
        "Masked": {"const": tok["masked"], "description": "자유 문자열·키 마스킹·keep 패턴 불일치의 결과. 소비자는 내용으로 쓰지 않는다"},
        "Pseudonym": {"type": "string", "pattern": "^" + RULES["pseudonym"]["pattern"] + "$(?![\\s\\S])", "description": "의사 식별자(session_id·turn_id, 어디에 나오든)"},
        "CountMap": {"type": "object", "propertyNames": {"pattern": "^" + RULES["count_map"]["key_pattern"] + "$(?![\\s\\S])"}, "additionalProperties": {"type": "integer", "minimum": 0}},
    }
    out = {k: current[k] for k in ("$schema", "$id", "title", "description", "x-producers", "x-consumers") if k in current}
    out["x-generated"] = {"by": "tools/gen_deid_view.py", "from": f"openit-survey-schema TurnTrace v{SURVEY_VERSION}", "rules": "boundary_contracts/data/deid_rules.json"}
    out.update(body)
    out["$defs"] = {**fixed, **dict(sorted(defs.items()))}
    return out


def main(argv):
    check = "--check" in argv
    bad = 0
    for name, review in (("OpsFeedbackDeidentifiedTrace", False), ("OpsFeedbackReviewTrace", True)):
        new = json.dumps(build(name, review), ensure_ascii=False, indent=1) + "\n"
        path = SCH / f"{name}.schema.json"
        if check:
            same = path.read_text(encoding="utf-8") == new
            print(("OK  " if same else "FAIL") + f" {name} 는 생성물과 같다")
            bad += not same
        else:
            path.write_text(new, encoding="utf-8")
            print(f"wrote {name} ({len(new)} bytes)")
    cfg = SCH / "OpsFeedbackJobConfig.schema.json"
    new = config_fragment(cfg.read_text(encoding="utf-8"))
    if check:
        same = cfg.read_text(encoding="utf-8") == new
        print(("OK  " if same else "FAIL") + " OpsFeedbackJobConfig 의 비식별 목록은 생성물과 같다"); bad += not same
    else:
        cfg.write_text(new, encoding="utf-8"); print("wrote OpsFeedbackJobConfig 비식별 목록")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
