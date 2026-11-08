#!/usr/bin/env python3
"""같은 이름 다른 정의 점검(계약 5.0.0, D117 '같은 뜻의 타입은 한 번만'). 사용: check_id_defs.py [--root DIR]

보장 범위(이것만 보장한다): schemas/*.json·openapi/*.json 안에서 이름이 `_id` 로 끝나는 칸(properties 와 쿼리·경로 매개변수)과
이름이 `id` 인 칸. 버전(version)·커서·current_item 처럼 이름이 `_id` 가 아닌 의미상 식별자는 이 점검의 범위 밖이다.

규칙
1. 같은 이름의 `_id` 칸은 모두 같은 '정의'에 닿아야 한다. 정의 = (끝점, 경로 위 좁히기 묶음).
   끝점: 순수 별칭($ref 와 주석 키만)을 따라가 만나는 첫 $defs 이름 타입(그 자체가 $ref 에 단언을 더해 새 타입을 만들어도 이름 있는 타입이다),
   또는 별칭 없이 모양을 쓴 칸(인라인). 경로 중간의 칸이 $ref 옆에 단언을 더하면(좁히기) 그 단언이 정의에 전파된다.
2. 같은 이름의 인라인 정의가 두 곳 이상이면 실패(정의는 한 번, 나머지는 $ref).
3. 좁히기는 허용 목록 refinements 에 위치별 근거가 있어야 한다.
4. 조건부: if·not·contains·propertyNames 안은 판별·부정이라 정의가 아니다(보지 않는다). then·else·dependentSchemas 안은 실제 정의라 본다.
   다만 then/else 의 {"type": "null"} 은 '이 경우 칸이 null' 이라는 좁히기라 정의로 세지 않는다.
5. 생성물(tools/gen_deid_view.py) 안의 칸은 파일·이름·끝점 단위로 허용 목록 generated 에 있어야 하고, 뜻이 달라(의사 식별자·마스킹) 비교에서 뺀다.
6. 이름이 `id` 인 칸은 대상이 위치마다 달라 이름으로 묶지 않는다. 대신 허용 목록 id_registry 에 위치마다 뜻과 끝점을 적고, 점검이 대조한다.
7. 허용 목록 항목은 근거(reason/means)가 필수이고, 쓰이지 않는 항목(낡은 항목)은 실패다.
종료 코드: 0 위반 없음, 1 위반 있음, 2 사용 오류.
"""
from __future__ import annotations

import json
import pathlib
import sys

ANNOT = {"description", "$comment", "title", "default", "examples", "deprecated", "readOnly", "writeOnly", "x-default-content-type"}
SKIP_COND = {"if", "not", "contains", "propertyNames"}
NULL_ONLY = {"type": "null"}


def _ptr_get(doc, ptr):
    cur = doc
    for raw in [p for p in ptr.split("/") if p != ""]:
        key = raw.replace("~1", "/").replace("~0", "~")
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur


def _is_named_def(ptr: str) -> bool:
    if "/$defs/" not in "/" + ptr:
        return False
    tail = ("/" + ptr).split("/$defs/")[-1]
    return "/" not in tail


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
        rel = base_rel if not target else str(pathlib.PurePosixPath(base_rel).parent / target)
        parts: list[str] = []
        for p in rel.split("/"):
            if p == "..":
                parts.pop()
            elif p not in ("", "."):
                parts.append(p)
        rel = "/".join(parts)
        if rel.startswith("boundary_contracts/"):
            rel = rel[len("boundary_contracts/"):]
        return rel, frag or "", _ptr_get(self.doc(rel), frag or "")

    def definition(self, rel: str, ptr: str, node, depth=0):
        """(끝점, 좁히기 묶음(정렬된 문자열 튜플), 인라인 여부)"""
        if depth > 32:
            raise ValueError(f"$ref 순환: {rel}#{ptr}")
        if isinstance(node, dict):
            any_of = node.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2 and NULL_ONLY in any_of and set(node) - ANNOT == {"anyOf"}:
                other = [a for a in any_of if a != NULL_ONLY][0]
                i = any_of.index(other)
                return self.definition(rel, f"{ptr}/anyOf/{i}", other, depth + 1)
            if "$ref" in node:
                extra = {k: node[k] for k in node if k not in ANNOT and k != "$ref"}
                if extra and _is_named_def(ptr):
                    return f"{rel}#{ptr}", (), False
                trel, tptr, tnode = self.resolve(rel, node["$ref"])
                end, refs, _ = self.definition(trel, tptr, tnode, depth + 1)
                mine = (json.dumps(extra, sort_keys=True, ensure_ascii=False),) if extra else ()
                return end, tuple(sorted(set(refs) | set(mine))), False
            if _is_named_def(ptr):
                return f"{rel}#{ptr}", (), False
        shape = {k: v for k, v in node.items() if k not in ANNOT} if isinstance(node, dict) else node
        return "inline:" + json.dumps(shape, sort_keys=True, ensure_ascii=False), (), True


def _walk(o, ptr, out, rel):
    if isinstance(o, dict):
        props = o.get("properties")
        if isinstance(props, dict):
            for name, d in props.items():
                out.append((name, rel, f"{ptr}/properties/{name.replace('~', '~0').replace('/', '~1')}", d))
        if {"name", "in", "schema"} <= set(o) and isinstance(o.get("name"), str):
            out.append((o["name"], rel, f"{ptr}/schema", o["schema"]))
        for k, v in o.items():
            _walk(v, f"{ptr}/{k.replace('~', '~0').replace('/', '~1')}", out, rel)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, f"{ptr}/{i}", out, rel)


DEID_REFS = {"#/$defs/Masked", "#/$defs/Redacted"}


def _keep_patterns(root: pathlib.Path) -> dict:
    p = root / "boundary_contracts/data/deid_rules.json"
    if not p.exists():
        p = root / "data/deid_rules.json"
    return json.loads(p.read_text(encoding="utf-8")).get("keep_patterns", {}) if p.exists() else {}


def _deid_branch_ok(node, name: str, keep: dict) -> bool:
    """비식별 합집합의 가지 하나가 허용 구조인가: 마스킹·제거 참조, null, 그 이름의 공개 keep 패턴 문자열, 또는 그런 가지만 가진 anyOf.
    무제약 가지({} 등)나 다른 패턴은 허용하지 않는다(codex 3차 검토: 가지 하나만 보면 {} 를 더해도 통과했다)."""
    if not isinstance(node, dict):
        return False
    body = {k: v for k, v in node.items() if k not in ANNOT}
    if set(body) == {"$ref"}:
        return body["$ref"] in DEID_REFS
    if body == {"type": "null"}:
        return True
    if set(body) == {"type", "pattern"} and body["type"] == "string" and name in keep:
        return body["pattern"] == f"^(?:{keep[name]})$(?![\\s\\S])"
    if set(body) == {"anyOf"} and isinstance(body["anyOf"], list) and body["anyOf"]:
        return all(_deid_branch_ok(a, name, keep) for a in body["anyOf"])
    return False


def _deid_kind(node, name: str = "", keep: dict | None = None) -> str:
    """생성물 칸의 끝점 종류를 구조로 판정한다: 의사 식별자 참조, 마스킹 참조, 또는 모든 가지가 허용 구조이고 마스킹·제거 참조를
    하나 이상 가진 비식별 합집합(gen_deid_view.py 가 만드는 모양). 그 밖은 other(실패)."""
    keep = keep or {}
    if isinstance(node, dict) and set(node) - ANNOT == {"$ref"}:
        r = node["$ref"]
        return "Pseudonym" if r == "#/$defs/Pseudonym" else "Masked" if r == "#/$defs/Masked" else "other"
    if isinstance(node, dict) and set(node) - ANNOT == {"anyOf"} and isinstance(node["anyOf"], list):
        refs = {a.get("$ref") for a in node["anyOf"] if isinstance(a, dict) and set(a) - ANNOT == {"$ref"}}
        if refs & DEID_REFS and all(_deid_branch_ok(a, name, keep) for a in node["anyOf"]):
            return "deid-anyof"
    return "other"


def check(root: pathlib.Path, allow: dict) -> list[str]:
    repo = Repo(root)
    keep = _keep_patterns(root)
    gen_files = {g["file"] for g in allow.get("generated", [])}
    gen_ok = {(g["file"], g["name"], g["kind"]) for g in allow.get("generated", [])}
    ref_ok = {(l["file"], l["pointer"]) for l in allow.get("refinements", [])}
    reg = {(r["file"], r["pointer"]): r["endpoint"] for r in allow.get("id_registry", [])}
    fields = []
    for sub in ("schemas", "openapi"):
        for p in sorted((root / sub).glob("*.json")):
            _walk(repo.doc(f"{sub}/{p.name}"), "", fields, f"{sub}/{p.name}")
    problems: list[str] = []
    by_name: dict[str, dict[tuple, list[str]]] = {}
    inline_locs: dict[str, list[str]] = {}
    used_gen, used_ref, used_reg = set(), set(), set()
    for name, rel, ptr, node in fields:
        segs = ptr.split("/")
        if any(s in SKIP_COND for s in segs):
            continue
        if not (name.endswith("_id") or name == "id"):
            continue
        if node == NULL_ONLY and any(s in ("then", "else") for s in segs):
            continue
        end, refs, inline = repo.definition(rel, ptr, node)
        loc = f"{rel}#{ptr}"
        if rel in gen_files:
            k = (rel, name, _deid_kind(node, name, keep))
            if k not in gen_ok:
                problems.append(f"{loc}: 생성물 안의 {name} 이 허용 목록 generated 에 없는 끝점 {end[:80]}")
            used_gen.add(k)
            continue
        if refs:
            used_ref.add((rel, ptr))
            if (rel, ptr) not in ref_ok:
                problems.append(f"{loc}: {name} 의 좁히기 {list(refs)} 에 근거가 없다(허용 목록 refinements)")
        if name == "id":
            want = reg.get((rel, ptr))
            used_reg.add((rel, ptr))
            got = "inline" if inline else end
            if want is None:
                problems.append(f"{loc}: 'id' 칸이 id_registry 에 없다(뜻과 끝점을 적는다). 끝점 {got[:80]}")
            elif want != got:
                problems.append(f"{loc}: 'id' 칸의 끝점 {got[:80]} 이 id_registry 의 {want} 와 다르다")
            continue
        # 근거가 있는 좁히기는 같은 타입의 허용된 좁히기로 본다(정의 비교는 끝점으로). 근거 없는 좁히기는 위에서 실패했고 비교에도 다른 정의로 남는다.
        key = (end, ()) if refs and (rel, ptr) in ref_ok else (end, refs)
        by_name.setdefault(name, {}).setdefault(key, []).append(loc)
        if inline:
            inline_locs.setdefault(name, []).append(loc)
    for name, defs in sorted(by_name.items()):
        if len(defs) > 1:
            detail = "; ".join(f"{e[:80]}{' +' + ','.join(r) if r else ''} <- {locs[0]}" + (f" 외 {len(locs) - 1}곳" if len(locs) > 1 else "")
                               for (e, r), locs in defs.items())
            problems.append(f"{name}: 정의 {len(defs)}종 — {detail}")
    for name, locs in sorted(inline_locs.items()):
        if len(locs) > 1:
            problems.append(f"{name}: 인라인 정의가 {len(locs)}곳(정의는 한 번, 나머지는 $ref) — {', '.join(locs[:3])}")
    for g in allow.get("generated", []):
        if (g["file"], g["name"], g["kind"]) not in used_gen:
            problems.append(f"허용 목록 generated 의 낡은 항목: {g['file']} {g['name']} {g['kind']}")
    for l in allow.get("refinements", []):
        if (l["file"], l["pointer"]) not in used_ref:
            problems.append(f"허용 목록 refinements 의 낡은 항목(그 자리에 좁히기가 없다): {l['file']}#{l['pointer']}")
    for k in reg:
        if k not in used_reg:
            problems.append(f"id_registry 의 낡은 항목: {k[0]}#{k[1]}")
    return problems


def main(argv):
    root = pathlib.Path(__file__).resolve().parents[1]
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print("--root 에는 디렉터리가 필요하다", file=sys.stderr)
            return 2
        root = pathlib.Path(argv[i + 1])
    allow_path = root / "tools/id_defs_allowlist.json"
    allow = json.loads(allow_path.read_text(encoding="utf-8")) if allow_path.exists() else {}
    for sect, key in (("generated", "reason"), ("refinements", "reason"), ("id_registry", "means")):
        for item in allow.get(sect, []):
            if not str(item.get(key, "")).strip():
                print(f"FAIL 허용 목록 {sect} 항목에 근거({key})가 없다: {item}")
                return 1
    probs = check(root, allow)
    for p in probs:
        print("FAIL", p)
    if not probs:
        print("OK   _id·id 칸은 한 정의만 참조한다(범위: 이름이 _id 로 끝나거나 id 인 칸)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
