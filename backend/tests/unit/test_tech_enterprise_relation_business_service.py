"""重点关注科技企业关系业务编排服务的单元测试。

用假的 httpx.AsyncClient 返回一个 subgraph(depth=2) mock，验证从点边解析出 governance +
project_cooperation 关系、角色定位、合作时间解析、重点企业筛选。
"""

from __future__ import annotations

import pytest

from biz.schemas.tech_enterprise_relation_business import KeyEnterpriseRelationRequest
from service.tech_enterprise_relation_business import KeyEnterpriseRelationService

EXPERT = "person_left_jing"


def _subgraph() -> dict:
    """构造一个 2 跳子图 mock：专家 --EXECUTIVE_BY--> 上市企业；专家 --HAS_PARTICIPANT--> 项目 --PARTICIPATES_IN--> 高校。"""
    nodes = [
        {"id": EXPERT, "labels": ["Person"], "properties": {"name_cn": "左晶"}},
        {
            "id": "org_lvdie",
            "labels": ["Organization"],
            "properties": {
                "name_cn": "苏州绿的谐波传动科技股份有限公司",
                "listing_status": "已上市",
                "stock_type": "中国_沪市A股_科创板",
                "stock_code": "688017.SH",
            },
        },
        {
            "id": "proj_1",
            "labels": ["Project"],
            "properties": {"research_period": "2020-01-01 至 2023-12-31"},
        },
        {"id": "org_pku", "labels": ["Organization"], "properties": {"name_cn": "北京大学"}},
    ]
    edges = [
        {
            "id": "e1",
            "type": "EXECUTIVE_OF",
            "source": EXPERT,
            "target": "org_lvdie",
            "properties": {"position": "副董事长"},
        },
        {
            "id": "e2",
            "type": "HAS_PARTICIPANT",
            "source": "proj_1",
            "target": EXPERT,
            "properties": {},
        },
        {
            "id": "e3",
            "type": "PARTICIPATES_IN",
            "source": "org_pku",
            "target": "proj_1",
            "properties": {},
        },
    ]
    return {"data": {"nodes": nodes, "edges": edges}}


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, routes: list[tuple[str, dict]]) -> None:
        self._routes = routes

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str, params: dict | None = None, timeout: float = 0) -> _FakeResponse:
        for key, payload in self._routes:
            if key in url:
                return _FakeResponse(payload)
        return _FakeResponse({"data": {"nodes": [], "edges": []}})


def _httpx():
    import service.tech_enterprise_relation_business as mod

    return mod.httpx


@pytest.mark.asyncio
async def test_run_parses_governance_and_project_cooperation(monkeypatch):
    svc = KeyEnterpriseRelationService(base_url="http://x")
    monkeypatch.setattr(
        _httpx(),
        "AsyncClient",
        lambda: _FakeAsyncClient([("/graph-search/filtered-subgraph/", _subgraph())]),
    )

    # 默认重点企业筛选：只保留苏州绿的（governance），北京大学（高校）被筛掉
    resp = await svc.run(KeyEnterpriseRelationRequest(expert_id=EXPERT))
    assert resp.expert_name == "左晶"
    assert len(resp.relations) == 1
    rel = resp.relations[0]
    assert rel.cooperation_type == "governance"
    assert rel.enterprise_name == "苏州绿的谐波传动科技股份有限公司"
    assert rel.cooperation_mode == "高管任职"
    assert rel.role_label == "副董事长"
    assert rel.role_level == "L1"
    assert rel.enterprise_background["stock_type"] == "中国_沪市A股_科创板"
    assert resp.enterprises == 1
    # 首要企业风险探测：mock 无 INVOLVED_IN 风险边 → 兜底文案
    assert rel.risk_summary == "暂无风险事件记录"
    # 置信度：governance → 0.9；响应综合 = max(relations) = 0.9
    assert rel.confidence == 0.9
    assert resp.confidence == 0.9


def test_key_tech_enterprise_only_coerces_string_bool():
    """前端参数框可能传 '是'/'否'/'true'/'false' 字符串，schema 应宽容转 bool。"""
    from biz.schemas.tech_enterprise_relation_business import KeyEnterpriseRelationRequest

    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="是"
        ).key_tech_enterprise_only
        is True
    )
    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="true"
        ).key_tech_enterprise_only
        is True
    )
    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="1"
        ).key_tech_enterprise_only
        is True
    )
    assert KeyEnterpriseRelationRequest(expert_id="x").key_tech_enterprise_only is True  # 默认
    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="否"
        ).key_tech_enterprise_only
        is False
    )
    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="false"
        ).key_tech_enterprise_only
        is False
    )
    assert (
        KeyEnterpriseRelationRequest(
            expert_id="x", key_tech_enterprise_only="0"
        ).key_tech_enterprise_only
        is False
    )


def test_enterprise_background_extracts_from_extra_json():
    """周威 ETL 把 base_info/product 表数据塞进 extra_json，_enterprise_background 应摊平提取。"""
    from service.tech_enterprise_relation_business import _enterprise_background

    props = {
        "name_cn": "苏州绿的谐波传动科技股份有限公司",
        "listing_status": "已上市",
        "stock_code": "688017.SH",
        "stock_type": "中国_沪市A股_科创板",
        "source_table": "dwd_org_stock_base",
        "extra_json": (
            '{"existing_payload": {"registered_capital_value": 183330125.0, '
            '"incorporation_year": 2011, "province": "江苏省", "city": "苏州市", '
            '"lerep": "左昱昱", "industry_l1_name": null, "industry": null}, '
            '"source_records": {"dwd_org_org_product_info:x": {"main_prod": "谐波减速器,人形机器人关节"}}}'
        ),
    }
    bg = _enterprise_background(props)
    assert bg["main_products"] == "谐波减速器,人形机器人关节"
    assert bg["registered_capital_value"] == 183330125.0
    assert bg["incorporation_year"] == 2011
    assert bg["legal_rep"] == "左昱昱"
    assert bg["province"] == "江苏省"
    assert bg["listing_status"] == "已上市"
    # industry_l1_name 源表为 null → 不应出现
    assert "industry_l1_name" not in bg


@pytest.mark.asyncio
async def test_primary_enterprise_risk_probe(monkeypatch):
    """首要企业有 INVOLVED_IN 风险事件时，risk_summary 含风险类型。"""
    risk_sub = {
        "data": {
            "nodes": [
                {"id": "org_lvdie", "labels": ["Organization"], "properties": {}},
                {
                    "id": "ev_zx",
                    "labels": ["Event"],
                    "properties": {"event_type": "zhixing"},
                },
                {
                    "id": "ev_bk",
                    "labels": ["Event"],
                    "properties": {"event_type": "bankruptcy"},
                },
            ],
            "edges": [
                {"type": "INVOLVED_IN", "source": "org_lvdie", "target": "ev_zx", "properties": {}},
                {"type": "INVOLVED_IN", "source": "org_lvdie", "target": "ev_bk", "properties": {}},
            ],
        }
    }
    # org 专属路由放前面（FakeAsyncClient 按 key 子串先匹配先返回）
    routes = [
        ("/graph-search/filtered-subgraph/org_lvdie", risk_sub),
        ("/graph-search/filtered-subgraph/", _subgraph()),
    ]
    svc = KeyEnterpriseRelationService(base_url="http://x")
    monkeypatch.setattr(_httpx(), "AsyncClient", lambda: _FakeAsyncClient(routes))

    resp = await svc.run(KeyEnterpriseRelationRequest(expert_id=EXPERT))
    rel = resp.relations[0]
    assert rel.enterprise_id == "org_lvdie"
    assert "2 条风险事件" in rel.risk_summary
    assert "bankruptcy" in rel.risk_summary
    assert "zhixing" in rel.risk_summary


@pytest.mark.asyncio
async def test_project_cooperation_period_and_university_filter(monkeypatch):
    svc = KeyEnterpriseRelationService(base_url="http://x")
    monkeypatch.setattr(
        _httpx(),
        "AsyncClient",
        lambda: _FakeAsyncClient([("/graph-search/filtered-subgraph/", _subgraph())]),
    )

    # 关掉重点企业筛选：北京大学（项目合作）保留，且带合作时间
    resp = await svc.run(
        KeyEnterpriseRelationRequest(expert_id=EXPERT, key_tech_enterprise_only=False)
    )
    by_type = {r.cooperation_type: r for r in resp.relations}
    assert "project_cooperation" in by_type
    proj = by_type["project_cooperation"]
    assert proj.enterprise_name == "北京大学"
    assert proj.period.start == "2020-01-01"
    assert proj.period.end == "2023-12-31"
    assert proj.source.startswith("project:")
