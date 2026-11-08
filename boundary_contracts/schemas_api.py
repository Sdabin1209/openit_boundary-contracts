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
    return ContractValidator(jsonschema.Draft202012Validator(schema, registry=schema_registry(schema_sources=schema_sources),
                                                             format_checker=format_checker(schema)))


def nonfinite_errors(instance):
    """값 안의 NaN·무한대 float 위치마다 jsonschema.ValidationError 하나(값은 싣지 않는다). 반복 순회(재귀 없음).
    왜 스키마 키워드가 아니라 값 순회인가: jsonschema 는 $ref 로 다른 파일에 들어가면 그 파일의 $schema 로 검증기 클래스를
    다시 고른다(validator_for). 그래서 type checker 를 바꾼 확장 클래스는 파일 경계를 넘으면 표준 클래스로 돌아가
    number 가 무한대를 받았다(codex 재검토 2026-11-08). 값 전체를 먼저 보면 참조 경로와 상관없다(I-JSON RFC 7493, CONVENTIONS 10절)."""
    import math
    from collections import deque
    import jsonschema
    stack = [(instance, ())]
    while stack:
        v, path = stack.pop()
        if isinstance(v, float) and not math.isfinite(v):
            yield jsonschema.ValidationError("NaN·무한대는 계약 JSON 값이 아니다(I-JSON, CONVENTIONS 10절)", validator="finite",
                                             path=deque(path), validator_value=None, instance=None, schema={})
        elif isinstance(v, dict):
            stack.extend((x, path + (k,)) for k, x in v.items())
        elif isinstance(v, (list, tuple)):
            stack.extend((x, path + (i,)) for i, x in enumerate(v))


class ContractValidator:
    """계약 검증기(5.0.0): 표준 Draft 2020-12 검증 앞에 비유한 수 검사를 붙인다. iter_errors·is_valid·validate 모두 같은 규칙이다.
    나머지 속성(schema, evolve 등)은 안쪽 표준 검증기의 것을 그대로 쓴다."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        # 값 데이터·설정만 넘긴다(schema, format_checker, is_type 등). 검증기를 돌려주거나 오류를 내는 메서드는 아래에 모두 명시했다:
        # evolve·descend·iter_errors·is_valid·validate. 그 밖의 공개 메서드(check_schema·is_type)는 검증기를 돌려주지 않는다.
        return getattr(self._inner, name)

    def evolve(self, **changes):
        """안쪽 검증기의 evolve(schema·format_checker·registry 등 인자 그대로 보존) 결과를 다시 감싼다.
        왜: evolve 가 표준 검증기를 그대로 돌려주면 그 뒤의 검증이 비유한 수 검사를 건너뛴다(codex 3차 검토, link _resolve·question-authoring 이 evolve 를 쓴다)."""
        return ContractValidator(self._inner.evolve(**changes))

    def descend(self, instance, schema, path=None, schema_path=None, resolver=None):
        """하위 스키마 검증도 같은 정책: 그 하위 값의 비유한 수 오류를 먼저 내고(오류 경로 앞에 path 를 붙인다) 안쪽 descend 를 잇는다."""
        for e in nonfinite_errors(instance):
            if path is not None:
                e.path.appendleft(path)
            if schema_path is not None:
                e.schema_path.appendleft(schema_path)
            yield e
        kw = {"path": path, "schema_path": schema_path}
        if resolver is not None:
            kw["resolver"] = resolver
        yield from self._inner.descend(instance, schema, **kw)

    @property
    def inner(self):
        """안쪽 표준 Draft 2020-12 검증기(읽기 전용). 이것으로 직접 검증하면 비유한 수 검사가 없다는 것을 호출자가 안다."""
        return self._inner

    def iter_errors(self, instance, *args, **kwargs):
        yield from nonfinite_errors(instance)
        yield from self._inner.iter_errors(instance, *args, **kwargs)

    def is_valid(self, instance, *args, **kwargs):
        return next(self.iter_errors(instance, *args, **kwargs), None) is None

    def validate(self, instance, *args, **kwargs):
        import jsonschema
        err = jsonschema.exceptions.best_match(self.iter_errors(instance, *args, **kwargs))
        if err is not None:
            raise err


def safe_error(e) -> dict:
    """값 없는 진단: 스키마 쪽 위치(absolute_schema_path)와 키워드 이름만. 인스턴스 경로는 사용자가 정한 키(환자 문장일 수 있다)를
    담을 수 있어 싣지 않는다(INTERFACES I7 '오류에 값을 싣지 않는다'). 스키마 경로의 이름은 계약이 정한 이름뿐이다."""
    return {"schema_path": "/" + "/".join(map(str, e.absolute_schema_path)), "keyword": str(e.validator)}


def validate(name: str, value, *, schema_sources=None) -> None:
    """계약 검증 진입점(5.0.0). 먼저 계약 JSON 공통 규칙(strict_json.check_json_value: 유한한 수, ±2**53 정수, 깊이 64, 값 2**19,
    압축 직렬화 1 MiB)을 보고, 그다음 스키마 검증을 한다. 어기면 BoundaryError(INVALID_RECORD).
    오류에는 값을 싣지 않는다: details.errors 는 처음 5개의 {schema_path, keyword} 뿐이다(INTERFACES I7)."""
    from .errors import BoundaryError
    from .strict_json import check_json_value, check_serialized_size
    check_json_value(value)
    check_serialized_size(value)
    errs = list(validator(name, schema_sources=schema_sources).iter_errors(value))
    if errs:
        raise BoundaryError("INVALID_RECORD", f"{name} 계약 위반 {len(errs)}건", {"errors": [safe_error(e) for e in errs[:5]]})
