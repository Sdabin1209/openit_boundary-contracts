"""패키지에 포함된 경계 계약 스키마(JSON Schema Draft 2020-12)를 찾는다."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PIPELINE_SCHEMA_VERSION = "5.0"


def schema_dir() -> Path:
    """<계약명>.schema.json 과 _common.schema.json 이 있는 디렉터리."""
    return Path(__file__).resolve().parent / "schemas"


def load_schema(name: str) -> dict:
    """계약 이름(예: 'ReleaseManifest')의 스키마. 내부의 $ref는 같은 디렉터리의 _common.schema.json을 가리킨다."""
    path = schema_dir() / f"{name}.schema.json"
    if not path.exists():
        raise KeyError(f"알 수 없는 경계 계약: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _formats(node):
    if isinstance(node, dict):
        if isinstance(node.get("format"), str):
            yield node["format"]
        for value in node.values():
            yield from _formats(value)
    elif isinstance(node, list):
        for value in node:
            yield from _formats(value)


@lru_cache(maxsize=1)
def _required_formats():
    return frozenset(f for path in schema_dir().glob("*.schema.json")
                     for f in _formats(json.loads(path.read_text(encoding="utf-8"))))


def format_checker(schema=None):
    """Fail when a declared format lacks its validator; never silently ignore it.

    OpenAPI's binary wire annotation is handled by the HTTP byte/stream layer.
    """
    import jsonschema
    required = (_required_formats() | set(_formats(schema))) - {"binary"}
    missing = required - set(jsonschema.FormatChecker.checkers)
    if missing:
        raise RuntimeError("missing schema format validators: " + ", ".join(sorted(missing)))
    return jsonschema.FormatChecker()


def schema_registry(*, schema_sources=None, transform=None):
    """Immutable offline registry; each schema is resolved from its declared owner."""
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    from urllib.parse import urljoin
    from .schema_sources import external_schema

    def resource(doc, uri):
        format_checker(doc)
        if transform:
            doc = transform(doc)
        return Resource.from_contents({**doc, "$id": uri}, default_specification=DRAFT202012)

    def retrieve(uri):
        return resource(external_schema(uri, schema_sources), uri)

    registry = Registry(retrieve=retrieve)
    base = schema_dir().as_uri() + "/"
    for path in schema_dir().glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        value = resource(doc, path.as_uri())
        registry = registry.with_resource(path.as_uri(), value)
        if "$id" in doc:
            registry = registry.with_resource(urljoin(base, doc["$id"]), value)
    return registry


def validator(name: str, *, schema_sources=None):
    """Draft 2020-12 validation with formats and offline owner references."""
    import jsonschema
    name, _, fragment = name.partition("#")
    uri = (schema_dir() / f"{name}.schema.json").as_uri()
    schema = {**load_schema(name), "$id": uri}
    if fragment:
        schema = {"$ref": uri + "#" + fragment}
    jsonschema.Draft202012Validator.check_schema(schema)
    return _finite_validator_class()(schema, registry=schema_registry(schema_sources=schema_sources),
                                     format_checker=format_checker(schema))


@lru_cache(maxsize=1)
def _finite_validator_class():
    """Draft 2020-12 에서 "number"·"integer" 타입이 NaN·무한대를 받지 않게 한 검증기(5.0.0, I-JSON RFC 7493).
    왜: 파이썬 객체를 바로 검증하면 json 이 만든 float('inf')(본문의 1e999)가 type number 를 통과했다(결함 대장 #10 가설).
    정수 범위·깊이·노드 예산 같은 값 전체 규칙은 validate()/strict_json.check_json_value 가 본다."""
    import math
    import jsonschema
    base = jsonschema.Draft202012Validator.TYPE_CHECKER
    def number(checker, x):
        return base.is_type(x, "number") and (not isinstance(x, float) or math.isfinite(x))
    def integer(checker, x):
        return base.is_type(x, "integer") and (not isinstance(x, float) or math.isfinite(x))
    tc = base.redefine_many({"number": number, "integer": integer})
    return jsonschema.validators.extend(jsonschema.Draft202012Validator, type_checker=tc)


def validate(name: str, value, *, schema_sources=None) -> None:
    """계약 검증 진입점(5.0.0): 계약 JSON 공통 규칙(strict_json.check_json_value: 유한한 수, ±2**53 정수, 깊이 64, 노드 예산)을 먼저 보고
    스키마 검증을 한다. 어기면 BoundaryError(INVALID_RECORD, details.errors 에 처음 몇 개)."""
    from .errors import BoundaryError
    from .strict_json import check_json_value
    check_json_value(value)
    errs = sorted(validator(name, schema_sources=schema_sources).iter_errors(value), key=lambda e: list(e.absolute_path))
    if errs:
        raise BoundaryError("INVALID_RECORD", f"{name} 계약 위반 {len(errs)}건",
                            {"errors": [f"/{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in errs[:5]]})
