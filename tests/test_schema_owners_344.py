"""3.4.4: 모든 계약 스키마는 누구의 출력(x-producers)이고 누구의 입력(x-consumers)인지 적는다(CONVENTIONS 13절).
계약은 '누구의 입력 → 누구의 출력'이다. 이 칸이 없으면 출력이 틀렸을 때 어느 영역의 결함인지 정할 수 없다."""
import json
from pathlib import Path

import pytest

from boundary_contracts import schema_dir

# CONVENTIONS 13절의 목록과 같아야 한다(영역 목록의 정본은 head/shared/areas.json, 헤드의 cross-area-check 가 대조한다).
AREAS = {
    "head", "deploy", "platform", "model-runtime", "model-lab", "synthetic-data", "survey-service",
    "release-gate", "ops-feedback", "question-authoring", "kiosk-frontend", "admin-console",
}
OTHER = {"*", "external:person", "external:install-site"}

SCHEMAS = sorted(Path(schema_dir()).glob("*.schema.json"))


def test_there_are_schemas():
    assert len(SCHEMAS) >= 90


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_schema_names_its_producers_and_consumers(path):
    s = json.loads(path.read_text(encoding="utf-8"))
    for key in ("x-producers", "x-consumers"):
        v = s.get(key)
        assert isinstance(v, list) and v, f"{path.name}: {key} 가 없거나 비었다"
        assert len(v) == len(set(v)), f"{path.name}: {key} 중복"
        unknown = set(v) - AREAS - OTHER
        assert not unknown, f"{path.name}: {key} 에 모르는 이름 {sorted(unknown)}"


def test_external_schema_registry_names_owners():
    """EXTERNAL_SCHEMAS.json(검토 B-20): 정본이 문진 스키마인 영역 사이 스키마도 주인을 적는다."""
    reg = json.loads((Path(schema_dir()).parent.parent / "EXTERNAL_SCHEMAS.json").read_text(encoding="utf-8"))
    assert reg["owner"] == "survey-service" and reg["package"] == "openit-survey-schema"
    names = [e["name"] for e in reg["schemas"]]
    assert len(names) == len(set(names)) and names
    local = {p.name[: -len(".schema.json")] for p in SCHEMAS}
    assert not (set(names) & local), "같은 이름을 두 곳이 정본으로 가지면 안 된다"
    for e in reg["schemas"]:
        for key in ("x-producers", "x-consumers"):
            v = e[key]
            assert v and not (set(v) - AREAS - OTHER), (e["name"], key)
