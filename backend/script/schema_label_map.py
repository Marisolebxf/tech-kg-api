"""Schema 目录英文类型名 → 中文名映射表。

自动化登记脚本（register_platform_extraction / register_graph_schemas）创建
目录记录时，Nebula TAG/EDGE 本身没有中文名元数据，只能拿英文名顶 label，
导致 Schema 管理页两个子页第一列（实体中文名 / 关系中文名）显示英文。
本模块是共享映射表：登记脚本与存量回填脚本（backfill_schema_labels）共用，
映射缺失时回退英文名并告警——映射表可随时补，回填脚本幂等可重跑。

与种子目录（service/schema_catalog_seed.py）同名的类型沿用种子的中文名，
保证跨空间展示口径一致。
"""

from __future__ import annotations

# name 既覆盖实体 TAG 也覆盖关系 EDGE，两类命名空间无冲突（PascalCase vs UPPER_SNAKE）
SCHEMA_LABELS: dict[str, str] = {
    # ---- 实体 TAG ----
    "BidNotice": "招标公告",
    "DataSource": "数据来源",
    "Event": "事件",
    "Gadget": "测试器件",
    "IndustryChain": "产业链",
    "IndustryNode": "产业链节点",
    "IntegrationTestPerson": "集成测试人物",
    "Journal": "期刊",
    "Keyword": "关键词",
    "News": "新闻资讯",
    "Organization": "机构 / 企业",
    "organization_base": "机构基础信息",
    "Paper": "论文",
    "Patent": "专利",
    "PatentFamily": "专利同族",
    "Person": "人物",
    "Product": "产品",
    "Project": "项目",
    "Report": "报告",
    "Widget": "测试部件",
    # ---- 关系 EDGE ----（与种子目录同名的沿用种子中文名）
    "ACQUIRES": "收购",
    "ACTUAL_CONTROLLER_OF": "实际控制",
    "AFFILIATED_WITH": "作者发表时单位",
    "ALUMNI": "校友关系",
    "A": "测试关系A",
    "APPLIED_BY": "专利申请方",
    "AUTHORED_BY": "论文作者",
    "BELONGS_TO_NODE": "隶属产业链节点",
    "BENEFICIAL_OWNER_OF": "受益所有人",
    "CHILD_OF": "上级机构",
    "CITED_BY": "被引用",
    "CITES": "论文引用",
    "COAUTHOR_WITH": "合作作者",
    "COLLEAGUE": "同事关系",
    "COVERS_CHAIN": "覆盖产业链",
    "DOWNSTREAM_OF": "下游关系",
    "EXECUTIVE_OF": "高管任职",
    "FUNDED_BY": "项目受资助",
    "HAS_KEYWORD": "涉及关键词",
    "HAS_NEWS": "相关新闻",
    "HAS_NODE": "含产业链节点",
    "HAS_OUTPUT": "产出成果",
    "HAS_PARTICIPANT": "参与人员",
    "INVENTED_BY": "专利发明人",
    "INVESTS_IN": "投资关系",
    "INVOLVED_IN": "参与项目",
    "LEADS": "主持项目",
    "LEGAL_REP_OF": "法定代表人",
    "MEMBER_OF_FAMILY": "同族专利成员",
    "OWNED_BY": "专利权利人",
    "PRODUCES": "生产产品",
    "PUBLISHED_IN": "论文发表于",
    "REFERENCED_BY": "被参考",
    "RELATED_TO": "相关联",
    "SAME_AS": "同一实体",
    "SHAREHOLDER_OF": "股东关系",
    "STUDIED_AT": "就读于",
    "SUBSIDIARY_OF": "子公司关系",
}


def resolve_label(name: str) -> str:
    """取中文名；映射缺失回退英文名（调用方应告警提醒补映射）。"""
    return SCHEMA_LABELS.get(name, name)
