"""Schema 目录英文类型名 → 中文名映射表。

自动化登记脚本（register_platform_extraction / register_graph_schemas）创建
目录记录时，Nebula TAG/EDGE 本身没有中文名元数据，只能拿英文名顶 label，
导致 Schema 管理页两个子页第一列（实体中文名 / 关系中文名）显示英文。
本模块是共享映射表：登记脚本与存量回填脚本（backfill_schema_labels）共用，
映射缺失时回退英文名并告警——映射表可随时补，回填脚本幂等可重跑。

PRODUCT_LABELS 是产品口径的权威命名（0923 拍板：关系中文名 = 九大业务页面
「关系详情」列，实体名 = 页面实体类别），对 dev/dev2 已有目录行强制套用
（含 is_system=1 的种子行）；其余名字只回填 label=英文名 的行。
"""

from __future__ import annotations

# 产品口径权威命名：关系中文名取「关系详情」列，实体取页面实体类别名。
# （原文里「LEADS / HAS_PARTICIPANT → 项目合作关系」是页面聚合行，不单列）
PRODUCT_LABELS: dict[str, str] = {
    # ---- 关系（中文名 = 关系详情列）----
    "AUTHORED_BY": "论文署名关系",
    "COAUTHOR_WITH": "专家合著关系",
    "PUBLISHED_IN": "论文发表关系",
    "HAS_KEYWORD": "论文主题",
    "CITES": "论文引用关系",
    "CITED_BY": "论文被引关系",
    "LEADS": "项目负责人",
    "HAS_PARTICIPANT": "项目参加人",
    "FUNDED_BY": "项目资助方",
    "PARTICIPATES_IN": "项目参与机构",
    "INVENTED_BY": "专利发明人",
    "APPLIED_BY": "专利申请方",
    "AFFILIATED_WITH": "任职关系",
    "EXECUTIVE_OF": "高管任职关系",
    "LEGAL_REP_OF": "法定代表关系",
    "ACTUAL_CONTROLLER_OF": "实际控制关系",
    "BENEFICIAL_OWNER_OF": "最终受益关系",
    "SHAREHOLDER_OF": "股东持股关系",
    "INVOLVED_IN": "涉及风险事件关系",
    "BELONGS_TO_NODE": "企业归属产业链节点",
    "HAS_NODE": "产业链包含产业节点",
    "HAS_NEWS": "企业关联资讯",
    "EVENT_EXPERT": "事件关联专家",
    "CHILD_OF": "产业节点上下级",
    "DOWNSTREAM_OF": "产业上下游",
    "COVERS_CHAIN": "产业资讯报道产业链",
    "STUDIED_AT": "就读所属院校",
    "RELATED_TO": "论文关联",
    "PRODUCES": "企业生产产品",
    "LAYERED_BY_TECH": "产业链环节涉及关键技术",
    "LAYERED_BY_ENTERPRISE": "产业链节点关联企业",
    "LAYERED_BY_EXPERT": "链上机构关联专家",
    "LAYERED_BY_EVENT": "产业链关联动态事件",
    "COLLEAGUE": "同事",
    "ALUMNI": "校友",
    "EMPLOYED_BY": "企业任职关系",
    "MEMBER_OF_FAMILY": "家族成员关系",
    "OUTPUT_OF": "成果归属关系",
    "HAS_OUTPUT": "成果产出关系",
    # ---- 实体（页面实体类别名）----
    "Person": "科技专家",
    "Organization": "机构",
    "Paper": "论文",
    "Patent": "专利",
    "Project": "项目",
    "Report": "科技成果",
    "IndustryChain": "产业链",
    "IndustryNode": "产业链节点",
    "Event": "事件",
    "Keyword": "技术主题",
}

# 产品表未覆盖、但图库/目录里存在的类型：按业务语义命名，仅回填 label=英文名 的行
SCHEMA_LABELS: dict[str, str] = {
    **PRODUCT_LABELS,
    # ---- 实体 ----
    "BidNotice": "招标公告",
    "DataSource": "数据来源",
    "Gadget": "测试器件",
    "IntegrationTestPerson": "集成测试人物",
    "Journal": "期刊",
    "News": "新闻资讯",
    "organization_base": "机构基础信息",
    "PatentFamily": "专利同族",
    "Product": "产品",
    "Widget": "测试部件",
    # ---- 关系 ----
    "A": "测试关系A",
    "ACQUIRES": "收购",
    "BID_FOR": "投标",
    "IntegrationTestKnows": "集成测试关系",
    "INVESTS_IN": "投资关系",
    "OWNED_BY": "专利权利人",
    "REFERENCED_BY": "被参考",
    "SAME_AS": "同一实体",
    "SOURCED_FROM": "来源",
    "SUBSIDIARY_OF": "子公司关系",
}


def resolve_label(name: str) -> str:
    """取中文名；映射缺失回退英文名（调用方应告警提醒补映射）。"""
    return SCHEMA_LABELS.get(name, name)
