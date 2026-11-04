"""3.4.11: ImageLabels 가 properties 에 둔 모든 io.openit.* 라벨을 propertyNames 도 받아야 한다(3.4.10 에서 database 가 빠졌다 — release-gate 담당이 찾음)."""
import json
from boundary_contracts import load_schema, validator


def test_every_declared_label_is_accepted_by_property_names():
    s = load_schema("ImageLabels")
    v = validator("ImageLabels")
    decl = json.dumps(json.load(open(__file__.rsplit("/tests/", 1)[0] + "/examples/DatabaseDeclaration.json")))
    for name, spec in s["properties"].items():
        errs = [e for e in v.iter_errors({name: decl if name == "io.openit.database" else "x"}) if e.validator == "propertyNames"]
        assert not errs, (name, [e.message for e in errs])


def test_database_label_with_declaration_is_valid_in_a_full_label_set():
    ex = json.load(open(__file__.rsplit("/tests/", 1)[0] + "/examples/ImageLabels.json"))
    ex["io.openit.database"] = json.dumps(json.load(open(__file__.rsplit("/tests/", 1)[0] + "/examples/DatabaseDeclaration.json")))
    errs = [e.message for e in validator("ImageLabels").iter_errors(ex)]
    assert not errs, errs
