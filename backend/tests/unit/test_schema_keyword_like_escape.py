"""Schema 目录搜索关键字的 LIKE 转义：%/_ 按字面匹配，不再变成通配符。

2026-10-15 问题：搜索栏输入 "%" 时 DAO 直接拼 f"%{keyword}%" → "%%%" 匹配全部行，
"_" 匹配任意单字——结果失真（“输入 % 需要转义”的由来）。转义后 % 只命中名字里
真含 % 的行。
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dao.schema_management import SchemaManagementDAO
from db_model.schema_management import GraphSchemaDefinition
from service.workflow_models import Base  # kg_schema_* 表挂在控制面 Base 上


def _make_dao() -> tuple[SchemaManagementDAO, Session]:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    dao = SchemaManagementDAO(session)

    def add(key: str, name: str, label: str) -> None:
        session.add(GraphSchemaDefinition(schema_key=key, kind="entity", name=name, label=label))

    add("widget", "Widget", "部件")
    add("percent100", "Percent100", "百分之%百")
    add("under_score", "UnderScore", "下划线_标签")
    session.commit()
    return dao, session


def _keys(dao: SchemaManagementDAO, keyword: str) -> list[str]:
    rows, _total = dao.list(kind=None, keyword=keyword, page=1, page_size=50)
    return sorted(r.schema_key for r in rows)


def test_percent_keyword_matches_only_literal_percent():
    dao, _ = _make_dao()
    # 未转义时 "%%%" 会把三行全部捞出
    assert _keys(dao, "%") == ["percent100"]


def test_underscore_keyword_matches_only_literal_underscore():
    dao, _ = _make_dao()
    assert _keys(dao, "_") == ["under_score"]


def test_plain_substring_still_matches_by_name_label_and_key():
    dao, _ = _make_dao()
    assert _keys(dao, "widget") == ["widget"]  # schema_key/name 命中
    assert _keys(dao, "部件") == ["widget"]  # label 命中
    assert _keys(dao, "不存在") == []


def test_mixed_wildcard_and_literal():
    dao, _ = _make_dao()
    # "件%"：字面上含「件%」的行——没有；未转义时会命中所有含「件」的行
    assert _keys(dao, "件%") == []
    assert _keys(dao, "%百") == ["percent100"]
