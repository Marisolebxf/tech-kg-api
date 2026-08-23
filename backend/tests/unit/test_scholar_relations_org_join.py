"""学者任职边(AFFILIATED_WITH)机构 VID 兜底策略单元测试。

防回归:scholar_org_id 缺失时必须走机构名 md5 桩 VID 兜底建边(coverage 优先),
禁止改回 name-join 跳过——后者会让 AFFILIATED_WITH 覆盖率≈0(见 ed1ffdb 回归)。
无 scholar_org_id 时还必须先建 md5 桩 Organization 顶点,否则 trs-graph 对指向
"不存在顶点"的边做遍历过滤,边虽存但业务读不到。真实机构对齐由
align_scholar_affiliations(Milvus 混合检索写 SAME_AS)后置处理。
"""

from __future__ import annotations

import hashlib

from script.load_scholar_relations import load_affiliations, org_vid
from script.scholar_provenance import CONFIDENCE_PLACEHOLDER_ORG


class _GraphStub:
    """记录 merge_edge / execute_write 调用,供断言 dst/props/建桩 sql。"""

    def __init__(self) -> None:
        self.edges: list[tuple[str, str, str, dict, dict]] = []
        self.writes: list[str] = []

    def merge_edge(self, src, dst, edge_type, identity, props) -> None:
        self.edges.append((src, dst, edge_type, identity, dict(props)))

    def execute_write(self, sql: str) -> None:
        self.writes.append(sql)


def test_org_vid_prefers_scholar_org_id() -> None:
    assert org_vid("o123", "某机构") == "org_o123"


def test_org_vid_falls_back_to_md5_stub_when_no_id() -> None:
    """scholar_org_id 缺失 → 机构名 md5[:16] 桩 VID(边照样建,顶点虚拟)。"""
    name = "新智认知数字科技股份有限公司"
    expected = "org_" + hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest()[:16]
    assert org_vid(None, name) == expected
    assert org_vid("  ", name) == expected  # 空白 id 视同缺失
    assert org_vid(None, "  ") is None  # 连机构名都没有才返回 None(调用方跳过)


def test_org_vid_lowercases_name_for_stable_stub() -> None:
    """同一机构名大小写不同应映射到同一桩 VID,避免重复桩顶点。"""
    assert org_vid(None, "Acme Inc") == org_vid(None, "acme inc")


def test_affiliation_uses_md5_stub_when_no_org_id(monkeypatch) -> None:
    """防回归:scholar_org_id 缺失时必须走 md5 桩兜底建边,不得跳过。

    ed1ffdb 曾把这里改成 name-join 跳过,导致 dwd_scholar 无 scholar_org_id 列时
    AFFILIATED_WITH 覆盖率从 ~全量 跌到个位数。本测试锁定桩兜底行为——部署时
    若再被改回跳过,该测试即失败,CI 拦截。
    """
    rows = [
        {
            "scholar_id": "s1",
            "scholar_org_id": None,
            "org_zh": "某科技公司",
            "org_en": "",
            "work_experience_date": "2019-01 至 2024-12",
            "work_experience_department_zh": "研发部",
            "work_experience_position_zh": "工程师",
        }
    ]
    monkeypatch.setattr("script.load_scholar_relations._iter_scholar_affiliations", lambda _: rows)
    graph = _GraphStub()
    # 不传 org_field_types → 不建桩顶点(建桩行为由下一测试覆盖)
    stats = load_affiliations(None, graph, dry_run=False)

    assert stats == {"written": 1, "skipped_no_org": 0, "placeholder_org": 1}
    src, dst, edge_type, _identity, props = graph.edges[0]
    assert src == "person_s1"
    assert edge_type == "AFFILIATED_WITH"
    # dst 是 md5 桩(非真实 org_id,也不是 None/跳过)
    assert dst == org_vid(None, "某科技公司")
    assert dst.startswith("org_") and len(dst) == len("org_") + 16
    assert props["affiliation_name"] == "某科技公司"
    assert props["work_experience_position_zh"] == "工程师"
    assert props["organization_id"] == ""  # 桩无 org_id
    assert props["confidence"] == CONFIDENCE_PLACEHOLDER_ORG
    assert graph.writes == []  # 无 org_field_types 不建桩


def test_affiliation_builds_stub_org_vertex_when_no_org_id(monkeypatch) -> None:
    """防回归:无 scholar_org_id 且传了 org_field_types 时,必须先建 md5 桩
    Organization 顶点再写边——否则 trs-graph 对指向"不存在顶点"的边做遍历过滤,
    边虽存但业务遍历读不到(覆盖率跌到 0)。建桩幂等:同机构名只建一次。
    """
    rows = [
        {"scholar_id": "s9", "scholar_org_id": None, "org_zh": "某集团", "org_en": ""},
        {"scholar_id": "s10", "scholar_org_id": None, "org_zh": "某集团", "org_en": ""},
        {"scholar_id": "s11", "scholar_org_id": None, "org_zh": "另一公司", "org_en": ""},
    ]
    monkeypatch.setattr("script.load_scholar_relations._iter_scholar_affiliations", lambda _: rows)
    graph = _GraphStub()
    org_field_types = {
        "name_cn": "string",
        "name_en": "string",
        "source_system": "string",
        "source_table": "string",
        "source_record_id": "string",
        "confidence": "double",
        "ingest_batch": "string",
        "ingest_time": "string",
        "organization_id": "string",
        "organization_base": "string",
    }
    stats = load_affiliations(None, graph, dry_run=False, org_field_types=org_field_types)

    assert stats == {"written": 3, "skipped_no_org": 0, "placeholder_org": 3}
    # 建 2 个 md5 桩顶点(某集团重复只建一次 + 另一公司)
    assert len(graph.writes) == 2
    for sql in graph.writes:
        assert "INSERT VERTEX Organization" in sql
    # 边 dst 都是 md5 桩
    for _src, dst, _et, _id, _props in graph.edges:
        assert dst.startswith("org_") and len(dst) == len("org_") + 16
    # s9/s10 同机构 → 同桩; s11 不同机构 → 不同桩
    assert graph.edges[0][1] == graph.edges[1][1]
    assert graph.edges[2][1] != graph.edges[0][1]


def test_affiliation_skips_only_when_no_org_name(monkeypatch) -> None:
    """只有连机构名都没有(既无 id 又无名)才跳过。"""
    rows = [{"scholar_id": "s2", "scholar_org_id": None, "org_zh": "", "org_en": ""}]
    monkeypatch.setattr("script.load_scholar_relations._iter_scholar_affiliations", lambda _: rows)
    graph = _GraphStub()
    stats = load_affiliations(None, graph, dry_run=False)
    assert stats == {"written": 0, "skipped_no_org": 1, "placeholder_org": 0}
    assert graph.edges == []
