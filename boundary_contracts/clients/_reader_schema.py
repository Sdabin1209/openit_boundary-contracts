"""읽기 모드 검증기(CONVENTIONS 1절 3항, 관대한 읽기): 이웃이 보낸 응답에서 모르는 필드와 모르는 열거값을 받아들인다.

불변식: 읽기 모드는 엄격 검증기(`schemas_api.validator`)가 받는 레코드를 하나도 거절하지 않는다(엄격 ⊆ 읽기).
넓히기(열거→문자열, additionalProperties:false→true, oneOf→anyOf)는 "맞으면 받는" 긍정 자리에서만 안전하다.
`if`·`not`·`contains`(maxContains 로 개수를 세는 자리 포함)는 넓히면 오히려 좁아지거나 뜻이 바뀌므로(4.0.3, CR-S-003)
그 하위 스키마와, 그 안의 `$ref` 가 가리키는 정의(같은 문서의 $defs, 다른 계약 문서, 문진 스키마)를 모두 원래의 엄격한 뜻으로 평가한다.
이를 위해 모든 문서를 두 벌로 둔다: 원래 URI 에는 넓힌 사본, `https://strict.invalid/<scheme>/<authority|_>/<path>` 에는 엄격 사본.
엄격 자리 안의 `$ref` 는 엄격 URI 로 다시 쓴다. 엄격 사본 안의 `$ref` 도 엄격 URI 로 다시 써서 엄격 영역 밖으로 새지 않는다.

위치 보존: 넓힌 사본은 JSON 포인터 `$ref` 가 가리키는 자리를 옮기지 않는다. additionalProperties:false 는 지우지 않고 true 로 바꾸고,
oneOf 의 anyOf 감싸기는 원래 allOf 항목들 뒤에 붙여 allOf/N 의 번호를 밀지 않는다. 포인터가 `oneOf/N` 을 지나가면(넓힌 사본에서 그 자리가 사라진다)
조용히 다른 곳을 가리키지 않도록 변환을 멈춘다(ValueError). 동적 참조($dynamicRef 등)도 같다. 문서는 참조될 때 하나씩 변환하므로
지원하지 않는 구문이 있는 문서는 그 문서를 쓰는 읽기만 멈추고 다른 계약의 읽기에는 번지지 않는다.

스키마 키워드를 아는 순회만 한다: `properties`·`$defs` 의 키는 이름이고, `const`·`enum`·`default`·`examples` 의 값은 데이터라 건드리지 않는다
(이름이 "enum"·"if" 인 속성이나 const 안의 객체를 스키마로 오인하면 엄격 ⊆ 읽기가 깨진다).

문서 위치: `schemas_api.validator` 처럼 문서는 등록 URI 에 놓인 것으로 보고 루트 `$id` 는 쓰지 않는다(상대 참조는 등록 URI 기준)."""
from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import urljoin, urlsplit

_STRICT = "https://strict.invalid/"
_NAME_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
_SCHEMA_LISTS = ("anyOf", "prefixItems")
_SCHEMA_ONE = ("items", "additionalProperties", "then", "else", "propertyNames", "unevaluatedProperties",
               "unevaluatedItems", "contentSchema")
_STRICT_ZONES = ("if", "not", "contains")
_UNSUPPORTED = ("$dynamicRef", "$dynamicAnchor", "$recursiveRef", "$recursiveAnchor")


def strict_uri(uri: str) -> str:
    """계층 URI(scheme://authority/path?query)만 받는다. authority 를 보존해 왕복이 같다(file://host/... 포함)."""
    base, hashmark, frag = uri.partition("#")
    if uri.startswith(_STRICT):
        return uri
    parts = urlsplit(base)
    if not parts.scheme or not base[len(parts.scheme) + 1:].startswith("//"):
        raise ValueError(f"읽기 모드 변환은 계층 URI 만 지원한다: {base[:80]}")
    tail = parts.path.lstrip("/") + ("?" + parts.query if parts.query else "")
    return f"{_STRICT}{parts.scheme}/{parts.netloc or '_'}/{tail}{hashmark}{frag}"


def original_uri(uri: str) -> str:
    scheme, _, rest = uri[len(_STRICT):].partition("/")
    netloc, _, tail = rest.partition("/")
    return f"{scheme}://{'' if netloc == '_' else netloc}/{tail}"


def _ref(ref: str, base: str, strict: bool) -> str:
    if not strict:
        frag = ref.partition("#")[2]
        if "/oneOf/" in "/" + frag + "/" or frag.rstrip("/").endswith("/oneOf"):
            raise ValueError(f"넓힌 사본에서 oneOf 는 자리를 옮기므로 그 안을 가리키는 $ref 를 지원하지 않는다: {ref[:120]}")
        return ref
    return strict_uri(urljoin(base, ref))


def transform(node, base: str, strict: bool):
    """strict=False 면 넓힌 사본, True 면 `$ref` 만 엄격 URI 로 다시 쓴 엄격 사본."""
    if not isinstance(node, dict):
        return node
    if any(k in node for k in _UNSUPPORTED):
        # 동적 참조는 실행 중 범위에 따라 대상이 바뀌어 엄격 영역 밖으로 샐 수 있다. 계약·문진 스키마에 없다: 생기면 조용히 넘기지 않고 멈춘다
        raise ValueError("읽기 모드 변환은 $dynamicRef/$dynamicAnchor/$recursiveRef 를 지원하지 않는다")
    out: dict = {}
    derived_type = None
    tail_allof: list = []
    if isinstance(node.get("$id"), str):
        # 안쪽 $id 는 새 리소스의 시작이다: 아래의 상대 참조는 그 $id 를 기준으로 푼다(Draft 2020-12 8.2.1). 엄격 사본에서는 그 리소스 ID 도 엄격 URI 로 쓴다
        base = urljoin(base, node["$id"])
        out["$id"] = strict_uri(base) if strict else node["$id"]
    for k, v in node.items():
        if k == "$id":
            continue
        if k == "$ref" and isinstance(v, str):
            out[k] = _ref(v, base, strict)
        elif k in _NAME_MAPS and isinstance(v, dict):
            out[k] = {name: transform(s, base, strict) for name, s in v.items()}
        elif k in _SCHEMA_LISTS and isinstance(v, list):
            out[k] = [transform(s, base, strict) for s in v]
        elif k == "allOf" and isinstance(v, list):
            out[k] = [transform(s, base, strict) for s in v]
        elif k == "oneOf" and isinstance(v, list):
            if strict:
                out[k] = [transform(s, base, True) for s in v]
            else:   # 넓힌 가지는 둘 이상이 함께 맞을 수 있다: 하나 이상 맞으면 받는다(넓힌 가지 ⊇ 엄격 가지이므로 엄격 ⊆ 읽기)
                tail_allof.append({"anyOf": [transform(s, base, False) for s in v]})
        elif k in _STRICT_ZONES:
            out[k] = transform(v, base, True)
        elif k in _SCHEMA_ONE:
            if not strict and k == "additionalProperties" and v is False:
                out[k] = True      # 지우지 않고 true: 포인터가 가리키는 자리를 보존한다
                continue
            out[k] = transform(v, base, strict)
        elif (not strict and k == "enum" and isinstance(v, list) and v
              and all(isinstance(x, str) or x is None for x in v) and any(isinstance(x, str) for x in v)):
            derived_type = ["string", "null"] if None in v else "string"   # 왜: null 을 허용하는 열거(pause_reason 등)도 모르는 값은 받는다
        else:
            out[k] = v      # type·pattern·const·required·default·examples 등: 그대로(데이터 값은 순회하지 않는다)
    if tail_allof:
        out["allOf"] = out.get("allOf", []) + tail_allof    # 원래 allOf 항목 뒤에: allOf/N 번호를 밀지 않는다
    if derived_type is not None and "type" not in out:
        out["type"] = derived_type   # 원래 type 이 있으면 그것이 열거값을 이미 포함하므로 원래 것을 둔다
    return out


def _resource(doc: dict, uri: str, strict: bool):
    from referencing import Resource
    from referencing.jsonschema import DRAFT202012
    from ..schemas_api import format_checker
    format_checker(doc)
    doc = {k: v for k, v in doc.items() if k != "$id"}     # 문서는 등록 URI 에 놓인다(schemas_api.validator 와 같다)
    rid = strict_uri(uri) if strict else uri
    return Resource.from_contents({**transform(doc, uri, strict), "$id": rid}, default_specification=DRAFT202012)


@lru_cache(maxsize=1)
def _local_docs() -> dict:
    from ..schemas_api import schema_dir
    docs = {}
    base = schema_dir().as_uri() + "/"
    for path in schema_dir().glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        docs[path.as_uri()] = doc
        if isinstance(doc.get("$id"), str):
            docs.setdefault(urljoin(base, doc["$id"]), doc)
    return docs


@lru_cache(maxsize=1)
def _base_registry():
    """문서는 처음 참조될 때 하나씩 변환한다(지원하지 않는 구문이 있는 문서가 다른 계약의 읽기를 멈추지 않게)."""
    from referencing import Registry
    from ..schema_sources import external_schema

    def retrieve(uri):
        strict = uri.startswith(_STRICT)
        orig = original_uri(uri) if strict else uri
        doc = _local_docs().get(orig)
        if doc is None:
            doc = external_schema(orig)
        return _resource(doc, orig, strict)

    return Registry(retrieve=retrieve)


def reader_validator(schema: dict, uri: str):
    """`schema`(엄격 계약 스키마)를 `uri` 에 둔 읽기 모드 검증기. 같은 문서의 엄격 사본도 함께 등록한다."""
    import jsonschema
    from ..schemas_api import format_checker
    relaxed = _resource(schema, uri, False)
    registry = _base_registry().with_resources([(uri, relaxed), (strict_uri(uri), _resource(schema, uri, True))])
    return jsonschema.Draft202012Validator(relaxed.contents, registry=registry, format_checker=format_checker(schema))
