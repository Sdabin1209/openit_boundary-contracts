#!/usr/bin/env python3
"""같은 이름 다른 정의 점검(계약 5.0.0, D117 '같은 뜻의 타입은 한 번만'). 사용: check_id_defs.py [--root DIR] [--json]

무엇을 보나: schemas/*.json 과 openapi/*.json 의 모든 properties·쿼리/경로 매개변수 중 이름이 `_id` 로 끝나는 칸.
같은 이름의 칸은 모두 같은 '정의 끝점'에 닿아야 한다. 끝점은 순수 별칭($ref 와 주석 키만 가진 노드)을 따라가 처음 만나는
비별칭 노드의 위치다(예: _common.schema.json#/$defs/SessionId). 별칭 없이 그 자리에 모양을 쓴 칸(인라인)은 그 자체가 끝점이라,
같은 이름의 다른 칸이 참조와 인라인으로 갈리면 위반이다(2026-11-08 결함 #22: session_id 6종, turn_id 64 대 128).
null 허용(anyOf [{type:null}, X])은 X 의 끝점으로 본다. $ref 옆에 단언 키를 더 둔 칸(좁히기)은 허용 목록에 근거가 있어야 한다.

보지 않는 것(이유는 허용 목록 파일 tools/id_defs_allowlist.json 에 있다): 조건부 하위 스키마(if·then·else·not·contains·dependentSchemas
안의 칸은 기본 정의를 좁히거나 판별할 뿐 타입을 정의하지 않는다), 생성물 파일, 뜻이 위치마다 다른 이름(id).
종료 코드: 0 위반 없음, 1 위반 있음, 2 사용 오류.
"""
from __future__ import annotations

import json
import pathlib
import sys

ANNOT = {"description", "$comment", "title", "default", "examples", "deprecated", "readOnly", "writeOnly", "x-default-content-type"}
COND = {"if", "then", "else", "not", "contains", "dependentSchemas", "propertyNames"}


def _ptr_get(doc, ptr):
    cur = doc
    for raw in [p for p in ptr.split("/") if p != ""]:
        key = raw.replace("~1", "/").replace("~0", "~")
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur


class Repo:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.docs: dict[str, object] = {}

    def doc(self, rel: str):
        if rel not in self.docs:
            self.docs[rel] = json.loads((self.root / rel).read_text(encoding="utf-8"))
        return self.docs[rel]

    def resolve(self, base_rel: str, ref: str):
        target, _, frag = ref.partition("#")
        rel = base_rel if not target else str((pathlib.PurePosixPath(base_rel).parent / target))
        parts = []
        for p in rel.split("/"):
            if p == "..":
                parts.pop()
            elif p not in ("", "."):
                parts.append(p)
        rel = "/".join(parts)
        if rel.startswith("boundary_contracts/"):
            rel = rel[len("boundary_contracts/"):]
        return rel, frag or "", _ptr_get(self.doc(rel), frag or "")

    def endpoint(self, rel: str, ptr: str, node, depth=0):
        """(끝점 문자열, 좁히기 여부)"""
        if depth > 32:
            raise ValueError(f"$ref 순환: {rel}#{ptr}")
        if isinstance(node, dict):
            any_of = node.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2 and {"type": "null"} in any_of and set(node) - ANNOT == {"anyOf"}:
                other = [a for a in any_of if a != {"type": "null"}][0]
                return self.endpoint(rel, ptr + "/anyOf", other, depth + 1)
            if "$ref" in node:
                extra = set(node) - ANNOT - {"$ref"}
                trel, tptr, tnode = self.resolve(rel, node["$ref"])
                end, _ = self.endpoint(trel, tptr, tnode, depth + 1)
                if extra:
                    if "/$defs/" in "/" + ptr and "/properties/" not in ptr.split("/$defs/")[-1]:
                        return f"{rel}#{ptr}", False   # $defs 의 이름 있는 타입이 다른 타입을 좁힌 것(예: SessionId = Id + 64자)은 그 자체가 새 타입이다
                    return end, True
                return end, False
            if "/$defs/" in "/" + ptr and "/properties/" not in ptr.split("/$defs/")[-1]:
                return f"{rel}#{ptr}", False
        shape = {k: v for k, v in node.items() if k not in ANNOT} if isinstance(node, dict) else node
        return "inline:" + json.dumps(shape, sort_keys=True, ensure_ascii=False), False


def _walk(o, ptr, out, rel):
    if isinstance(o, dict):
        props = o.get("properties")
        if isinstance(props, dict):
            for name, d in props.items():
                out.append((name, rel, f"{ptr}/properties/{name}", d))
        if {"name", "in", "schema"} <= set(o) and isinstance(o.get("name"), str):
            out.append((o["name"], rel, f"{ptr}/schema", o["schema"]))
        for k, v in o.items():
            _walk(v, f"{ptr}/{k.replace('~', '~0').replace('/', '~1')}", out, rel)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, f"{ptr}/{i}", out, rel)


def check(root: pathlib.Path, allow: dict) -> list[str]:
    repo = Repo(root)
    gen = {g["file"] for g in allow.get("generated_files", [])}
    names_ex = {n["name"] for n in allow.get("excluded_names", [])}
    loc_ok = {(l["file"], l["pointer"]) for l in allow.get("refinements", [])}
    fields = []
    for sub in ("schemas", "openapi"):
        for p in sorted((root / sub).glob("*.json")):
            rel = f"{sub}/{p.name}"
            if rel in gen:
                continue
            _walk(repo.doc(rel), "", fields, rel)
    problems, by_name, seen_refine = [], {}, set()
    for name, rel, ptr, node in fields:
        if not name.endswith("_id") or name in names_ex:
            continue
        if any(seg in COND for seg in ptr.split("/")):
            continue
        end, refined = repo.endpoint(rel, ptr, node)
        if refined:
            seen_refine.add((rel, ptr))
            if (rel, ptr) not in loc_ok:
                problems.append(f"{rel}#{ptr}: {name} 가 참조 옆에 단언을 더했다(좁히기). 근거를 허용 목록 refinements 에 적거나 공통 타입으로 올린다")
        by_name.setdefault(name, {}).setdefault(end, []).append(f"{rel}#{ptr}")
    for name, ends in sorted(by_name.items()):
        if len(ends) > 1:
            detail = "; ".join(f"{e[:90]} <- {locs[0]}" + (f" 외 {len(locs) - 1}곳" if len(locs) > 1 else "") for e, locs in ends.items())
            problems.append(f"{name}: 정의 {len(ends)}종 — {detail}")
    for l in allow.get("refinements", []):
        if (l["file"], l["pointer"]) not in seen_refine:
            problems.append(f"허용 목록의 낡은 항목(그 자리에 좁히기가 없다): {l['file']}#{l['pointer']}")
    return problems


def main(argv):
    root = pathlib.Path(__file__).resolve().parents[1]
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("--root 에는 디렉터리가 필요하다", file=sys.stderr); return 2
        root = pathlib.Path(argv[i + 1])
    allow_path = root / "tools/id_defs_allowlist.json"
    allow = json.loads(allow_path.read_text(encoding="utf-8")) if allow_path.exists() else {}
    for sect in ("generated_files", "excluded_names", "refinements"):
        for item in allow.get(sect, []):
            if not str(item.get("reason", "")).strip():
                print(f"허용 목록 {sect} 항목에 근거(reason)가 없다: {item}", file=sys.stderr); return 1
    probs = check(root, allow)
    for p in probs:
        print("FAIL", p)
    if not probs:
        print("OK   같은 이름(_id)의 칸은 모두 같은 정의 끝점에 닿는다")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
