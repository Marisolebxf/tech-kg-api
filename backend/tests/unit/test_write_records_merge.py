"""write_records 实体写前合并（多来源同 VID 列级保留）的单测。

背景（2026-10-18 页面测试证伪旧假设）：Nebula 的 INSERT VERTEX 对已存在
顶点是**整标签覆盖**——未列出的列被重置成默认值，并非「列级 upsert 互不
覆盖」。多来源绑同一实体（如 Person=dwd_scholar+dwd_zh_author）或跨批重写
同一 vid 时，后写携带的子集列会把先写的列清掉。

修复语义（service/temporal_workflows.py::_merge_entity_rows）：
- 批内同 VID 多条按出现序累积（同列后者覆盖，先出现的列保留）；
- 写前 FETCH 图上已有属性，记录未携带的列保留图上值；
- create_time/update_time 不从图上保留（每次写入由平台兜底刷新）；
- 图上 NULL 值不进合并；记录已覆盖标签全部列时跳过 FETCH。
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest


class MergeFakeGraphClient:
    """按语句类型应答的假图客户端：DESCRIBE 给列清单、FETCH 给旧值。

    ``existing`` 是 vid -> 图上已有属性 dict；``props_as_json_str`` 为 True 时
    把 FETCH 的 properties(vertex) 序列化成 JSON 字符串（trs-graph 的一种
    返回形状）。写语句全部捕获进 write_stmts。
    """

    describe_cols: list[dict[str, str]] = []
    existing: dict[str, dict] = {}
    props_as_json_str = False
    instances: list[MergeFakeGraphClient] = []

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
        if query.startswith("DESCRIBE"):
            return SimpleNamespace(records=list(type(self).describe_cols))
        if query.startswith("FETCH PROP ON"):
            vids = re.findall(r'"([^"]+)"', query)
            rows = []
            for vid in vids:
                props = dict(type(self).existing.get(vid) or {})
                if type(self).props_as_json_str:
                    props = json.dumps(props, ensure_ascii=False)
                rows.append({"vid": vid, "props": props})
            return SimpleNamespace(records=rows)
        return SimpleNamespace(records=[])

    def execute_write(self, query, *args, **kwargs):
        self.write_stmts.append(query)
        return SimpleNamespace()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", MergeFakeGraphClient)
    MergeFakeGraphClient.instances = []
    MergeFakeGraphClient.describe_cols = []
    MergeFakeGraphClient.existing = {}
    MergeFakeGraphClient.props_as_json_str = False
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_PACE_EVERY", "0")
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_BATCH_ROWS", "64")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
    # per-VID 写锁关掉：本文件测合并语义本身，锁行为见
    # test_write_records_vid_lock（那里用假 Redis 逐项断言）
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")
    return MergeFakeGraphClient


def describe(cols: list[tuple[str, str]]) -> None:
    """给假客户端设置 DESCRIBE TAG 应答（列名, 类型；全部可空）。"""
    MergeFakeGraphClient.describe_cols = [
        {"Field": col, "Type": typ, "Null": "YES"} for col, typ in cols
    ]


PERSON_COLS = [
    ("id", "string"),
    ("name", "string"),
    ("name_zh", "string"),
    ("name_en", "string"),
    ("scholar_org", "string"),
    ("paper_nums", "int64"),
    ("h_index", "int64"),
    ("source_table", "string"),
    ("create_time", "string"),
    ("update_time", "string"),
]


def entity_request(records, name="Person"):
    return {
        "kind": "entity",
        "name": name,
        "activeProps": [
            "id",
            "name",
            "name_zh",
            "name_en",
            "scholar_org",
            "paper_nums",
            "h_index",
            "source_table",
            "create_time",
            "update_time",
        ],
        "records": records,
        "graph": {"space": "test_space"},
        "sourceTable": "dwd_t",
    }


def stmt_pairs():
    """解析唯一一条 INSERT 语句的 (列名 -> 值字面量) 映射（单 vid 场景）。"""
    assert MergeFakeGraphClient.instances, "活动未建图客户端"
    stmts = MergeFakeGraphClient.instances[-1].write_stmts
    assert len(stmts) == 1, f"预期 1 条语句，实际 {len(stmts)}: {stmts}"
    stmt = stmts[0]
    cols_part, values_part = stmt.split(") VALUES ", 1)
    cols = [c.strip().strip("`") for c in cols_part.split("(", 1)[1].split(",")]
    body = values_part.rsplit(")", 1)[0].split(":(", 1)[1]  # 剥掉 "vid":( 前缀
    values = re.findall(r'"(?:[^"\\]|\\.)*"|[^,]+', body)
    values = [v.strip() for v in values]
    assert len(cols) == len(values), (cols, values)
    return dict(zip(cols, values, strict=True))


class TestEntityMerge:
    async def test_cross_write_retains_earlier_source_columns(self, client):
        """第二次写（作者来源子集列）不得清掉第一次写（学者来源）的列。"""
        from service.temporal_workflows import write_records

        describe(PERSON_COLS)
        # 第一批：学者来源，带 scholar_org/paper_nums/h_index
        await write_records(
            entity_request(
                [
                    {
                        "id": "person_A1",
                        "props": {
                            "id": "person_A1",
                            "name_zh": "张守拙",
                            "scholar_org": "中科天玑科技有限公司",
                            "paper_nums": 46,
                            "h_index": 18,
                            "source_table": "dwd_scholar",
                        },
                    }
                ]
            )
        )
        first = stmt_pairs()
        assert first["scholar_org"] == '"中科天玑科技有限公司"'
        assert first["paper_nums"] == "46"

        # 第二批：作者来源只带姓名（图上已有第一批的属性）
        MergeFakeGraphClient.existing = {
            "person_A1": {
                "id": "person_A1",
                "name_zh": "张守拙",
                "scholar_org": "中科天玑科技有限公司",
                "paper_nums": 46,
                "h_index": 18,
                "source_table": "dwd_scholar",
            }
        }
        await write_records(
            entity_request(
                [
                    {
                        "id": "person_A1",
                        "props": {
                            "id": "person_A1",
                            "name_zh": "张守拙",
                            "name_en": "ZHANG Shouzhuo",
                            "source_table": "dwd_zh_author",
                        },
                    }
                ]
            )
        )
        second = stmt_pairs()
        # 未携带的学者列保留图上旧值
        assert second["scholar_org"] == '"中科天玑科技有限公司"'
        assert second["paper_nums"] == "46"
        assert second["h_index"] == "18"
        # 携带的列按本次写为准
        assert second["source_table"] == '"dwd_zh_author"'
        assert second["name_en"] == '"ZHANG Shouzhuo"'

    async def test_within_batch_accumulates_across_column_sets(self, client):
        """同一批内同 VID 多条不同列集：合并成一条并集语句（先出现的列保留）。"""
        from service.temporal_workflows import write_records

        describe(PERSON_COLS)
        result = await write_records(
            entity_request(
                [
                    {"id": "v", "props": {"id": "v", "scholar_org": "机构甲", "paper_nums": 7}},
                    {
                        "id": "v",
                        "props": {"id": "v", "name_zh": "后写姓名", "source_table": "dwd_b"},
                    },
                ]
            )
        )
        assert result == {"written": 1}
        pairs = stmt_pairs()
        assert pairs["scholar_org"] == '"机构甲"'  # 先出现的列保留
        assert pairs["paper_nums"] == "7"
        assert pairs["name_zh"] == '"后写姓名"'  # 共享/后写列最后写者胜
        assert pairs["source_table"] == '"dwd_b"'

    async def test_full_column_coverage_skips_fetch(self, client):
        """DESCRIBE 可知全列且记录已覆盖全部列：跳过 FETCH 省一次往返。"""
        from service.temporal_workflows import write_records

        MergeFakeGraphClient.describe_cols = [
            {"Field": c, "Type": "string", "Null": "YES"}
            for c in ("id", "name", "source_table", "create_time", "update_time")
        ]
        MergeFakeGraphClient.existing = {"v": {"name": "不该出现"}}
        await write_records(
            {
                "kind": "entity",
                "name": "Person",
                "activeProps": ["id", "name", "source_table", "create_time", "update_time"],
                "records": [
                    {
                        "id": "v",
                        "props": {
                            "id": "v",
                            "name": "全覆盖",
                            "source_table": "t",
                            "create_time": "2026-10-18 17:00:00",
                            "update_time": "2026-10-18 17:00:00",
                        },
                    }
                ],
                "graph": {"space": "s"},
                "sourceTable": "t",
            }
        )
        reads_list = MergeFakeGraphClient.instances[-1].read_stmts
        assert all(q.startswith("DESCRIBE") for q in reads_list), reads_list

    async def test_partial_coverage_fetches_existing(self, client):
        """记录缺列时必须 FETCH 旧值（合并的依据）。"""
        from service.temporal_workflows import write_records

        MergeFakeGraphClient.describe_cols = [
            {"Field": c, "Type": "string", "Null": "YES"}
            for c in ("id", "name", "extra", "source_table", "create_time", "update_time")
        ]
        MergeFakeGraphClient.existing = {"v": {"extra": "旧值"}}
        await write_records(
            {
                "kind": "entity",
                "name": "Person",
                "activeProps": [
                    "id",
                    "name",
                    "extra",
                    "source_table",
                    "create_time",
                    "update_time",
                ],
                "records": [{"id": "v", "props": {"id": "v", "name": "新"}}],
                "graph": {"space": "s"},
                "sourceTable": "t",
            }
        )
        reads_list = MergeFakeGraphClient.instances[-1].read_stmts
        assert any(q.startswith("FETCH PROP ON") for q in reads_list), reads_list
        assert stmt_pairs()["extra"] == '"旧值"'

    async def test_audit_columns_not_retained_from_graph(self, client):
        """create_time/update_time 不从图上保留，由平台每次兜底刷新。"""
        from service.temporal_workflows import write_records

        MergeFakeGraphClient.existing = {
            "v": {
                "create_time": "1999-01-01 00:00:00",
                "update_time": "1999-01-01 00:00:00",
                "extra": "留",
            }
        }
        MergeFakeGraphClient.describe_cols = [
            {"Field": c, "Type": "string", "Null": "YES"}
            for c in ("id", "name", "extra", "source_table", "create_time", "update_time")
        ]
        await write_records(
            {
                "kind": "entity",
                "name": "Person",
                "activeProps": [
                    "id",
                    "name",
                    "extra",
                    "source_table",
                    "create_time",
                    "update_time",
                ],
                "records": [{"id": "v", "props": {"id": "v", "name": "新"}}],
                "graph": {"space": "s"},
                "sourceTable": "t",
            }
        )
        stmt = MergeFakeGraphClient.instances[-1].write_stmts[0]
        assert "1999-01-01" not in stmt  # 旧时间戳不进语句
        pairs = stmt_pairs()
        assert pairs["extra"] == '"留"'
        assert pairs["create_time"] and pairs["create_time"] != "NULL"

    async def test_graph_null_values_dropped_and_json_string_props(self, client):
        """图上 NULL 不进合并；properties(vertex) 序列化成 JSON 字符串也能兜住。"""
        from service.temporal_workflows import write_records

        MergeFakeGraphClient.props_as_json_str = True
        describe(
            [
                ("id", "string"),
                ("name", "string"),
                ("extra", "string"),
                ("bio", "string"),
                ("paper_nums", "int64"),
                ("source_table", "string"),
                ("create_time", "string"),
                ("update_time", "string"),
            ]
        )
        MergeFakeGraphClient.existing = {"v": {"extra": "留", "bio": None, "paper_nums": 3}}
        await write_records(
            {
                "kind": "entity",
                "name": "Person",
                "activeProps": [
                    "id",
                    "name",
                    "extra",
                    "bio",
                    "paper_nums",
                    "source_table",
                    "create_time",
                    "update_time",
                ],
                "records": [{"id": "v", "props": {"id": "v", "name": "甲"}}],
                "graph": {"space": "s"},
                "sourceTable": "t",
            }
        )
        stmt = MergeFakeGraphClient.instances[-1].write_stmts[0]
        assert "`bio`" not in stmt  # NULL 列不显式写回
        pairs = stmt_pairs()
        assert pairs["extra"] == '"留"'
        assert pairs["paper_nums"] == "3"

    async def test_relation_path_unchanged_no_fetch(self, client):
        """关系路径不做合并、不发 FETCH（本次修复只动实体语义）。"""
        from service.temporal_workflows import write_records

        await write_records(
            {
                "kind": "relation",
                "name": "AUTHORED_BY",
                "activeProps": ["author_order", "source_table", "create_time", "update_time"],
                "records": [
                    {
                        "fromId": "p1",
                        "toId": "person_A1",
                        "props": {"author_order": "1", "source_table": "dwd_zh_author"},
                    }
                ],
                "graph": {"space": "s"},
                "sourceTable": "t",
            }
        )
        reads_list = MergeFakeGraphClient.instances[-1].read_stmts
        assert not any(q.startswith("FETCH PROP ON") for q in reads_list), reads_list
        stmt = MergeFakeGraphClient.instances[-1].write_stmts[0]
        assert stmt.startswith("INSERT EDGE `AUTHORED_BY`(")
