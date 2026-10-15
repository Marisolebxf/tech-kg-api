from dataclasses import replace
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db_model.base import Base
from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.llm_default import BusinessLlmDefault
from script.migrate_business_llm_defaults import check_defaults
from service.llm_config import LlmConfigService, resolve_llm_settings
from service.llm_defaults import decorate_defaults, resolve_default_config, set_default_for_actor
from service.platform_access import PlatformActor


def actor(business=None):
    return PlatformActor(
        user_id=business or "admin",
        username="test",
        display_name="test",
        email="",
        is_admin=business is None,
        business_id=business or "",
        business_role="developer",
    )


@pytest.fixture
def factory(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            BusinessClient.__table__,
            ConfigOwnership.__table__,
            LlmConfig.__table__,
            BusinessLlmDefault.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("infra.mysql.create_session", factory)
    with factory.begin() as session:
        session.add_all(
            [BusinessClient(client_id="a", name="A"), BusinessClient(client_id="b", name="B")]
        )
        for config_id, business in [("public1", None), ("public2", None), ("a1", "a"), ("b1", "b")]:
            session.add(
                LlmConfig(
                    id=config_id,
                    name=config_id,
                    base_url="http://test",
                    api_key="key",
                    model=config_id,
                    is_default=config_id == "public1",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
            session.add(
                ConfigOwnership(config_kind="llm", config_id=config_id, business_id=business)
            )
    yield factory
    engine.dispose()


def test_business_shared_and_public_fallback(factory):
    with factory() as s:
        assert resolve_default_config(s, "a").id == "public1"
        set_default_for_actor(s, actor("a"), "a1")
        assert resolve_default_config(s, "a").id == "a1"
        assert resolve_default_config(s, "b").id == "public1"
        set_default_for_actor(s, actor(), "public2")
        assert resolve_default_config(s, "a").id == "a1"
        assert resolve_default_config(s, "b").id == "public2"
        set_default_for_actor(s, replace(actor("a"), user_id="coworker"), "public1")
        assert resolve_default_config(s, "a").id == "public1"
        assert resolve_default_config(s).id == "public2"
    assert resolve_llm_settings("a")[2] == "public1"


def test_default_permission_and_disabled(factory):
    with factory() as s:
        for who, target in [(actor("a"), "b1"), (actor(), "a1")]:
            with pytest.raises(HTTPException) as error:
                set_default_for_actor(s, who, target)
            assert error.value.status_code == 403
            s.rollback()
        LlmConfigService(s).update_config("a1", {"status": "停用"})
        with pytest.raises(HTTPException):
            set_default_for_actor(s, actor("a"), "a1")


def test_abnormal_model_cannot_become_default(factory):
    """异常=探活事实：挂死的模型设为默认会让下游抽取全部失败，全部写路径 409 拦下。"""
    with factory() as s:
        service = LlmConfigService(s)
        service.update_config("a1", {"status": "异常"})
        s.get(LlmConfig, "public2").status = "异常"
        s.commit()
        for action in [
            lambda: set_default_for_actor(s, actor("a"), "a1"),  # 业务默认
            lambda: set_default_for_actor(s, actor(), "public2"),  # 公共默认
            lambda: service.update_config("public2", {"is_default": True}),
            lambda: service.set_default("public2"),
        ]:
            with pytest.raises(HTTPException) as error:
                action()
            assert error.value.status_code == 409
            s.rollback()
        # 新建时直发「异常 + 默认」同样被拦（带 Key 才会走到状态守卫）
        with pytest.raises(HTTPException) as error:
            service.create_config(
                {"name": "x", "base_url": "http://test", "model": "x", "api_key": "k",
                 "is_default": True, "status": "异常"}
            )
        assert error.value.status_code == 409
        s.rollback()
        # 恢复正常后即可设默认
        service.update_config("a1", {"status": "正常"})
        set_default_for_actor(s, actor("a"), "a1")


def test_default_reference_protects_other_business_public_model(factory):
    with factory() as s:
        set_default_for_actor(s, actor("a"), "public2")
        service = LlmConfigService(s)
        for action in [
            lambda: service.delete_config("public2"),
            lambda: service.update_config("public2", {"status": "停用"}),
        ]:
            with pytest.raises(HTTPException) as error:
                action()
            assert error.value.status_code == 409
            s.rollback()
        set_default_for_actor(s, actor("a"), "a1")
        assert service.delete_config("public2")


def test_invalid_business_selection_never_falls_back(factory):
    with factory() as s:
        set_default_for_actor(s, actor("a"), "a1")
        s.get(LlmConfig, "a1").status = "停用"
        s.commit()
        with pytest.raises(HTTPException):
            resolve_default_config(s, "a")
        assert resolve_default_config(s, "b").id == "public1"
        with pytest.raises(HTTPException):
            resolve_default_config(s, "a", "b1")


def test_public_default_conflict_migration(factory):
    with factory() as s:
        s.get(LlmConfig, "a1").is_default = True
        s.commit()
        assert len(check_defaults(s)["conflicts"]) == 2
        with pytest.raises(HTTPException):
            resolve_default_config(s, "b")


def test_create_update_cannot_promote_business_to_global(factory):
    with factory() as s:
        service = LlmConfigService(s)
        with pytest.raises(HTTPException):
            service.create_config(
                {
                    "name": "x",
                    "base_url": "http://test",
                    "model": "x",
                    "is_default": True,
                    "_business_id": "a",
                }
            )
        with pytest.raises(HTTPException):
            service.update_config("a1", {"is_default": True})
        created = service.create_config(
            {
                "name": "x",
                "base_url": "http://test",
                "model": "x",
                "api_key": "key",
                "is_default": True,
                "_business_id": None,
            }
        )
        assert resolve_default_config(s).id == created["id"]
        assert not s.get(LlmConfig, "public1").is_default


def test_decoration_uses_business_default_without_global_mutation(factory):
    with factory() as s:
        configs = [{"id": "public1", "visibility": "public", "status": "正常", "hasApiKey": True}]
        inherited = decorate_defaults(s, actor("a"), configs)[0]
        assert (
            inherited["isDefault"]
            and inherited["defaultSource"] == "public"
            and inherited["canSetDefault"]
        )
        set_default_for_actor(s, actor("a"), "public1")
        own = decorate_defaults(s, actor("a"), configs)[0]
        assert own["isDefault"] and own["defaultSource"] == "business"


def test_default_remains_in_list_after_thousand_other_records(factory):
    with factory() as s:
        set_default_for_actor(s, actor("a"), "a1")
        for index in range(1001):
            s.add(
                LlmConfig(
                    id=f"other-{index}",
                    name="other",
                    base_url="http://test",
                    api_key="key",
                    model="other",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
            s.add(ConfigOwnership(config_kind="llm", config_id=f"other-{index}", business_id="b"))
        s.commit()
        from service.config_ownership import visible_configurations

        rows = visible_configurations(s, actor("a"), "llm", LlmConfigService(s).list_configs())
        assert "a1" in {item["id"] for item in rows}
        assert not any(item["id"].startswith("other-") for item in rows)


def test_all_global_default_write_paths_require_key(factory):
    with factory() as s:
        service = LlmConfigService(s)
        with pytest.raises(HTTPException):
            service.create_config(
                {"name": "x", "base_url": "http://test", "model": "x", "is_default": True}
            )
        s.get(LlmConfig, "public2").api_key = ""
        s.commit()
        with pytest.raises(HTTPException):
            service.update_config("public2", {"is_default": True})
        with pytest.raises(HTTPException):
            set_default_for_actor(s, actor(), "public2")


@pytest.mark.parametrize("invalid", ["missing", "foreign", "disabled", "key", "business"])
def test_migration_rejects_invalid_existing_business_default(factory, invalid):
    with factory() as s:
        set_default_for_actor(s, actor("a"), "a1")
        if invalid == "missing":
            s.get(BusinessLlmDefault, "a").config_id = "missing"
        elif invalid == "foreign":
            s.get(BusinessLlmDefault, "a").config_id = "b1"
        elif invalid == "disabled":
            s.get(LlmConfig, "a1").status = "停用"
        elif invalid == "key":
            s.get(LlmConfig, "a1").api_key = ""
        else:
            s.get(BusinessClient, "a").enabled = False
        s.commit()
        report = check_defaults(s)
        assert len(report["conflicts"]) == 1
        assert report["conflicts"][0]["businessId"] == "a"
