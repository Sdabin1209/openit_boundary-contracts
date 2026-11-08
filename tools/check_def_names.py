#!/usr/bin/env python3
"""같은 이름 다른 타입 정의 점검(계약 5.0.0, D117 '같은 뜻의 타입은 한 번만'). 사용: check_def_names.py [--root DIR]

이름 있는 타입 = schemas/*.json 의 각 `$defs` 항목과 각 최상위 계약 스키마(파일 이름에서 `.schema.json` 을 뺀 이름, `_` 로 시작하는 공통 파일 제외).
같은 이름의 타입이 두 곳 이상에 있으면 모두 같은 정의여야 한다. 정의 비교: 순수 별칭($ref 와 주석·x- 키만)은 대상까지 따라가고,
그 밖은 주석·x- 키를 뺀 모양으로 비교한다. 같은 모양 사본은 이 점검이 막지 않는다(정의가 갈리는 것을 막는다).
뜻이 다른데 이름이 같은 파일 범위 이름은 허용 목록 tools/def_names_allowlist.json 에 이름·파일·근거로 둔다(근거 필수, 쓰이지 않으면 실패).
2026-11-08 결함: ArtifactRef.schema.json 과 _common.$defs.ArtifactRef 가 같은 이름의 두 정의였다.
종료 코드: 0 위반 없음, 1 위반 있음, 2 사용 오류.
"""
from __future__ import annotations

import json
import pathlib
import sys

ANNOT = {"description", "$comment", "title", "default", "examples", "deprecated", "$schema", "$id"}


def _strip(v):
    return {k: x for k, x in v.items() if k not in ANNOT and not k.startswith("x-")} if isinstance(v, dict) else v


def _ptr_get(doc, ptr):
    cur = doc
    for raw in [p for p in ptr.split("/") if p]:
        cur = cur[int(raw)] if isinstance(cur, list) else cur[raw.replace("~1", "/").replace("~0", "~")]
    return cur


def check(root: pathlib.Path, allow: dict) -> list[str]:
    sch = root / "schemas"
    docs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(sch.glob("*.json"))}

    def shape(fname, node, depth=0):
        body = _strip(node)
        if isinstance(body, dict) and set(body) == {"$ref"} and depth < 32:
            target, _, frag = body["$ref"].partition("#")
            tf = target or fname
            if tf in docs:
                return shape(tf, _ptr_get(docs[tf], frag), depth + 1)
        return json.dumps(body, sort_keys=True, ensure_ascii=False)

    names: dict[str, list[tuple[str, str]]] = {}
    for fname, d in docs.items():
        for k, v in (d.get("$defs") or {}).items():
            names.setdefault(k, []).append((f"{fname}#/$defs/{k}", shape(fname, v)))
        if not fname.startswith("_"):
            top = {k: v for k, v in d.items() if k != "$defs"}
            names.setdefault(fname.split(".")[0], []).append((fname, shape(fname, top)))
    ok = {}
    for item in allow.get("same_name_different_meaning", []):
        ok[item["name"]] = set(item["files"])
    problems, used = [], set()
    for name, locs in sorted(names.items()):
        if len({s for _, s in locs}) <= 1:
            continue
        files = {l.split("#")[0] for l, _ in locs}
        if name in ok and files == ok[name]:
            used.add(name)
            continue
        groups: dict[str, list[str]] = {}
        for l, s in locs:
            groups.setdefault(s, []).append(l)
        problems.append(f"{name}: 정의 {len(groups)}종 — " + "; ".join(", ".join(g[:3]) for g in groups.values()))
    for name in ok:
        if name not in used:
            problems.append(f"허용 목록의 낡은 항목: {name}")
    return problems


def main(argv):
    root = pathlib.Path(__file__).resolve().parents[1]
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("--root 에는 디렉터리가 필요하다", file=sys.stderr)
            return 2
        root = pathlib.Path(argv[i + 1])
    ap = root / "tools/def_names_allowlist.json"
    allow = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else {}
    for item in allow.get("same_name_different_meaning", []):
        if not str(item.get("reason", "")).strip():
            print(f"FAIL 허용 목록 항목에 근거(reason)가 없다: {item.get('name')}")
            return 1
    probs = check(root, allow)
    for p in probs:
        print("FAIL", p)
    if not probs:
        print("OK   같은 이름의 타입($defs·최상위 스키마)은 한 정의다")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
