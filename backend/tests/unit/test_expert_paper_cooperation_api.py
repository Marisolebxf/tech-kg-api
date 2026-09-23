import asyncio

import pytest

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service import expert_paper_cooperation_api
from service.expert_paper_cooperation_api import (
    _affiliation_text,
    _backfill_expert_org_from_mysql,
    _build_rules,
    _build_structured_result,
    _context_semaphore,
    _fetch_paper_context,
    _fetch_shared_paths,
    _paper_citations,
    _relation_confidences,
    _split_context_subgraph,
    _stable_team_note,
    _venue_level,
    _year_filters,
    clear_caches,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    """模拟 gkx_element_read_session()：按表名返回预置行，记录查询的表和 ID。"""

    def __init__(self, rows_by_table: dict):
        self._rows = rows_by_table
        self.queries = []

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, stmt, params):
        table = str(stmt).split(" FROM ")[1].split()[0]
        ids = next(iter(params.values()))
        self.queries.append((table, list(ids)))
        return _FakeResult(self._rows.get(table, []))


class FakeGraphSearchApi:
    def __init__(self):
        self.path_requests = []

    async def get_node(self, node_id: str, *, space: str):
        # 同时接受带/不带 person_ 前缀的 ID，兼容 dev/techkg 两种图空间
        normalized = node_id.removeprefix("person_")
        nodes = {
            "A": {
                "id": "person_A",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家甲",
                    "scholar_org": "甲单位",
                    "research_fields": "医学影像;人工智能",
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "source_record_id": "A",
                    "ingest_batch": "BATCH_PERSON",
                    "ingest_time": "2026-08-23 09:21:28",
                },
            },
            "B": {
                "id": "person_B",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家乙",
                    "scholar_org": "乙单位",
                    "research_fields": "医学影像;知识图谱",
                },
            },
        }
        return nodes[normalized]

    async def search_paths(self, body: dict):
        self.path_requests.append(body)
        edge_type = body["steps"][0]["edgeType"]
        # 无论文路径：AUTHORED（techkg）或 AUTHORED_BY（dev）均返回空
        if edge_type in ("AUTHORED", "AUTHORED_BY"):
            return {"items": [], "total": 0}
        if len(body["steps"]) == 1:
            return {
                "items": [
                    {
                        "nodes": [{"id": "person_A"}, {"id": "person_B"}],
                        "edges": [
                            {
                                "id": "person_A->person_B@0",
                                "type": "COAUTHOR_WITH",
                                "source": "person_A",
                                "target": "person_B",
                                "properties": {
                                    "co_paper_count": 35,
                                    "source_table": "dwd_scholar_coauthor",
                                    "source_record_id": "A_B",
                                    "ingest_batch": "BATCH_EDGE",
                                    "ingest_time": "2026-08-23 16:20:30",
                                },
                            }
                        ],
                    }
                ],
                "total": 1,
            }
        return {
            "items": [
                {
                    "nodes": [
                        {"id": "person_A"},
                        {
                            "id": "person_C",
                            "properties": {"name_zh": "共同作者丙"},
                        },
                        {"id": "person_B"},
                    ],
                    "edges": [
                        {"properties": {"co_paper_count": 12}},
                        {"properties": {"co_paper_count": 4}},
                    ],
                }
            ],
            "total": 1,
        }

    async def get_subgraph(self, *args, **kwargs):
        raise AssertionError("无逐篇论文路径时不应查询论文子图")


def test_request_schema_does_not_expose_data_source():
    schema = ExpertPaperCooperationDemoRequest.model_json_schema()

    assert "dataSource" not in schema["properties"]


@pytest.mark.parametrize(
    ("expert_a_id", "expert_b_id"),
    [
        ("专家甲", "专家乙"),
        ("person_A.1", "person_B-2"),
        ("专家·甲", "专家·乙"),
    ],
)
def test_expert_ids_accept_the_same_characters_as_colleague_relation(
    expert_a_id: str, expert_b_id: str
):
    body = ExpertPaperCooperationDemoRequest(
        expertAId=expert_a_id,
        expertBId=expert_b_id,
    )

    assert body.expertAId == expert_a_id
    assert body.expertBId == expert_b_id


@pytest.mark.parametrize("field", ["expertAId", "expertBId"])
@pytest.mark.parametrize("invalid_id", ["person A", "person@A", " person_A", "person_A\n"])
def test_expert_ids_reject_whitespace_and_abnormal_characters(field: str, invalid_id: str):
    payload = {"expertAId": "person_A", "expertBId": "person_B"}
    payload[field] = invalid_id

    with pytest.raises(ValueError, match="异常字符"):
        ExpertPaperCooperationDemoRequest(**payload)


def test_year_filters_use_string_publication_year():
    body = ExpertPaperCooperationDemoRequest(
        expertAId="A",
        expertBId="B",
        startTime="2021-01-01",
        endTime="2026-08-31",
    )

    assert _year_filters(body) == [
        {"property": "publication_year", "operator": "gte", "value": "2021"},
        {"property": "publication_year", "operator": "lte", "value": "2026"},
    ]


@pytest.mark.parametrize(
    ("props", "expected"),
    [
        # 1) Paper 节点自带 venue_level 时最高优先
        ({"venue_level": "CCF-A"}, "CCF-A"),
        ({"venue_level": "未分级", "jcr_zone": "Q1"}, "JCR-Q1"),
        # 2) 期刊分级体系按影响力排序
        ({"jcr_zone": "Q2"}, "JCR-Q2"),
        ({"scope_zone": "1区"}, "中科院-1区"),
        ({"sub_quartile": "2区"}, "分区-2区"),
        ({"top": "1"}, "Top期刊"),
        ({"is_sci": "1", "zh_core": "北大核心"}, "SCI"),
        # 3) 中文核心（未被 SCIE 收录的中文核心刊）排在 SCI 之后兜底
        ({"zh_core": "北大核心/CSSCI/CSCD"}, "北大核心/CSSCI/CSCD"),
        ({"zh_core": "EI/北大核心"}, "EI/北大核心"),
        ({"zh_core": "  "}, "未分级"),
        ({}, "未分级"),
    ],
)
def test_venue_level_prefers_grading_systems_in_order(props, expected):
    assert _venue_level({"id": "journal_1", "properties": props}) == expected


def test_rules_describe_the_actual_paper_cooperation_algorithm():
    rules = _build_rules(
        {
            "cooperationPaperCount": 6,
            "stableTeamMembers": ["共同作者丙"],
            "academicImpactScore": 57.8,
        }
    )

    assert [rule["name"] for rule in rules] == [
        "作者关联与合作频次算法",
        "论文指标与合作成员统计规则",
        "学术影响力与共同贡献计算规则",
        "论文合作关系置信度规则",
    ]
    assert "仅取" in rules[0]["logic"]
    assert "年份" in rules[0]["logic"]
    assert "未配置 status=1" in rules[0]["threshold"]
    assert "至少覆盖 2 个不同发表年份" in rules[1]["threshold"]
    assert "论文数×6.5" in rules[2]["logic"]
    assert "逐篇共同论文路径为 0.75" in rules[3]["logic"]
    assert "不使用前端固定值" in rules[3]["threshold"]


def test_relation_confidences_follow_structured_evidence_rules():
    confidences = _relation_confidences(
        paper_count=3,
        years=[2018, 2021, 2024],
        has_direct_paper_paths=True,
        unit_count=2,
        has_topic_edges=False,
        has_topic_fallback=False,
        venue_evidence_count=0,
        has_stable_team=True,
    )

    assert confidences == {
        "paperCooperation": 0.95,
        "authorship": 1.0,
        "authorUnit": 1.0,
        "researchTopic": 0.0,
        "publicationVenue": 0.0,
        "teamMembership": 1.0,
    }


def test_stable_team_note_explains_why_no_stable_team():
    """未构成稳定团队时按数据说明原因；构成时为空，不遮蔽正向结论。"""
    papers = [{"id": f"paper_{i}"} for i in range(1, 4)]
    assert (
        _stable_team_note(
            stable_members=["专家甲"],
            papers=papers,
            years=[2021, 2023],
            fallback_paper_count=0,
        )
        == ""
    )
    # 单年集中合作（两条规则门槛都只差“跨年”这一条）。
    assert (
        _stable_team_note(
            stable_members=[], papers=papers[:2], years=[2022, 2022], fallback_paper_count=0
        )
        == "共同论文 2 篇均发表于 2022 年，未跨年持续合作，不构成长期稳定团队"
    )
    # 共同论文不足 2 篇。
    assert (
        _stable_team_note(
            stable_members=[], papers=papers[:1], years=[2022], fallback_paper_count=0
        )
        == "共同论文仅 1 篇，未达长期稳定团队标准（需共同论文≥2篇且覆盖≥2个年份）"
    )
    # 时间范围内无共同论文。
    assert (
        _stable_team_note(stable_members=[], papers=[], years=[], fallback_paper_count=0)
        == "筛选时间范围内无共同论文，未形成合作团队"
    )


@pytest.mark.asyncio
async def test_provenance_records_query_time_sources():
    body = ExpertPaperCooperationDemoRequest(
        expertAId="A",
        expertBId="B",
    )

    graph_api = FakeGraphSearchApi()
    result = await _build_structured_result(graph_api, body)

    assert result["authorList"] == ["专家甲", "专家乙"]
    assert result["cooperationPaperCount"] == 35
    assert result["cooperationFrequency"] == 35
    shared_path_request = graph_api.path_requests[0]
    assert shared_path_request["sourceId"] == "person_A"
    assert shared_path_request["targetId"] == "person_B"
    assert shared_path_request["steps"][0]["direction"] == "in"
    assert shared_path_request["steps"][1]["direction"] == "out"
    assert result["paperTopics"][0] == "医学影像"
    assert result["coreCollaborators"] == ["共同作者丙", "专家乙", "专家甲"]
    assert result["stableTeamMembers"] == []
    # 聚合回退路径没有逐篇年份，说明须如实指出无法判定，而非“暂无数据”。
    assert result["stableTeamNote"] == (
        "共同论文仅聚合统计 35 篇，缺少逐篇发表年份，无法判定是否跨年持续合作"
    )
    assert result["cooperationTimeRange"]["displayText"] == ""
    assert result["journalLevelCount"] == {}
    assert result["conferenceLevelCount"] == {}
    assert result["citation"] == {"total": 0, "max": 0}
    assert result["relationConfidences"] == {
        "paperCooperation": 0.85,
        "authorship": 0.85,
        "authorUnit": 1.0,
        "researchTopic": 0.8,
        "publicationVenue": 0.0,
        "teamMembership": 0.85,
    }
    provenance = result["_provenance"]
    assert provenance["sourceDatabase"].startswith("trs-graph / space=")
    # 查到即记：带入图血缘的专家透传 MySQL 血缘。
    expert_evidence = next(
        item for item in provenance["evidences"] if item["graphVid"] == "person_A"
    )
    assert expert_evidence == {
        "title": "专家 · 专家甲",
        "sourceTable": "dwd_scholar",
        "sourceField": "scholar_id",
        "graphVid": "person_A",
        "summary": "入库批次：BATCH_PERSON；入库时间：2026-08-23 09:21:28",
    }
    # 无入图血缘的专家如实记录图库查询来源与识别属性，不再默认断言 dwd_scholar。
    expert_b_evidence = next(
        item for item in provenance["evidences"] if item["graphVid"] == "person_B"
    )
    assert expert_b_evidence["sourceTable"] == "trs-graph / space=dev"
    assert expert_b_evidence["sourceField"] == "name_zh"
    assert expert_b_evidence["summary"] == "节点未携带入图血缘，来源为本次图库查询"
    # 实体置信度：图节点按证据规则携带 confidence，实体 Tab 不再显示"暂无"。
    graph_nodes = {n["id"]: n for n in result["_graph"]["nodes"]}
    assert graph_nodes["person_A"]["data"]["confidence"] == pytest.approx(0.98)
    assert graph_nodes["person_A"]["data"]["confidenceSource"] == "derived"
    assert graph_nodes["person_A"]["data"]["confidenceBasis"]["rule"] == (
        "expert-entity-completeness-v1"
    )
    assert graph_nodes["person_B"]["data"]["confidence"] == pytest.approx(0.75)


class _ContextFakeApi:
    """上下文拉取桩：分别记录合并调用与单类型调用，回放可配置的合并子图。"""

    def __init__(self, merged: dict | None = None):
        self.merged_calls: list[tuple[tuple[str, ...], str]] = []
        self.subgraph_calls: list[tuple[str, str]] = []
        self._merged = merged or {"nodes": [], "edges": []}

    async def get_filtered_subgraph(self, node_id, *, edge_types, direction, space, limit=200):
        self.merged_calls.append((tuple(edge_types), direction))
        return self._merged

    async def get_subgraph(self, node_id, *, edge_type, direction, space, limit=200):
        self.subgraph_calls.append((edge_type, direction))
        return {"nodes": [{"id": node_id}], "edges": []}


@pytest.mark.asyncio
async def test_paper_context_merges_three_types_into_one_call():
    """作者/期刊/关键词合并为一次 filtered-subgraph 调用（方向 both），不再逐类型查。"""
    graph_api = _ContextFakeApi(
        merged={
            "nodes": [
                {"id": "paper_1"},
                {"id": "person_x", "properties": {"name_zh": "作者甲"}},
                {"id": "kw_1", "properties": {"keyword": "知识图谱"}},
            ],
            "edges": [
                {
                    "id": "paper_1->person_x@0",
                    "type": "AUTHORED_BY",
                    "source": "paper_1",
                    "target": "person_x",
                    "properties": {},
                },
                {
                    "id": "paper_1->kw_1@0",
                    "type": "HAS_KEYWORD",
                    "source": "paper_1",
                    "target": "kw_1",
                    "properties": {},
                },
            ],
        }
    )

    context = await _fetch_paper_context(
        graph_api,
        {"id": "paper_1", "properties": {}},
        space="dev",
        semaphore=asyncio.Semaphore(4),
    )

    # 一次合并调用覆盖三类上下文边；单类型调用只剩按需的 CITED_BY
    assert graph_api.merged_calls == [(("AUTHORED_BY", "PUBLISHED_IN", "HAS_KEYWORD"), "both")]
    assert graph_api.subgraph_calls == [("CITED_BY", "out")]  # 无预计算引用数 → 仍拉取
    # 合并结果按类型拆回：authored 带出作者、keywords 带出关键词、published 空
    assert [n["id"] for n in context["authored"]["nodes"]] == ["paper_1", "person_x"]
    assert [n["id"] for n in context["keywords"]["nodes"]] == ["paper_1", "kw_1"]
    assert context["published"]["nodes"] == [{"id": "paper_1"}]
    assert context["keywords"]["edges"][0]["type"] == "HAS_KEYWORD"


@pytest.mark.asyncio
async def test_paper_context_skips_cited_subgraph_when_citation_precomputed():
    """引用数有可信来源（citation_count / 作者边 citations）时不拉 CITED_BY，输出不变。"""

    async def run(paper: dict) -> tuple[_ContextFakeApi, dict]:
        graph_api = _ContextFakeApi()
        context = await _fetch_paper_context(
            graph_api, paper, space="dev", semaphore=asyncio.Semaphore(4)
        )
        return graph_api, context

    # 1) Paper 节点自带 citation_count
    graph_api, context = await run({"id": "paper_2", "properties": {"citation_count": 7}})
    assert graph_api.subgraph_calls == []  # 只剩合并调用，CITED_BY 跳过
    assert _paper_citations(context) == 7  # 引用数不受跳过影响

    # 2) 节点无 citation_count，但作者边带 citations
    graph_api, context = await run(
        {"id": "paper_3", "properties": {}, "pathEdges": [{"properties": {"citations": 5}}]}
    )
    assert graph_api.subgraph_calls == []
    assert _paper_citations(context) == 5

    # 3) 两级都缺 → 仍拉 CITED_BY（走第三级回退）
    graph_api, context = await run({"id": "paper_4", "properties": {}})
    assert graph_api.subgraph_calls == [("CITED_BY", "out")]


@pytest.mark.asyncio
async def test_paper_context_slash_vid_keeps_per_type_calls():
    """DOI 斜杠 VID 走不了 filtered-subgraph 单段路径，保持旧的逐类型调用。"""
    graph_api = _ContextFakeApi()

    context = await _fetch_paper_context(
        graph_api,
        {"id": "paper_ref_10.1111/jth.14768", "properties": {}},
        space="dev",
        semaphore=asyncio.Semaphore(4),
    )

    assert graph_api.merged_calls == []
    assert graph_api.subgraph_calls == [
        ("AUTHORED_BY", "out"),
        ("PUBLISHED_IN", "out"),
        ("HAS_KEYWORD", "out"),
        ("CITED_BY", "out"),
    ]
    assert context["keywords"]["nodes"] == [{"id": "paper_ref_10.1111/jth.14768"}]


def test_split_context_subgraph_filters_edges_by_original_direction():
    """合并子图按「原单类型调用的方向」拆分：反向边不进上下文、节点顺序保留。"""
    merged = {
        "nodes": [
            {"id": "p1"},
            {"id": "s1", "properties": {"name_zh": "作者"}},
            {"id": "j1", "properties": {"name_cn": "期刊"}},
            {"id": "k1", "properties": {"keyword": "主题"}},
        ],
        "edges": [
            # dev 口径：AUTHORED_BY 存储 Paper→Person，正方向（out）保留
            {"id": "p1->s1@0", "type": "AUTHORED_BY", "source": "p1", "target": "s1"},
            # 存储反向的 AUTHORED_BY（Person→Paper）：原 out 调用看不到，剔除
            {"id": "s2->p1@0", "type": "AUTHORED_BY", "source": "s2", "target": "p1"},
            {"id": "p1->j1@0", "type": "PUBLISHED_IN", "source": "p1", "target": "j1"},
            {"id": "j1->p1@0", "type": "PUBLISHED_IN", "source": "j1", "target": "p1"},
            {"id": "p1->k1@0", "type": "HAS_KEYWORD", "source": "p1", "target": "k1"},
        ],
    }

    split = _split_context_subgraph(merged, "p1")

    assert [n["id"] for n in split["authored"]["nodes"]] == ["p1", "s1"]
    assert [e["id"] for e in split["authored"]["edges"]] == ["p1->s1@0"]
    assert [n["id"] for n in split["published"]["nodes"]] == ["p1", "j1"]
    assert [e["id"] for e in split["published"]["edges"]] == ["p1->j1@0"]
    assert [n["id"] for n in split["keywords"]["nodes"]] == ["p1", "k1"]
    # 反向边对端 s2/j1 不进任何上下文（与逐类型方向调用口径一致）
    all_ids = {n["id"] for field in split.values() for n in field["nodes"]}
    assert "s2" not in all_ids


def test_context_semaphore_shared_within_loop_and_isolated_across_loops():
    """信号量按事件循环共享：服务进程单循环下全局一个；跨循环不复用（避免
    asyncio 原语绑定旧循环的 RuntimeError，测试每用例各建循环也能跑）。"""

    async def acquire_and_release():
        semaphore = _context_semaphore()
        async with semaphore:
            return semaphore

    first = asyncio.run(acquire_and_release())
    second = asyncio.run(acquire_and_release())
    assert first is not second  # 各循环独立实例，跨循环复用会 RuntimeError

    async def same_loop_twice():
        assert _context_semaphore() is _context_semaphore()

    asyncio.run(same_loop_twice())


@pytest.mark.asyncio
async def test_context_semaphore_caps_concurrency_across_callers(monkeypatch):
    """并发上限对多个调用方共享：两批上下文同时拉取时在飞数仍不超过上限。"""
    monkeypatch.setattr(expert_paper_cooperation_api, "_CONTEXT_CONCURRENCY", 3)
    semaphore = _context_semaphore()
    in_flight = 0
    peak = 0

    class _SlowApi:
        async def get_filtered_subgraph(self, node_id, *, space, **_):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {"nodes": [{"id": node_id}], "edges": []}

        async def get_subgraph(self, node_id, *, space, **_):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return {"nodes": [{"id": node_id}], "edges": []}

    papers = [{"id": f"paper_{i}", "properties": {"citation_count": 1}} for i in range(10)]
    # 两批调用方（对应两个并发请求）共用同一信号量
    await asyncio.gather(
        *[
            _fetch_paper_context(_SlowApi(), paper, space="dev", semaphore=semaphore)
            for paper in papers
        ],
        *[
            _fetch_paper_context(_SlowApi(), paper, space="dev", semaphore=semaphore)
            for paper in papers
        ],
    )

    assert peak <= 3  # 全局上限对两批调用方一起生效


def test_affiliation_text_takes_first_nonempty_from_json_array():
    assert _affiliation_text('["中国石油大学(华东)新能源学院"]') == "中国石油大学(华东)新能源学院"
    assert _affiliation_text('["", "备用单位"]') == "备用单位"
    assert _affiliation_text("纯文本单位") == "纯文本单位"
    assert _affiliation_text("[broken json") == "[broken json"
    assert _affiliation_text(None) == ""


def test_backfill_expert_org_fills_missing_org_only(monkeypatch):
    clear_caches()
    session = _FakeSession(
        {
            "dwd_zh_author": [
                ("author-b", '["中国石油大学(华东)新能源学院"]', None),
                ("author-c", None, "兜底学院"),
            ],
        }
    )
    monkeypatch.setattr(expert_paper_cooperation_api, "gkx_element_read_session", session)

    with_org = {"properties": {"scholar_org": "已有单位"}}
    orgless_b = {"properties": {"name_zh": "专家乙"}}
    orgless_c = {"properties": {"name_zh": "专家丙"}}
    orgless_d = {"properties": {"name_zh": "专家丁"}}

    _backfill_expert_org_from_mysql(
        [
            ("person_author-a", with_org),
            ("person_author-b", orgless_b),
            ("person_author-c", orgless_c),
            ("person_author-d", orgless_d),
        ]
    )

    # 图上已有机构属性的不动；缺失的按源表回填（affiliation 优先、institution 兜底）；
    # 源表查不到 author-d（dwd_en_author 也无行）时保持原样。
    assert with_org == {"properties": {"scholar_org": "已有单位"}}
    assert orgless_b["properties"]["scholar_org"] == "中国石油大学(华东)新能源学院"
    assert orgless_c["properties"]["scholar_org"] == "兜底学院"
    assert "scholar_org" not in orgless_d["properties"]
    assert session.queries[0] == (
        "dwd_zh_author",
        ["author-b", "author-c", "author-d"],
    )
    assert session.queries[1][0] == "dwd_en_author"


def test_backfill_expert_org_swallows_mysql_failure(monkeypatch):
    clear_caches()

    class _BoomSession:
        def __enter__(self):
            raise RuntimeError("mysql down")

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(expert_paper_cooperation_api, "gkx_element_read_session", _BoomSession())
    node = {"properties": {}}

    _backfill_expert_org_from_mysql([("person_author-x", node)])

    # MySQL 故障不影响主查询，也不把"未找到"写进缓存。
    assert "scholar_org" not in node["properties"]
    assert expert_paper_cooperation_api._author_org_cache == {}


class _OrglessGraphApi(FakeGraphSearchApi):
    """专家 B 的图节点不带任何机构属性，模拟论文 ETL 丢弃 affiliation 的情况。"""

    async def get_node(self, node_id: str, *, space: str):
        node = await super().get_node(node_id, space=space)
        if node["id"] == "person_B":
            props = dict(node["properties"])
            props.pop("scholar_org", None)
            node = {**node, "properties": props}
        return node


@pytest.mark.asyncio
async def test_structured_result_backfills_author_units_from_source_table(monkeypatch):
    clear_caches()
    session = _FakeSession({"dwd_zh_author": [("B", '["中国石油大学(华东)新能源学院"]', None)]})
    monkeypatch.setattr(expert_paper_cooperation_api, "gkx_element_read_session", session)

    body = ExpertPaperCooperationDemoRequest(expertAId="A", expertBId="B")
    result = await _build_structured_result(_OrglessGraphApi(), body)

    assert result["authorUnits"] == ["甲单位", "中国石油大学(华东)新能源学院"]
    graph_nodes = {n["id"]: n for n in result["_graph"]["nodes"]}
    assert graph_nodes["person_B"]["subtitle"] == "中国石油大学(华东)新能源学院"


class _PagedPathsApi:
    """按 offset 返回预置页数的假 paths/search 客户端，记录全部请求体。"""

    def __init__(self, full_pages: int, last_page_size: int, page_size: int = 200):
        self.full_pages = full_pages
        self.last_page_size = last_page_size
        self.page_size = page_size
        self.requests: list[dict] = []

    async def search_paths(self, body: dict):
        self.requests.append(body)
        page_index = body["offset"] // body["limit"]
        count = body["limit"] if page_index < self.full_pages else self.last_page_size
        items = [{"nodes": [{"id": f"paper_{body['offset'] + i}"}]} for i in range(count)]
        # countTotal=False 时服务端约定返回 -1（未统计）
        total = 0 if body.get("countTotal", True) else -1
        return {"items": items, "total": total}


async def test_fetch_shared_paths_counts_total_only_on_first_page():
    api = _PagedPathsApi(full_pages=1, last_page_size=50)

    items = await _fetch_shared_paths(
        api, ExpertPaperCooperationDemoRequest(expertAId="A", expertBId="B")
    )

    assert len(items) == 250  # 200 + 50：页不满即止
    assert [r["offset"] for r in api.requests] == [0, 200]
    assert api.requests[0]["countTotal"] is True
    assert api.requests[1]["countTotal"] is False


async def test_fetch_shared_paths_stops_on_empty_page():
    api = _PagedPathsApi(full_pages=0, last_page_size=0)

    items = await _fetch_shared_paths(
        api, ExpertPaperCooperationDemoRequest(expertAId="A", expertBId="B")
    )

    assert items == []
    assert len(api.requests) == 1


async def test_fetch_shared_pages_capped_at_max_shared_papers():
    api = _PagedPathsApi(full_pages=10, last_page_size=0)

    items = await _fetch_shared_paths(
        api, ExpertPaperCooperationDemoRequest(expertAId="A", expertBId="B")
    )

    # 每页 200 条、上限 1000：恰好 5 页封顶，不发第 6 页请求
    assert len(api.requests) == 5
    assert len(items) == 1000
