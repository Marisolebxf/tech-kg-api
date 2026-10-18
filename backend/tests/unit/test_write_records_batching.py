"""write_records 批量多行 INSERT 的单测（分组/去重/自愈/回退）。

批量写图语义等价性的关键点：
- 同属性列集一组拼一条多行语句；组内同目标（同 vid / 同 from->to）后者覆盖前者；
- 不同列集的组组间按「组内最后一条记录的原始序」排序；Nebula 的 INSERT VERTEX
  对已存在顶点是整标签覆盖（未列出列被重置），同 VID 跨列集的保留语义由
  _merge_entity_rows 承担（见 test_write_records_merge.py），分组只管语句形状；
- unknown column 整组剔列重试；行级错误回退逐条定位坏行。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from infra.graph_db.exceptions import GraphRequestError


class FakeGraphClient:
    """捕获 execute_write 语句的假图客户端；fail_predicate 命中即抛 400。

    活动函数内部自建实例，测试经类级 ``instances`` 登记表取最后一个实例断言。
    """

    fail_predicate = None
    instances: list[FakeGraphClient] = []

    def __init__(self, settings=None):
        self.settings = settings
        self.write_stmts: list[str] = []
        self.read_stmts: list[str] = []
        type(self).instances.append(self)

    def connect(self):
        pass

    def close(self):
        pass

    def execute_read(self, query, *args, **kwargs):
        self.read_stmts.append(query)
        return SimpleNamespace(records=[])

    def execute_write(self, query, *args, **kwargs):
        pred = type(self).fail_predicate
        if pred and pred(query):
            raise GraphRequestError("injected failure", status_code=400)
        self.write_stmts.append(query)
        return SimpleNamespace()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", FakeGraphClient)
    monkeypatch.setattr(FakeGraphClient, "fail_predicate", None)
    FakeGraphClient.instances = []
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_PACE_EVERY", "0")
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_BATCH_ROWS", "64")
    # 写前守卫关掉：本文件只测批量写图语句形状，终判/锁行为见
    # test_entity_write_guard
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
    return FakeGraphClient


def entity_request(records, name="Product"):
    return {
        "kind": "entity",
        "name": name,
        "activeProps": ["id", "name", "source_table", "create_time", "update_time"],
        "records": records,
        "graph": {"space": "test_space"},
        "sourceTable": "dwd_t",
    }


def edge_request(records, name="AUTHORED_BY"):
    return {
        "kind": "relation",
        "name": name,
        "activeProps": ["author_order", "source_table", "create_time", "update_time"],
        "records": records,
        "graph": {"space": "test_space"},
        "sourceTable": "dwd_t",
    }


def stmts() -> list[str]:
    assert FakeGraphClient.instances, "活动未建图客户端"
    return FakeGraphClient.instances[-1].write_stmts


class TestEntityBatching:
    async def test_same_prop_keys_one_multi_row_statement(self, client):
        from service.temporal_workflows import write_records

        records = [
            {"id": "v1", "props": {"id": "v1", "name": "甲"}},
            {"id": "v2", "props": {"id": "v2", "name": "乙"}},
            {"id": "v3", "props": {"id": "v3", "name": "丙"}},
        ]
        result = await write_records(entity_request(records))
        assert result == {"written": 3}
        statements = stmts()
        assert len(statements) == 1
        stmt = statements[0]
        assert stmt.startswith("INSERT VERTEX `Product`(")
        for vid in ("v1", "v2", "v3"):
            assert f'"{vid}":(' in stmt
        # 审计列由平台注入（activeProps 内）
        assert "`source_table`" in stmt and "`create_time`" in stmt

    async def test_different_prop_keys_grouped_order_by_last_record(self, client):
        from service.temporal_workflows import write_records

        request = entity_request(
            [
                {"id": "a", "props": {"id": "a", "name": "组员"}},
                {"id": "b", "props": {"id": "b", "name": "带额外列", "extra": "x"}},
                {"id": "c", "props": {"id": "c", "name": "组员"}},
            ]
        )
        request["activeProps"].append("extra")  # extra 列必须在白名单内才进得了语句
        result = await write_records(request)
        assert result == {"written": 3}
        statements = stmts()
        assert len(statements) == 2
        # 组间按「组内最后一条记录的原始序」排序：{id,name} 组最后是 c(idx2)，
        # 带 extra 的组最后是 b(idx1) → extra 组先写
        first, second = statements
        assert '"b":(' in first and "`extra`" in first
        assert '"a":(' in second and '"c":(' in second and '"b":(' not in second

    async def test_shared_column_final_value_matches_sequential(self, client):
        """同 vid 跨列集：先合并成一条（列级后者覆盖、先出现的列保留）再写。

        Nebula INSERT VERTEX 是整标签覆盖，两条子集语句会把先写的列清掉；
        合并后一条语句携带并集列，共享列（name）终值 = 逐条顺序写的最后写者。
        """
        from service.temporal_workflows import write_records

        records = [
            {"id": "v", "props": {"id": "v", "name": "早", "tagx": "x"}},
            {"id": "v", "props": {"id": "v", "name": "晚"}},
        ]
        request = entity_request(records)
        request["activeProps"].append("tagx")  # tagx 须在白名单内
        result = await write_records(request)
        assert result == {"written": 1}
        statements = stmts()
        assert len(statements) == 1
        stmt = statements[0]
        assert "`tagx`" in stmt and '"x"' in stmt  # 先出现的列保留
        assert "晚" in stmt and "早" not in stmt  # 共享列最后写者胜

    async def test_same_vid_dedupe_keeps_last(self, client):
        from service.temporal_workflows import write_records

        records = [
            {"id": "v1", "props": {"id": "v1", "name": "旧名"}},
            {"id": "v1", "props": {"id": "v1", "name": "新名"}},
        ]
        result = await write_records(entity_request(records))
        assert result == {"written": 1}
        stmt = stmts()[0]
        assert stmt.count('"v1":(') == 1
        assert "新名" in stmt and "旧名" not in stmt

    async def test_batch_rows_env_chunks_statements(self, client, monkeypatch):
        from service.temporal_workflows import write_records

        monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_BATCH_ROWS", "2")
        records = [{"id": f"v{i}", "props": {"id": f"v{i}", "name": f"名{i}"}} for i in range(5)]
        result = await write_records(entity_request(records))
        assert result == {"written": 5}
        statements = stmts()
        assert len(statements) == 3  # 2 + 2 + 1
        assert '"v0":(' in statements[0] and '"v2":(' not in statements[0]

    async def test_entity_empty_props_skipped(self, client):
        from service.temporal_workflows import write_records

        # activeProps 不含审计列 → 空属性实体按旧语义跳过
        request = entity_request(
            [{"id": "skip", "props": None}, {"id": "keep", "props": {"name": "有属性"}}]
        )
        request["activeProps"] = ["id", "name"]
        result = await write_records(request)
        assert result == {"written": 1}
        assert '"keep":(' in stmts()[0] and '"skip":(' not in stmts()[0]

    async def test_id_backfill_injected_when_missing(self, client):
        from service.temporal_workflows import write_records

        records = [{"id": "vid9", "props": {"name": "无id"}}]
        result = await write_records(entity_request(records))
        assert result == {"written": 1}
        stmt = stmts()[0]
        assert "`id`" in stmt and '"vid9"' in stmt


class TestEdgeBatching:
    async def test_edges_multi_row_statement(self, client):
        from service.temporal_workflows import write_records

        records = [
            {"fromId": "paper_1", "toId": "person_1", "props": {"author_order": "1"}},
            {"fromId": "paper_1", "toId": "person_2", "props": {"author_order": "2"}},
        ]
        result = await write_records(edge_request(records))
        assert result == {"written": 2}
        stmt = stmts()[0]
        assert stmt.startswith("INSERT EDGE `AUTHORED_BY`(")
        assert '"paper_1"->"person_1":(' in stmt
        assert '"paper_1"->"person_2":(' in stmt

    async def test_same_edge_target_dedupe_keeps_last(self, client):
        from service.temporal_workflows import write_records

        records = [
            {"fromId": "p", "toId": "q", "props": {"author_order": "1"}},
            {"fromId": "p", "toId": "q", "props": {"author_order": "9"}},
        ]
        result = await write_records(edge_request(records))
        assert result == {"written": 1}
        stmt = stmts()[0]
        assert stmt.count('"p"->"q":(') == 1
        assert '"9"' in stmt


class TestSelfHealAndFallback:
    async def test_unknown_column_healed_for_whole_group(self, client, monkeypatch):
        from service.temporal_workflows import write_records

        # 语句里含 extra 列 → 整条以 unknown column 文案被拒，剔列后重试成功
        orig_execute = FakeGraphClient.execute_write

        def execute_write(self, query, *args, **kwargs):
            if "`extra`" in query:
                raise GraphRequestError(
                    "POST /api/v1/query/write -> 400: Unknown column 'extra' in schema",
                    status_code=400,
                )
            return orig_execute(self, query, *args, **kwargs)

        monkeypatch.setattr(FakeGraphClient, "execute_write", execute_write)

        records = [
            {"id": "v1", "props": {"id": "v1", "name": "甲", "extra": "e1"}},
            {"id": "v2", "props": {"id": "v2", "name": "乙", "extra": "e2"}},
        ]
        result = await write_records(entity_request(records))
        assert result == {"written": 2}
        statements = stmts()
        assert len(statements) == 1  # 剔列重试成功，无逐条回退
        assert "`extra`" not in statements[0]
        assert "`name`" in statements[0]

    async def test_row_level_error_falls_back_to_per_record(self, client, monkeypatch):
        from service.temporal_workflows import write_records

        def execute_write(self, query, *args, **kwargs):
            if query.count(":(") > 1:  # 多行语句 → 行级错误
                raise GraphRequestError(
                    "POST /api/v1/query/write -> 400: data type does not meet the requirements",
                    status_code=400,
                )
            self.write_stmts.append(query)
            return SimpleNamespace()

        monkeypatch.setattr(FakeGraphClient, "execute_write", execute_write)

        records = [
            {"id": "v1", "props": {"id": "v1", "name": "甲"}},
            {"id": "v2", "props": {"id": "v2", "name": "乙"}},
            {"id": "v3", "props": {"id": "v3", "name": "丙"}},
        ]
        result = await write_records(entity_request(records))
        assert result == {"written": 3}
        statements = stmts()
        # 批量语句被拒后回退：三条单行语句全部落地
        assert len(statements) == 3
        assert all(s.count(":(") == 1 for s in statements)

    async def test_poison_row_still_raises(self, client, monkeypatch):
        from service.temporal_workflows import write_records

        def execute_write(self, query, *args, **kwargs):
            if '"v2"' in query:
                raise GraphRequestError(
                    "POST /api/v1/query/write -> 400: data type does not meet the requirements",
                    status_code=400,
                )
            self.write_stmts.append(query)
            return SimpleNamespace()

        monkeypatch.setattr(FakeGraphClient, "execute_write", execute_write)

        records = [
            {"id": "v1", "props": {"id": "v1", "name": "甲"}},
            {"id": "v2", "props": {"id": "v2", "name": "坏行"}},
        ]
        with pytest.raises(GraphRequestError):
            await write_records(entity_request(records))
        # 好行已在逐条回退中落地，坏行按原语义上抛
        assert len(stmts()) == 1 and '"v1":(' in stmts()[0]
