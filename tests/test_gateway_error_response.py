"""The HTTP status, gateway body and retry header form one declared response."""
import copy
import pytest
from boundary_contracts import validator

GOOD = {"status":503,"headers":{"retry-after":"5"},"body":{"code":"UPSTREAM_UNAVAILABLE"}}

@pytest.mark.parametrize("status",[503,504])
def test_gateway_failure_response(status):
    validator("GatewayErrorResponse").validate(dict(GOOD,status=status))

@pytest.mark.parametrize("change",[lambda d:d.update(status=500),lambda d:d["headers"].clear(),lambda d:d["headers"].update({"retry-after":"1"}),lambda d:d["body"].update(code="UNAVAILABLE")])
def test_gateway_failure_response_rejects_mismatch(change):
    data=copy.deepcopy(GOOD);change(data)
    assert list(validator("GatewayErrorResponse").iter_errors(data))
