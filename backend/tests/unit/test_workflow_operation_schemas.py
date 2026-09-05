import pytest
from pydantic import ValidationError

from biz.schemas.workflow_operations import WorkflowExecuteRequest


def test_workflow_execute_request_accepts_missing_or_positive_limit():
    assert WorkflowExecuteRequest().payload == {}
    assert WorkflowExecuteRequest(payload={"limit": 10}).payload["limit"] == 10


@pytest.mark.parametrize("invalid", [0, -1, True, None, "10"])
def test_workflow_execute_request_rejects_invalid_limit(invalid):
    with pytest.raises(ValidationError, match="limit 必须为正整数"):
        WorkflowExecuteRequest(payload={"limit": invalid})
