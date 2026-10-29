"""패키지에 포함된 경계 계약 스키마(JSON Schema Draft 2020-12)를 찾는다."""
from __future__ import annotations

import json
from pathlib import Path

PIPELINE_SCHEMA_VERSION = "2.6"


def schema_dir() -> Path:
    """<계약명>.schema.json 과 _common.schema.json 이 있는 디렉터리."""
    return Path(__file__).resolve().parent / "schemas"


def load_schema(name: str) -> dict:
    """계약 이름(예: 'ReleaseManifest')의 스키마. 내부의 $ref는 같은 디렉터리의 _common.schema.json을 가리킨다."""
    path = schema_dir() / f"{name}.schema.json"
    if not path.exists():
        raise KeyError(f"알 수 없는 경계 계약: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def validator(name: str):
    """계약 이름으로 jsonschema 검증기를 만든다(_common 참조를 해석한다)."""
    import jsonschema

    base = schema_dir().as_uri() + "/"
    common = json.loads((schema_dir() / "_common.schema.json").read_text(encoding="utf-8"))
    schema = load_schema(name)
    store = {base + p.name: json.loads(p.read_text(encoding="utf-8")) for p in schema_dir().glob("*.schema.json")}
    store[base + "_common.schema.json"] = common
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, resolver=jsonschema.RefResolver(base, schema, store=store))
