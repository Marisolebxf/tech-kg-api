"""全站缓存失效防回归：变更接口必须失效对应读缓存。

2026-09-20 Schema 目录缓存漏失效引发「删除后列表脏行」后，全库审计出的
同类问题统一修复：llm/embedding 配置、工作流任务更新、任务重试、图空间
创建、图算法类型缓存、NGQL 控制台写后读。本文件用源码级断言防再次遗漏
（与 test_schema_catalog_cache_invalidation.py 同一手法）。
"""

import importlib
import inspect

from service import graph_console as graph_console_module
from service.graph_algorithm import _algo_info_cache, clear_algo_info_cache
from service.platform_access import PlatformActor


def _source(module_path: str, name: str) -> str:
    obj = importlib.import_module(module_path)
    for part in name.split("."):
        obj = getattr(obj, part)
    return inspect.getsource(obj)


def test_llm_config_mutations_clear_cache():
    # create/update/delete/set-default 四条变更路由都要失效（def 之外 ≥ 4 处调用）
    from biz.handler import llm_config

    calls = inspect.getsource(llm_config).count("_config_cache_clear()")
    assert calls >= 5, "llm_config 变更路由必须调用 _config_cache_clear（1 处定义 + ≥4 处调用）"


def test_embedding_config_mutations_clear_cache():
    from biz.handler import embedding_config

    calls = inspect.getsource(embedding_config).count("_config_cache_clear()")
    assert calls >= 5, (
        "embedding_config 变更路由必须调用 _config_cache_clear（1 处定义 + ≥4 处调用）"
    )


def test_workflow_job_update_clears_jobs_cache():
    source = _source("biz.handler.workflow_system", "update_job")
    assert "_jobs_cache_clear()" in source, "PUT /jobs/{id} 更新任务后必须失效任务列表缓存"


def test_task_center_retry_invalidates_tasks_cache():
    source = _source("biz.handler.task_center", "retry_task")
    assert 'invalidate("task-center:tasks")' in source, "任务重试下发后必须失效任务列表缓存"


def test_graph_space_create_resets_all_spaces_cache():
    source = _source("service.graph_space", "GraphSpaceService.create_space")
    assert "_all_spaces_cached_at = 0.0" in source, (
        "创建图空间后必须重置 _all_spaces 的 30s 缓存，否则新空间在列表里最长 30s 不可见"
    )


def test_schema_ddl_changes_clear_algo_info_cache():
    # Schema 新建（_create）/删除（delete_schema）都会改类型清单，需清算法页缓存
    assert "clear_algo_info_cache" in _source(
        "service.schema_management", "SchemaManagementService._create"
    )
    assert "clear_algo_info_cache" in _source(
        "service.schema_management", "SchemaManagementService.delete_schema"
    )


def test_clear_algo_info_cache_empties_entries():
    _algo_info_cache["meta:dev2"] = (0.0, {"edgeTypes": []})
    clear_algo_info_cache()
    assert not _algo_info_cache


def test_console_write_clears_read_cache(monkeypatch):
    """控制台写语句执行成功后作废只读缓存：写完再查同一条 SELECT 不吃写前结果。"""
    actor = PlatformActor(
        user_id="u1", username="u1", display_name="u1", email="u@x", is_admin=True
    )
    executed: list[str] = []

    def fake_run(_actor, _space, statement: str) -> dict:
        executed.append(statement)
        return {"rows": len(executed)}

    monkeypatch.setattr(graph_console_module, "run_statement", fake_run)
    monkeypatch.setattr(graph_console_module, "_ngql_payload_cache", {})
    select = "MATCH (v:Expert) RETURN v LIMIT 1"
    insert = 'INSERT VERTEX Expert(name="x") VALUES "e1"'

    graph_console_module.run_statement_cached_payload(actor, "dev2", select)
    graph_console_module.run_statement_cached_payload(actor, "dev2", select)
    assert len(executed) == 1, "第二次相同 SELECT 应命中缓存，不再真实执行"
    assert len(graph_console_module._ngql_payload_cache) == 1

    graph_console_module.run_statement_cached_payload(actor, "dev2", insert)
    assert len(executed) == 2, "写语句不缓存，每次真实执行"
    assert not graph_console_module._ngql_payload_cache, "写语句执行后只读缓存应被整体作废"

    graph_console_module.run_statement_cached_payload(actor, "dev2", select)
    assert len(executed) == 3, "写后同一条 SELECT 应重新执行（不再命中写前缓存）"
