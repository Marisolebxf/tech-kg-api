"""目录缓存失效：所有变更方法必须调 _invalidate_list_cache。

2026-09-20 线上问题：delete_schema 未失效 60s 列表缓存（SCHEMA_LIST_CACHE_SECONDS），
删除关系后列表接口仍返回已删行，前端刷新拿到的还是脏数据，再点删除报
「Schema 不存在」。同类变更（增删属性/来源绑定/脚本保存）此前也漏失效。
"""

import inspect
from types import SimpleNamespace

from service import schema_management as schema_management_module
from service.schema_management import SchemaManagementService

MUTATING_METHODS = (
    "create_entity",
    "create_relation",
    "replace_script",
    "add_property",
    "delete_property",
    "replace_sources",
    "delete_schema",
    "verify_and_save_script",
)


def test_all_mutating_methods_invalidate_catalog_cache():
    """防回归：任何目录变更方法遗漏失效都会复现「删除/变更后列表脏行」。"""
    for name in MUTATING_METHODS:
        source = inspect.getsource(getattr(SchemaManagementService, name))
        assert "_invalidate_list_cache" in source, f"{name} 必须失效目录缓存"


def test_delete_schema_invalidates_list_cache(monkeypatch):
    invalidated: list[bool] = []
    monkeypatch.setattr(
        SchemaManagementService,
        "_invalidate_list_cache",
        classmethod(lambda cls: invalidated.append(True)),
    )
    definition = SimpleNamespace(
        id="sch-1",
        is_system=False,
        created_by="user-1",
        kind="relation",
        name="USES_TECH",
        graph_space="dev2",
        script=None,
    )
    service = object.__new__(SchemaManagementService)
    service._session = SimpleNamespace(commit=lambda: None)
    service._dao = SimpleNamespace(
        get=lambda _schema_id: definition,
        delete=lambda _definition: None,
        referenced_relation_names=lambda _schema_id: [],
    )
    monkeypatch.setattr(
        schema_management_module,
        "delete_schema_graph_data",
        lambda _kind, _name, _space: {
            "status": "succeeded",
            "verticesDeleted": 0,
            "edgesDeleted": 0,
        },
    )
    monkeypatch.setattr(
        schema_management_module, "find_running_extraction", lambda _definition: None
    )

    result = service.delete_schema("sch-1", "user-1")

    assert result["deleted"] is True
    assert invalidated == [True]
