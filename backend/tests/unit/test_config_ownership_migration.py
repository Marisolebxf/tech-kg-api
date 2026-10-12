from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, select, text

from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.mysql_datasource import MysqlDatasource
from script.migrate_config_ownership import TARGET_BUSINESS, migrate


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    for model in (BusinessClient, LlmConfig, MysqlDatasource):
        model.__table__.create(engine)
    now = datetime.now()
    with engine.begin() as connection:
        connection.execute(
            BusinessClient.__table__.insert(),
            {"client_id": TARGET_BUSINESS, "name": "亿级知识图谱", "enabled": True},
        )
        for model, extra in (
            (LlmConfig, {"base_url": "secret-url", "api_key": "secret-key", "model": "test"}),
            (
                MysqlDatasource,
                {"host": "secret-host", "username": "secret-user", "password": "secret-password"},
            ),
        ):
            for id, name in (("private", "开发者测试"), ("public", "公共测试")):
                connection.execute(
                    model.__table__.insert(),
                    dict(
                        id=id,
                        name=name,
                        owner="legacy-owner",
                        created_at=now,
                        updated_at=now,
                        **extra,
                    ),
                )
    yield engine
    engine.dispose()


def test_check_is_readonly_and_secret_free(engine):
    report = migrate(engine)
    assert not report["errors"]
    assert not inspect(engine).has_table(ConfigOwnership.__tablename__)
    assert "secret-" not in str(report)
    assert report["plan"]["business_name"] == "亿级知识图谱"


def test_apply_is_idempotent_and_preserves_all_source_columns(engine):
    plan = migrate(engine)["plan"]
    with engine.connect() as connection:
        before = {
            m: connection.execute(select(m.__table__)).all() for m in (LlmConfig, MysqlDatasource)
        }
    assert migrate(engine, plan, apply=True)["inserted"] == 4
    assert migrate(engine, plan, apply=True)["inserted"] == 0
    with engine.connect() as connection:
        for model, rows in before.items():
            assert connection.execute(select(model.__table__)).all() == rows
        assert (
            connection.execute(
                select(ConfigOwnership.business_id).where(ConfigOwnership.config_id == "private")
            )
            .scalars()
            .all()
            == [TARGET_BUSINESS] * 2
        )


@pytest.mark.parametrize(
    "change", ["duplicate", "missing", "rename", "business", "default", "wrong_target"]
)
def test_invalid_full_plan_never_creates_table(engine, change):
    plan = deepcopy(migrate(engine)["plan"])
    if change == "duplicate":
        plan["records"].append(plan["records"][0])
    elif change == "missing":
        plan["records"][0]["config_id"] = "missing"
    elif change == "rename":
        plan["records"][0]["name"] = "changed"
    elif change == "business":
        plan["business_name"] = "wrong"
    elif change == "wrong_target":
        plan["records"][0]["business_id"] = "another-business"
    else:
        with engine.begin() as connection:
            connection.execute(
                LlmConfig.__table__.update()
                .where(LlmConfig.id == "private")
                .values(is_default=True)
            )
    assert migrate(engine, plan, apply=True)["errors"]
    assert not inspect(engine).has_table(ConfigOwnership.__tablename__)


def test_existing_different_ownership_is_never_overwritten(engine):
    plan = migrate(engine)["plan"]
    migrate(engine, plan, apply=True)
    with engine.begin() as connection:
        connection.execute(
            ConfigOwnership.__table__.update()
            .where(ConfigOwnership.config_id == "private")
            .values(business_id="another-business")
        )
    assert migrate(engine, plan, apply=True)["errors"]


def test_later_configuration_not_in_plan_is_not_backfilled(engine):
    plan = migrate(engine)["plan"]
    migrate(engine, plan, apply=True)
    with engine.begin() as connection:
        row = dict(
            connection.execute(select(LlmConfig.__table__).where(LlmConfig.id == "public"))
            .mappings()
            .one()
        )
        row.update(id="later", name="后来新建")
        connection.execute(LlmConfig.__table__.insert(), row)
        connection.execute(
            ConfigOwnership.__table__.insert(),
            {"config_kind": "llm", "config_id": "later", "business_id": "another-business"},
        )
    assert migrate(engine, plan, apply=True)["inserted"] == 0
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(ConfigOwnership.business_id).where(ConfigOwnership.config_id == "later")
            )
            == "another-business"
        )


def test_ambiguous_or_missing_special_name_rejected(engine):
    with engine.begin() as connection:
        connection.execute(LlmConfig.__table__.update().values(name="开发者测试"))
    with pytest.raises(ValueError, match="恰好一条"):
        migrate(engine)


def test_apply_requires_reviewed_plan(engine):
    with pytest.raises(ValueError, match="--plan"):
        migrate(engine, apply=True)


def test_schema_reference_report_includes_mysql_and_llm(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE kg_schema_definition (id VARCHAR(64), graph_space VARCHAR(64), llm_config_id VARCHAR(64))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE kg_schema_source (id VARCHAR(64), schema_id VARCHAR(64), datasource_id VARCHAR(64))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO kg_schema_definition VALUES ('schema-a','other-business-space','private')"
            )
        )
        connection.execute(
            text("INSERT INTO kg_schema_source VALUES ('source-a','schema-a','private')")
        )
    report = migrate(engine)["schema_references"]
    assert report["status"] == "review_required"
    assert {r["config_kind"] for r in report["references"]} == {"mysql", "llm"}
    assert {r["graph_space"] for r in report["references"]} == {"other-business-space"}


def test_schema_report_handles_missing_llm_column(engine):
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE kg_schema_definition (id VARCHAR(64), graph_space VARCHAR(64))")
        )
    report = migrate(engine)["schema_references"]
    assert report["status"] == "incomplete"
    assert "kg_schema_definition.llm_config_id" in report["missing"]
