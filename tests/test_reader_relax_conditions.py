"""읽기 모드 불변식: 엄격 검증기가 받는 레코드는 읽기 모드도 받는다(엄격 ⊆ 읽기). 4.0.3, synthetic-data CR-S-003, 교차검증.

넓히기는 긍정 자리에서만 하고 if·not·contains 와 그 안의 $ref(같은 문서·다른 문서·문진 스키마)는 엄격한 뜻으로 평가한다."""
import json
from pathlib import Path

import jsonschema
import pytest

from boundary_contracts import load_schema, validator
from boundary_contracts.clients._http import _reader
from boundary_contracts.clients._reader_schema import reader_validator

ROOT = Path(__file__).resolve().parents[1]
URI = "file:///reader-test/T.schema.json"


def both(schema, rec):
    strict = jsonschema.Draft202012Validator(schema).is_valid(rec)
    return strict, reader_validator(schema, URI).is_valid(rec)


COND = {"type": "object", "properties": {"status": {"enum": ["ANSWERED", "MISSING"]}, "value": {}},
        "if": {"properties": {"status": {"enum": ["MISSING"]}}}, "then": {"properties": {"value": {"type": "null"}}}}
COND_REF = {"type": "object", "$defs": {"missing": {"properties": {"status": {"enum": ["MISSING"]}}}},
            "properties": {"status": {"enum": ["ANSWERED", "MISSING"]}, "value": {}},
            "if": {"$ref": "#/$defs/missing"}, "then": {"properties": {"value": {"type": "null"}}}}
NOT = {"type": "object", "properties": {"kind": {"type": "string", "not": {"enum": ["RETIRED"]}}}}
NOT_REF = {"$defs": {"retired": {"enum": ["RETIRED"]}}, "type": "object",
           "properties": {"kind": {"type": "string", "not": {"$ref": "#/$defs/retired"}}}}
ONE = {"oneOf": [{"type": "object", "properties": {"k": {"enum": ["A"]}}, "required": ["k"]},
                 {"type": "object", "properties": {"k": {"enum": ["B"]}}, "required": ["k"]}]}
COUNT = {"type": "array", "contains": {"enum": ["NEXT"]}, "minContains": 1, "maxContains": 1}
NAMED = {"type": "object", "properties": {"enum": {"const": {"additionalProperties": False, "enum": ["x"]}}},
         "required": ["enum"]}


@pytest.mark.parametrize("schema,rec", [
    (COND, {"status": "ANSWERED", "value": 5}), (COND_REF, {"status": "ANSWERED", "value": 5}),
    (NOT, {"kind": "ACTIVE"}), (NOT_REF, {"kind": "ACTIVE"}),
    (ONE, {"k": "A"}), (ONE, {"k": "B"}),
    (COUNT, ["NEXT", "OTHER"]),
    (NAMED, {"enum": {"additionalProperties": False, "enum": ["x"]}}),
    # 독립 검토 반례 D1~D3(4.0.3 첫 수정안에서 엄격 통과·읽기 거절)
    ({"$defs": {"X": {"type": "string", "enum": ["a"]}}, "not": {"$ref": "#/$defs/X"}}, "zzz"),
    ({"$defs": {"X": {"type": "string", "enum": ["a"]}}, "if": {"$ref": "#/$defs/X"}, "then": {"const": "a"}}, "zzz"),
    ({"type": "array", "contains": {"enum": ["a"]}, "maxContains": 1}, ["a", "b"]),
    ({"const": {"enum": ["a"]}}, {"enum": ["a"]}),
    ({"enum": [{"additionalProperties": False}]}, {"additionalProperties": False}),
    # 교차검증 반례: 안쪽 $id 아래의 상대 참조는 그 $id 를 기준으로 푼다
    ({"type": "object", "properties": {"x": {"$id": "child.json", "$defs": {"bad": {"enum": ["bad"]}},
                                             "not": {"$ref": "#/$defs/bad"}}}}, {"x": "ok"}),
    ({"type": "object", "$defs": {"c": {"$id": "c2.json", "$defs": {"bad": {"enum": ["bad"]}}, "not": {"$ref": "#/$defs/bad"}}},
      "properties": {"x": {"not": {"$ref": "c2.json"}}}}, {"x": "bad"}),
])
def test_strict_accepts_implies_reader_accepts(schema, rec):
    assert both(schema, rec) == (True, True)


@pytest.mark.parametrize("schema,rec", [
    (COND, {"status": "MISSING", "value": 5}), (COND_REF, {"status": "MISSING", "value": 5}),
    (NOT, {"kind": "RETIRED"}), (NOT_REF, {"kind": "RETIRED"}),
    (ONE, {}), (COUNT, ["NEXT", "NEXT"]),
    ({"type": "object", "properties": {"x": {"$id": "child.json", "$defs": {"bad": {"enum": ["bad"]}},
                                             "not": {"$ref": "#/$defs/bad"}}}}, {"x": "bad"}),
])
def test_conditions_keep_their_strict_meaning(schema, rec):
    assert both(schema, rec) == (False, False)


@pytest.mark.parametrize("schema,rec", [
    (COND, {"status": "NEW_STATUS", "value": 5, "extra": 1}), (ONE, {"k": "C"}),
])
def test_unknown_enum_values_and_fields_are_tolerated(schema, rec):
    assert both(schema, rec)[1] is True


def test_strict_zone_refs_into_other_contract_documents_stay_strict():
    # 다른 계약 문서의 정의를 if 안에서 참조해도 엄격한 뜻으로 평가한다
    s = {"type": "object", "properties": {"code": {"type": "string"}, "n": {}},
         "if": {"properties": {"code": {"$ref": "BoundaryError.schema.json#/properties/code"}}},
         "then": {"properties": {"n": {"type": "null"}}}}
    from boundary_contracts.schemas_api import schema_dir
    v = reader_validator(s, (schema_dir() / "_t.schema.json").as_uri())
    assert v.is_valid({"code": "NOT_A_CODE", "n": 5})     # 엄격 열거에 없으므로 if 거짓 → then 적용 안 함
    from boundary_contracts.schemas_api import schema_registry
    strict = jsonschema.Draft202012Validator({**s, "$id": (schema_dir() / "_t.schema.json").as_uri()}, registry=schema_registry())
    assert strict.is_valid({"code": "NOT_A_CODE", "n": 5})
    assert not v.is_valid({"code": "INVALID_RECORD", "n": 5}) and not strict.is_valid({"code": "INVALID_RECORD", "n": 5})


def _examples():
    for f in sorted((ROOT / "examples").rglob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        yield f.name.split(".")[0], rec, str(f)
    for path in sorted((ROOT / "boundary_contracts" / "schemas").glob("*.schema.json")):
        for i, rec in enumerate(json.loads(path.read_text(encoding="utf-8")).get("examples", [])):
            yield path.name.removesuffix(".schema.json"), rec, f"{path.name}#examples/{i}"


def test_every_strictly_valid_example_passes_the_reader():
    checked = 0
    for name, rec, where in _examples():
        try:
            load_schema(name)
        except KeyError:
            continue
        if not list(validator(name).iter_errors(rec)):          # 객체·배열·스칼라 예시 모두
            assert not list(_reader(name).iter_errors(rec)), where
            checked += 1
    assert checked > 0


def test_dynamic_refs_are_refused_not_silently_relaxed():
    with pytest.raises(ValueError):
        reader_validator({"$dynamicRef": "#meta"}, URI)


# 독립 검토 2차 반례(일반 Draft 2020-12 구문) — 4.0.3
def _strict_at(schema, uri=URI):
    return jsonschema.Draft202012Validator({**schema, "$id": uri})


def test_allof_pointer_indices_are_not_shifted_by_oneof_wrapping():
    s = {"$defs": {"h": {"oneOf": [{"type": "string"}, {"type": "integer"}], "allOf": [{"const": "p"}, {"type": "string"}]}},
         "properties": {"a": {"$ref": "#/$defs/h/allOf/1"}}}
    assert _strict_at(s).is_valid({"a": "q"}) and reader_validator(s, URI).is_valid({"a": "q"})


def test_additional_properties_false_location_is_kept_for_pointers():
    s = {"$defs": {"o": {"type": "object", "additionalProperties": False}},
         "properties": {"a": {"$ref": "#/$defs/o/additionalProperties"}}}
    assert _strict_at(s).is_valid({}) and reader_validator(s, URI).is_valid({})
    assert not _strict_at(s).is_valid({"a": 1})       # 엄격: false 스키마 / 읽기: true 로 넓어짐(허용 방향)


def test_pointer_into_oneof_is_refused_loudly():
    s = {"$defs": {"h": {"oneOf": [{"type": "string", "enum": ["x"]}, {"type": "integer"}]}},
         "properties": {"a": {"$ref": "#/$defs/h/oneOf/0"}}}
    with pytest.raises(ValueError):
        reader_validator(s, URI)


def test_root_id_is_ignored_like_the_strict_contract_validator():
    s = {"$id": "https://example.test/a.json", "$defs": {"X": {"enum": ["a"]}}, "if": {"$ref": "#/$defs/X"}, "then": {"const": "a"}}
    for rec in ("zzz", "a"):
        assert _strict_at(s).is_valid(rec) and reader_validator(s, URI).is_valid(rec)


@pytest.mark.parametrize("uri", ["file:///reader-test/T.schema.json", "file://server/share/t.json",
                                 "https://h:8443/p/t.json?x=1", "file:///C:/a%20b/t.json"])
def test_strict_uri_round_trips_hierarchical_uris(uri):
    from boundary_contracts.clients._reader_schema import strict_uri, original_uri
    assert original_uri(strict_uri(uri)) == uri


@pytest.mark.parametrize("uri", ["urn:example:t", "file:/a/t.json"])
def test_non_hierarchical_uris_are_refused(uri):
    with pytest.raises(ValueError):
        reader_validator({"if": {"$ref": "#/$defs/X"}, "$defs": {"X": {"enum": ["a"]}}}, uri)


def test_unsupported_document_does_not_break_other_readers(monkeypatch):
    from boundary_contracts.clients import _reader_schema as rs
    docs = dict(rs._local_docs())
    docs["file:///reader-test/Bad.schema.json"] = {"$dynamicAnchor": "n"}
    monkeypatch.setattr(rs, "_local_docs", lambda: docs)
    rs._base_registry.cache_clear()
    try:
        v = reader_validator({"properties": {"code": {"$ref": "BoundaryError.schema.json#/properties/code"}}},
                             (Path(__file__).resolve().parents[1] / "boundary_contracts" / "schemas" / "_t2.schema.json").as_uri())
        assert v.is_valid({"code": "ANYTHING"})
    finally:
        rs._base_registry.cache_clear()


def test_contract_and_survey_documents_use_no_construct_the_reader_refuses():
    # 읽기 모드가 멈추는 구문(동적 참조, oneOf 안을 가리키는 포인터, 비계층 URI)을 계약·문진 스키마에 들이지 않는다: 들어오면 여기서 먼저 걸린다
    from boundary_contracts.clients._reader_schema import transform, _local_docs
    from boundary_contracts.schema_sources import SURVEY_URI, external_schema
    import survey_schema, os
    docs = dict(_local_docs())
    sdir = os.path.dirname(survey_schema.__file__)
    for root, _, files in os.walk(sdir):
        for f in files:
            if f.endswith(".json") and root.replace(os.sep, "/").endswith("/v1/schemas"):
                docs[SURVEY_URI + f] = external_schema(SURVEY_URI + f)
    assert docs
    for uri, doc in docs.items():
        for strict in (False, True):
            transform({k: v for k, v in doc.items() if k != "$id"}, uri, strict)
