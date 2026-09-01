import pytest

ENDPOINT = "/api/v1/kg-construction/expert-indirect-relations/demo/structured-result"
VALID_PAYLOAD = {
    "core_node_id": "4G7t0B0t",
    "relation_types": ["学术关联"],
    "path_depth": 2,
    "min_strength": 0.65,
}


@pytest.mark.parametrize(
    ("overrides", "removed_field", "expected_field"),
    [
        ({"core_node_id": ""}, None, "core_node_id"),
        ({"core_node_id": "A" * 65}, None, "core_node_id"),
        ({"core_node_id": "!#@!@#"}, None, "core_node_id"),
        ({}, "relation_types", "relation_types"),
        ({"path_depth": 0}, None, "path_depth"),
        ({"path_depth": 1}, None, "path_depth"),
        ({"path_depth": 4}, None, "path_depth"),
        ({"path_depth": 5}, None, "path_depth"),
        ({"path_depth": int("9" * 65)}, None, "path_depth"),
        ({"path_depth": "abc!@#"}, None, "path_depth"),
        ({"min_strength": -0.1}, None, "min_strength"),
        ({"min_strength": 1.1}, None, "min_strength"),
        ({"min_strength": int("9" * 65)}, None, "min_strength"),
        ({"min_strength": "abc!@#"}, None, "min_strength"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_parameter_returns_http_422(
    async_client,
    overrides,
    removed_field,
    expected_field,
):
    payload = {**VALID_PAYLOAD, **overrides}
    if removed_field:
        payload.pop(removed_field)

    response = await async_client.post(ENDPOINT, json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["success"] is False
    assert body["msg"] == "接口参数校验错误"
    assert any(error["loc"][-1] == expected_field for error in body["data"])
