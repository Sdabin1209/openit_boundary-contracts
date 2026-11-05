"""Contract completeness and negative cases, independently of server implementation."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema
import pytest

from boundary_contracts import validator
from boundary_contracts.http_contracts import HttpContract, ContractViolation, catalog, document

ROOT = Path(__file__).resolve().parents[1]
KNOWN = {x["name"] for x in json.loads((ROOT / "EXTERNAL_SCHEMAS.json").read_text())["schemas"]}


def owner(name):
    if name not in KNOWN:
        raise KeyError(name)
    # A sentinel proves owner delegation without copying a domain schema.
    return {"type": "string", "const": "owner:" + name}


@pytest.mark.parametrize("service", list(catalog()["services"]))
def test_every_service_is_valid_openapi_with_closed_contract_extensions(service):
    meta = json.loads((ROOT / "tests/fixtures/openapi-3.1-schema.json").read_text())
    doc = document(service)
    jsonschema.Draft202012Validator(meta).validate(doc)
    validator("HttpServiceDocument").validate(doc)
    assert HttpContract(service, schema_sources={"survey": owner}).lint()["operations"]


def test_services_with_the_same_url_path_keep_independent_payload_schemas():
    a, b = document("survey-service"), document("question-authoring")
    assert a["paths"]["/v1/question-sets"]["get"]["responses"]["200"] != b["paths"]["/v1/question-sets"]["get"]["responses"]["200"]
    assert document("model-serving")["paths"]["/v1/releases/{release_id}"]["get"]["responses"]["200"] != document("release-gate")["paths"]["/v1/releases/{rid}"]["get"]["responses"]["200"]


@pytest.mark.parametrize("mutation", ["wildcard", "placeholder", "missing_body_policy", "no_path_parameter", "unknown_reference"])
def test_incomplete_declarations_fail(mutation):
    c = HttpContract("model-serving", schema_sources={"survey": owner})
    op = c.doc["paths"]["/v1/releases/{release_id}"]["put"]
    if mutation == "wildcard":
        op["responses"]["2XX"] = op["responses"].pop("200")
    elif mutation == "placeholder":
        op["responses"]["200"]["content"]["application/json"] = {"x-survey-schema": "anything"}
    elif mutation == "missing_body_policy":
        del op["x-body-absent"]
    elif mutation == "no_path_parameter":
        op["parameters"] = []
    else:
        op["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "https://unregistered.invalid/a"}
    with pytest.raises(Exception):
        validator("HttpServiceDocument").validate(c.doc)
        # lint operates on the instance's independently mutated declarations.
        c.lint()


def test_strict_query_types_and_body_media_type():
    c = HttpContract("question-authoring")
    with pytest.raises(ContractViolation):
        c.request("GET", "/v1/signals", params={}, query={"max_cases": "20001"}, headers={}, body=None)
    with pytest.raises(ContractViolation):
        c.request("GET", "/v1/question-sets", params={}, query={"limit": "501"}, headers={}, body=None)
    with pytest.raises(ContractViolation):
        c.request("POST", "/v1/drafts", params={}, query={}, headers={"Content-Type": "application/x-www-form-urlencoded"}, body={"question_set_id": "q1"})
    c.request("GET", "/v1/signals", params={}, query={"max_cases": "20000"}, headers={}, body=None)


def test_wrong_status_wrong_item_and_nonempty_no_content_are_rejected():
    c = HttpContract("model-serving")
    with pytest.raises(ContractViolation):
        c.response("PUT", "/v1/releases/{release_id}", 201, {})
    with pytest.raises(ContractViolation):
        HttpContract("model-registry").response("GET", "/v1/packages", 200, {"items": [{}], "next_cursor": None})
    with pytest.raises(ContractViolation):
        HttpContract("survey-service").response("POST", "/v1/staff/push-subscriptions/unsubscribe", 204, {})


def test_registered_external_owner_is_used_and_resolvers_are_safe_to_share():
    c = HttpContract("survey-service", schema_sources={"survey": owner})
    def check(_):
        c.response("POST", "/v1/sessions", 200, "owner:FrontendInput", content_type="application/json")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(check, range(80)))
    with pytest.raises(ContractViolation):
        c.response("POST", "/v1/sessions", 200, {}, content_type="application/json")


def test_job_config_must_name_its_schema_and_executable_cannot_be_empty():
    v = validator("JobsDeclaration")
    base = {"name": "maintenance", "argv": ["/app/job"], "idempotent": True}
    v.validate({"jobs": [base]})
    for delta in ({"argv": [""]}, {"config": {"container_path": "/etc/job.json"}}):
        with pytest.raises(jsonschema.ValidationError):
            v.validate({"jobs": [{**base, **delta}]})
