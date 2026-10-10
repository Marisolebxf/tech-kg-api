"""目录缓存失效：变更事务提交后清本地缓存并广播 Redis 版本号。

2026-09-20 线上问题：delete_schema 未失效 60s 列表缓存（SCHEMA_LIST_CACHE_SECONDS），
删除关系后列表接口仍返回已删行，前端刷新拿到的还是脏数据，再点删除报
「Schema 不存在」。2026-10-09 二次问题：失效改为挂在 session 的 after_commit
钩子上（提交前失效会被竞态读者把未提交旧数据重新算进缓存），并升 Redis
版本号让多 worker（uvicorn --workers 8）下其它进程立即失配——「绑定来源表
后离开再回来未回显」的根因。
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


def test_service_wires_commit_invalidation():
    """防回归：失效挂在 session 事件上，删掉 __init__ 里的监听注册即全线失效。"""
    source = inspect.getsource(SchemaManagementService.__init__)
    assert '"before_flush"' in source
    assert '"after_commit"' in source


def test_mutating_methods_commit_through_session():
    """变更必须经 session 提交落库——after_commit 钩子才有机会失效。

    直接调 self._session.commit()，或经 _create / _persist_script（内部提交）皆可；
    verify_and_save_script 走内部自建 Session 的 inner 服务，同样过钩子。
    """
    for name in MUTATING_METHODS:
        source = inspect.getsource(getattr(SchemaManagementService, name))
        assert (
            "self._session.commit()" in source
            or "_persist_script" in source
            or "self._create(" in source
        ), f"{name} 必须经 session 提交"


def test_note_schema_writes_marks_only_kg_schema_tables():
    service = object.__new__(SchemaManagementService)
    service._session = SimpleNamespace(
        new=[SimpleNamespace(**{"__table__": SimpleNamespace(name="kg_schema_definition")})],
        dirty=[],
        deleted=[SimpleNamespace(**{"__table__": SimpleNamespace(name="kg_other")})],
    )
    service._touched_schema_tables = False
    service._note_schema_writes()
    assert service._touched_schema_tables is True

    service._session = SimpleNamespace(
        new=[SimpleNamespace(**{"__table__": SimpleNamespace(name="kg_other")})],
        dirty=[],
        deleted=[],
    )
    service._touched_schema_tables = False
    service._note_schema_writes()
    assert service._touched_schema_tables is False


def test_commit_hook_clears_and_broadcasts(monkeypatch):
    bumps: list[bool] = []
    monkeypatch.setattr(
        schema_management_module, "_bump_shared_list_cache_version", lambda: bumps.append(True)
    )
    service = object.__new__(SchemaManagementService)
    service._session = SimpleNamespace()
    service._touched_schema_tables = True
    SchemaManagementService._list_cache.clear()
    SchemaManagementService._catalog_cache.clear()
    SchemaManagementService._list_cache[("sentinel",)] = (1.0, {})
    SchemaManagementService._catalog_cache["sentinel"] = (1.0, "{}", "0")

    service._invalidate_after_commit()

    assert SchemaManagementService._list_cache == {}
    assert SchemaManagementService._catalog_cache == {}
    assert bumps == [True]
    # 未动过目录表的提交（只读事务后的收尾 commit）不失效、不广播
    service._invalidate_after_commit()
    assert bumps == [True]


def test_list_cache_key_includes_shared_version(monkeypatch):
    """版本号变化（其它 worker 已变更）必须让本地缓存立即失配重算。"""
    queries: list[dict] = []

    def fake_list(**kwargs):
        queries.append(kwargs)
        return [], 0

    service = object.__new__(SchemaManagementService)
    service._session = SimpleNamespace()
    service._dao = SimpleNamespace(list=fake_list)
    monkeypatch.setattr(SchemaManagementService, "_list_cache_seconds", 60.0)
    SchemaManagementService._list_cache.clear()
    monkeypatch.setattr(schema_management_module, "_shared_list_cache_version", lambda: "1")

    kwargs = dict(kind=None, keyword=None, page=1, page_size=10, user_id=None)
    service.list_schemas(**kwargs)
    assert len(queries) == 1
    # 版本不变 → 命中缓存，不重算
    service.list_schemas(**kwargs)
    assert len(queries) == 1
    # 其它 worker 变更（版本号 +1）→ 立即失配重算
    monkeypatch.setattr(schema_management_module, "_shared_list_cache_version", lambda: "2")
    service.list_schemas(**kwargs)
    assert len(queries) == 2


def test_delete_schema_commits_through_session(monkeypatch):
    """delete_schema 全链路仍走 session 提交（钩子失效的前置条件）。"""
    commits: list[bool] = []
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
    service._session = SimpleNamespace(commit=lambda: commits.append(True))
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
    assert commits == [True]
