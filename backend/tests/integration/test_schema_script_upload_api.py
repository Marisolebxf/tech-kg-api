"""Schema 脚本上传/双信号 API 集成测试。

原「执行抽取」「历史回填」入口已随入口收敛删除（2026-10-16，触发统一走
图谱构建任务 POST /workflow-system/jobs），相关用例一并移除；本文件保留
脚本上传（@step 多步/旧 transform 拒绝）与属性变更 stale 双信号用例。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor, require_platform_maintainer
from infra.s3 import StoredObject
from infra.workflow_mysql import get_workflow_session
from main import app
from script.init_schema_management import initialize_schema_management
from service.platform_access import PlatformActor


class FakeS3Storage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.bucket = "test-schema-scripts"

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> StoredObject:
        self.objects[(self.bucket, object_key)] = data
        return StoredObject(bucket=self.bucket, object_key=object_key, etag="test-etag")

    def get_object(self, bucket: str, object_key: str):
        from io import BytesIO

        return BytesIO(self.objects[(bucket, object_key)])

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)


class _SafeLLM:
    """固定放行的假 LLM（fixture 默认；安全门行为专项测试内覆写）。"""

    def synthesize(self, prompt: str, max_tokens: int = 2048) -> str | None:
        return '{"safe": true, "issues": [], "summary": "安全"}'


class _FakeLLM:
    def __init__(self, response: str | None) -> None:
        self._response = response

    def synthesize(self, prompt: str, max_tokens: int = 2048) -> str | None:
        return self._response


def _actor(user_id: str, is_admin: bool) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        email=f"{user_id}@test",
        is_admin=is_admin,
    )


@pytest.fixture
def script_api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_schema_management(engine)
    storage = FakeS3Storage()
    monkeypatch.setenv("TRS_GRAPH_SPACE", "techkg")
    monkeypatch.setattr("service.schema_ddl.list_graph_spaces", lambda: ["techkg"])
    monkeypatch.setattr(
        "service.schema_management.run_schema_ddl",
        lambda *args, **kwargs: {
            "statement": "CREATE TAG",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_workflow_session] = override_session
    # These tests exercise the legacy schema owner gate below the menu-level gate.
    app.dependency_overrides[require_platform_maintainer] = lambda: None
    monkeypatch.setattr("service.schema_management.get_schema_s3_storage", lambda: storage)
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "false")
    monkeypatch.setattr("service.schema_management._validate_datasource_exists", lambda ds_id: None)
    # PUT 通道已全员过门：默认给一个"放行"的假 LLM，安全门行为专项测试内覆写。
    monkeypatch.setattr("service.schema_management.get_llm_client", lambda: _SafeLLM())

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = _actor(user_id, is_admin)
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("admin-1", True)
    yield engine, set_actor, storage
    app.dependency_overrides.pop(get_workflow_session, None)
    app.dependency_overrides.pop(require_platform_maintainer, None)
    app.dependency_overrides.pop(require_platform_actor, None)
    engine.dispose()


async def _create_entity(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/schema-management/schemas/entities",
        json={
            "schemaKey": "widget",
            "name": "Widget",
            "label": "部件",
            "description": "",
            "properties": [{"name": "widget_id", "dataType": "string", "required": True}],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _upload_script(client: AsyncClient, schema_id: str) -> None:
    response = await client.put(
        f"/api/v1/schema-management/schemas/{schema_id}/script",
        files={
            "script": (
                "widget.py",
                b"from kg_sdk import step\n\n\n@step\ndef emit_widget(payload):\n"
                b"    return {'entities': []}\n",
                "text/x-python",
            )
        },
    )
    assert response.status_code == 200


async def _detail(client: AsyncClient, schema_id: str) -> dict:
    response = await client.get(f"/api/v1/schema-management/schemas/{schema_id}")
    assert response.status_code == 200
    return response.json()["data"]


async def _add_property(client: AsyncClient, schema_id: str, name: str = "rank") -> None:
    response = await client.post(
        f"/api/v1/schema-management/schemas/{schema_id}/properties",
        json={"name": name, "dataType": "int64"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_script_stale_double_signal(script_api, monkeypatch: pytest.MonkeyPatch) -> None:
    """脚本双信号：属性变更后未更新脚本 → stale；重传脚本 → 消除。"""
    _, _set_actor, _storage = script_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop, graph_space=None: {
            "statement": "ALTER ...",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await _upload_script(client, entity["id"])

        script = (await _detail(client, entity["id"]))["script"]
        assert script["capturedRevision"] == 1
        assert script["stale"] is False
        assert script["lastRunStatus"] == "none"

        # 属性变更（property_revision+1）后未更新脚本 → stale
        await _add_property(client, entity["id"])
        script = (await _detail(client, entity["id"]))["script"]
        assert script["stale"] is True
        assert script["staleBehind"] == 1

        # 重传脚本 → captured_revision 刷新，警告消除
        await _upload_script(client, entity["id"])
        script = (await _detail(client, entity["id"]))["script"]
        assert script["stale"] is False
        assert script["capturedRevision"] == 2


STEPS_SCRIPT = (
    b"from kg_sdk import step\n"
    b"\n"
    b"\n"
    b"@step\n"
    b"def step_clean(payload):\n"
    b'    return {"cleaned": payload.get("rows", [])}\n'
    b"\n"
    b"\n"
    b"@step\n"
    b"def step_emit(payload):\n"
    b'    return {"entities": []}\n'
)


@pytest.mark.asyncio
async def test_upload_steps_script_stores_first_fn(script_api) -> None:
    """@step 多步脚本：上传 200，入口名存第一步 fn（展示参考；执行时 plan 重新解析）。"""
    _, _set_actor, _storage = script_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)

        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/script",
            files={"script": ("widget_steps.py", STEPS_SCRIPT, "text/x-python")},
        )
        assert response.status_code == 200
        script = (await _detail(client, entity["id"]))["script"]
        assert script["workflowFunctionName"] == "step_clean"
        assert script["stale"] is False


@pytest.mark.asyncio
async def test_upload_rejects_legacy_transform_script(script_api) -> None:
    """旧单步 transform 脚本上传即 400，中文报错引导迁移 @step。"""
    _, _set_actor, _storage = script_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/script",
            files={
                "script": (
                    "legacy.py",
                    b"def transform(payload):\n    return {}\n",
                    "text/x-python",
                )
            },
        )
        assert response.status_code == 400
        assert "已下线" in response.json()["detail"]


@pytest.mark.asyncio
async def test_put_upload_blocked_when_llm_unsafe_with_evidence(script_api, monkeypatch) -> None:
    """PUT 全员过门：真高危（有实证 os.system）照样被拒，理由透出。"""
    _, _set_actor, _storage = script_api
    monkeypatch.setattr(
        "service.schema_management.get_llm_client",
        lambda: _FakeLLM(
            '{"safe": false, "issues": [{"problem": "调用 os.system 执行系统命令",'
            ' "evidence": "os.system(\'rm -rf /\')"}], "summary": "危险脚本"}'
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/script",
            files={
                "script": (
                    "evil.py",
                    b"import os\n\nfrom kg_sdk import step\n\n\n@step\ndef run(payload):\n"
                    b"    os.system('rm -rf /')\n    return payload\n",
                    "text/x-python",
                )
            },
        )
        assert response.status_code == 400
        assert "未通过 LLM 安全校验" in response.json()["detail"]
        assert "os.system" in response.json()["detail"]
        # 拒绝后不应落任何脚本对象
        detail = await _detail(client, entity["id"])
        assert detail.get("script") is None


@pytest.mark.asyncio
async def test_put_upload_unavailable_when_llm_rate_limited(script_api, monkeypatch) -> None:
    """PUT 全员过门：LLM 限流（两次 None）→ 400 且文案是"稍后重传"，非"脚本不安全"。"""
    _, _set_actor, _storage = script_api
    monkeypatch.setattr("service.schema_management.get_llm_client", lambda: _FakeLLM(None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/script",
            files={
                "script": (
                    "widget.py",
                    b"from kg_sdk import step\n\n\n@step\ndef f(payload):\n    return payload\n",
                    "text/x-python",
                )
            },
        )
        assert response.status_code == 400
        assert "暂不可用" in response.json()["detail"]
        assert "不安全" not in response.json()["detail"]


@pytest.mark.asyncio
async def test_put_upload_rejected_when_llm_not_configured(script_api, monkeypatch) -> None:
    """PUT 全员过门：LLM 未配置（client 为 None）→ 400 提示配置 LLM_API_KEY。"""
    _, _set_actor, _storage = script_api
    monkeypatch.setattr("service.schema_management.get_llm_client", lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/script",
            files={
                "script": (
                    "widget.py",
                    b"from kg_sdk import step\n\n\n@step\ndef f(payload):\n    return payload\n",
                    "text/x-python",
                )
            },
        )
        assert response.status_code == 400
        assert "LLM_API_KEY" in response.json()["detail"]
