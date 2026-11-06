"""Formats must be active dependencies, not optional unchecked annotations."""
from unittest.mock import patch
import jsonschema
import pytest
from boundary_contracts import format_checker, validator
from boundary_contracts.clients._http import require_egress_proxy


def test_real_contract_rejects_invalid_calendar_date():
    v=validator("StaffAlert")
    import json
    from pathlib import Path
    record=json.loads((Path(__file__).parents[1]/"examples/StaffAlert.json").read_text())
    v.validate(record)
    record["created_at"]="2026-02-30T00:00:00Z"
    assert not v.is_valid(record)


def test_missing_format_dependency_fails_instead_of_accepting_data():
    with patch.object(jsonschema.FormatChecker,"checkers",{}):
        with pytest.raises(RuntimeError,match="missing schema format validators"):
            format_checker()


def test_unknown_new_format_cannot_silently_disable_assertion():
    with pytest.raises(RuntimeError,match="unregistered-future-format"):
        format_checker({"format":"unregistered-future-format"})


@pytest.mark.parametrize("url",["http://127.0.0.1:1","http://127.255.255.255:65535","http://[::1]:3128/","http://localhost:3128",
 "http://127.0.0.1:0","http://127.0.0.1:65536","http://127.999.0.1:3128","http://127.0.0.1:3128#fragment",
 "http://user:password@localhost:3128","http://localhost:3128?x=1","http://localhost:3128\n"])
def test_sdk_uses_the_same_proxy_rule_as_the_schema(url):
    expected=validator("CommonEnv").is_valid({"OPENIT_EGRESS_PROXY":url})
    try:require_egress_proxy(url); actual=True
    except ValueError:actual=False
    assert expected==actual
