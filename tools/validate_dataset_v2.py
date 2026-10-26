#!/usr/bin/env python3
"""학습 데이터셋 v2(D74) JSONL을 stdin(또는 파일)에서 읽어 새 스키마로 검증한다. 파일을 쓰지 않는다.

  ssh openit 'cat ~/taehyeon/data/dataset_10_14/lora_a_train.jsonl' | python3 tools/validate_dataset_v2.py a
  ssh openit 'cat ~/taehyeon/data/dataset_10_14/lora_b_train.jsonl' | python3 tools/validate_dataset_v2.py b

행은 {human_review, messages[system,user,assistant], scenario_id, split} 형태다(학습 서버 형식).
user -> ActionExtractionInput | ResponseRequest, assistant -> ActionExtraction | ResponseText.
스키마 검증 뒤에 스키마로 표현하지 못하는 의미 검사(targets, next_item, 건너뛰기)를 더한다.
"""
import collections, json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from boundary_contracts.schemas_api import validator

ORDER = ["Q1.D%02d" % i for i in range(1, 12)] + ["Q2.D%02d" % i for i in range(1, 6)] + [
    "Q3", "Q4", "Q4_1", "Q5", "Q5_1", "Q6", "Q6_1", "Q7", "Q7_1", "Q7_2", "Q8_1", "Q8_2", "Q9_1", "Q9_2", "Q10"]
SKIPS = [("Q4.answer", False, "Q4_1"), ("Q5.answer", False, "Q5_1"), ("Q6.answer", False, "Q6_1"),
         ("Q7.does_not_drink", True, "Q7_1"), ("Q7.does_not_drink", True, "Q7_2"),
         ("Q8_1.days", 0, "Q8_2"), ("Q9_1.days", 0, "Q9_2")]


def item_of(key):
    return key.rsplit(".", 1)[0].split("[")[0]


def short(err):
    path = "/".join(str(p) for p in err.absolute_path)
    path = re.sub(r"/\d+", "/*", path)
    return f"{path or '<root>'}: {err.message[:90]}"


def expected_next(out, qid):
    saved = {}
    for v in out["values"]:
        if v["save"]:
            saved[re.sub(r"\[[^\]]*\]", "", v["key"])] = v["value"]
    keys = [v["key"] for v in out["values"]] + out.get("targets", [])
    base = max((item_of(k) for k in keys), key=ORDER.index) if keys else qid  # 한 말에 여러 문항 값이 나오면 가장 뒤 문항 기준
    i = ORDER.index(base) + 1
    while i < len(ORDER):
        skipped = any(ORDER[i] == sk and k in saved and saved[k] == v and isinstance(saved[k], bool) == isinstance(v, bool)
                      for k, v, sk in SKIPS)
        if not skipped:
            return ORDER[i]
        i += 1
    return "END"


def main():
    kind = sys.argv[1]
    files = sys.argv[2:]
    vin = validator("ActionExtractionInput" if kind == "a" else "ResponseRequest")
    vout = validator("ActionExtraction") if kind == "a" else validator("ResponseText")
    total = ok = 0
    fails = collections.Counter()
    sem = collections.Counter()
    info = collections.Counter()
    examples = {}
    streams = [open(f, encoding="utf-8") for f in files] if files else [sys.stdin]
    for st in streams:
        for line in st:
            total += 1
            bad = False
            try:
                r = json.loads(line)
                roles = [m["role"] for m in r["messages"]]
                assert roles == ["system", "user", "assistant"], roles
                u = json.loads(r["messages"][1]["content"])
                a = r["messages"][2]["content"]
                out = json.loads(a) if kind == "a" else a
            except Exception as e:  # 형식 자체가 깨진 행
                fails[("record", repr(e)[:80])] += 1
                continue
            for tag, v, inst in (("input", vin, u), ("output", vout, out)):
                for e in v.iter_errors(inst):
                    fails[(tag, short(e))] += 1
                    examples.setdefault((tag, short(e)), r["scenario_id"])
                    bad = True
            if kind == "a" and not bad:
                keys = {v["key"] for v in out["values"]}
                if not set(out.get("targets", [])) <= keys:
                    sem["targets not in values"] += 1; bad = True
                act = out["action"]
                if act in ("REASK", "REDIRECT") and out["next_item"] != u["question_id"]:
                    sem[f"{act} next_item != question_id"] += 1; bad = True
                if act == "CONFIRM":
                    tg = {item_of(t) for t in out["targets"]}
                    if out["next_item"] not in tg:
                        sem["CONFIRM next_item not target item"] += 1; bad = True
                if act in ("NEXT", "CORRECT", "HOLD", "SKIP"):
                    exp = expected_next(out, u["question_id"])
                    if out["next_item"] != exp:
                        if out["next_item"] in {item_of(k) for k in keys}:
                            # 같은 말에서 이미 일부 칸이 채워진 문항으로 넘어감(예: Q4 예 + Q4_1.status). 알려진 미결(next.text가 받은 내용을 다시 묻는 문제)
                            info["next_item is partially pre-filled in same turn"] += 1
                        else:
                            sem[f"{act} next_item != order/skip rule"] += 1; bad = True
            if kind == "b" and not bad:
                if u["action"] == "START" and u["next"]["question_id"] != "Q1.D01":
                    sem["START not Q1.D01"] += 1; bad = True
            ok += not bad
    print(f"kind={kind} rows={total} pass={ok} fail={total - ok}")
    for (tag, msg), n in fails.most_common(30):
        print(f"  [{tag}] {n:5d}  {msg}   e.g. {examples.get((tag, msg))}")
    for msg, n in sem.most_common():
        print(f"  [semantic] {n:5d}  {msg}")
    for msg, n in info.most_common():
        print(f"  [info, not a failure] {n:5d}  {msg}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
