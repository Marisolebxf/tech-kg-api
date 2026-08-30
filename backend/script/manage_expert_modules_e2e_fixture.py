"""两个专家模块的端到端测试数据闭环（MySQL gkx_element -> TRSGraph）。

覆盖模块：
1. 科技专家两点合作成果
2. 科技专家校友关系

安全约束：默认只输出计划；只有 ``--apply`` 才写库；``--cleanup`` 必须同时提供
``--confirm-cleanup EXPERT_MODULES_E2E_V1``。脚本仅允许
``MYSQL_DATABASE=gkx_element`` 且 ``TRS_GRAPH_SPACE`` 为 ``dev`` 或 ``test``。

ID 形态对齐真实库（学者 8 位、论文整数、项目 UUID、专利 CN…B），但使用预留号段；
清理不依赖名称前缀，按本脚本定义的白名单删除（并兼容清理旧版 ``expert_e2e_v1_`` 数据）。

用法（本文件仅提供脚本，不会自动执行）：

    uv run python script/manage_expert_modules_e2e_fixture.py
    TRS_GRAPH_SPACE=test uv run python script/manage_expert_modules_e2e_fixture.py --apply
    TRS_GRAPH_SPACE=test uv run python script/manage_expert_modules_e2e_fixture.py --verify
    uv run python script/manage_expert_modules_e2e_fixture.py \
      --cleanup --confirm-cleanup EXPERT_MODULES_E2E_V1

姓名和成果名称均为自然、可读的测试名称；人物及其履历为虚构，不对应真实个人。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from infra.graph_db import close_trs_graph_client, get_trs_graph_client
from infra.mysql import MySQLClient

BATCH = "EXPERT_MODULES_E2E_V1"
# 预留号段：形态像真，与现网抽样不冲突；清理靠白名单 + BATCH 确认。
PAPER_ID_BASE = 889900000  # paper ids: 889900001 .. 889900080
EXPECTED_PERSONS = 100
EXPECTED_ACHIEVEMENTS = 100
# 旧版 ID（expert_e2e_v1_* / 9930…），apply/cleanup 时一并清除以免残留。
LEGACY_PREFIX = "expert_e2e_v1_"
LEGACY_PAPER_ID_BASE = 9930000000000000


@dataclass(frozen=True)
class Person:
    no: int
    name: str
    school_zh: str | None
    school_en: str | None
    degree_zh: str | None
    degree_en: str | None
    education_date: str | None

    @property
    def scholar_id(self) -> str:
        # 对齐 dwd_scholar.scholar_id：8 位字母数字，如 007Rb117 → 9F9A0001
        return f"9F9A{self.no:04d}"

    @property
    def vid(self) -> str:
        return f"person_{self.scholar_id}"


@dataclass(frozen=True)
class Paper:
    no: int
    title: str
    title_en: str
    year: int | None
    authors: tuple[int, ...]
    fields: tuple[str, ...] = ()
    awards: tuple[str, ...] = ()

    @property
    def mysql_id(self) -> int:
        return PAPER_ID_BASE + self.no

    @property
    def vid(self) -> str:
        # 与正式论文加载器 paper_vid(paper_id) 保持一致。
        return f"paper_{self.mysql_id}"


@dataclass(frozen=True)
class Project:
    no: int
    title: str
    year: int
    host: int
    participants: tuple[int, ...]
    fields: tuple[str, ...]
    awards: tuple[str, ...] = ()

    @property
    def mysql_id(self) -> str:
        # 对齐 dwd_zh_project.id：UUID
        return f"9f9a0001-0000-4000-a000-{self.no:012d}"

    @property
    def vid(self) -> str:
        return f"project_{self.mysql_id}"


@dataclass(frozen=True)
class Patent:
    no: int
    title: str
    title_en: str
    year: int
    inventors: tuple[int, ...]
    fields: tuple[str, ...]

    @property
    def patent_id(self) -> str:
        # 对齐 dwd_patent.patent_id：CN + 数字 + 后缀字母，如 CN103073024B
        return f"CN8899{self.no:06d}B"

    @property
    def row_id(self) -> str:
        return f"9f9a0002-0000-4000-a000-{self.no:012d}"

    @property
    def title_row_id(self) -> str:
        return f"9f9a0003-0000-4000-a000-{self.no:012d}"

    @property
    def vid(self) -> str:
        return f"patent_{self.patent_id}"


def _sql_in(column: str, values: list[Any], prefix: str) -> tuple[str, dict[str, Any]]:
    """构造 ``col IN (:p0, :p1, ...)`` 与参数字典；values 为空时返回恒假条件。"""
    if not values:
        return "1=0", {}
    params = {f"{prefix}{i}": v for i, v in enumerate(values)}
    placeholders = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    return f"{column} IN ({placeholders})", params


def fixture_scholar_ids() -> list[str]:
    return [p.scholar_id for p in people()]


def fixture_paper_ids() -> list[int]:
    return [p.mysql_id for p in papers()]


def fixture_project_ids() -> list[str]:
    return [p.mysql_id for p in projects()]


def fixture_patent_ids() -> list[str]:
    return [p.patent_id for p in patents()]


def fixture_vids() -> list[str]:
    return [
        *(p.vid for p in people()),
        *(p.vid for p in papers()),
        *(p.vid for p in projects()),
        *(p.vid for p in patents()),
    ]


def legacy_fixture_vids() -> list[str]:
    """旧版 expert_e2e_v1_* / 9930… 图节点，迁移时一并 detach 删除。"""
    return [
        *(f"person_{LEGACY_PREFIX}{i:03d}" for i in range(1, EXPECTED_PERSONS + 1)),
        *(f"paper_{LEGACY_PAPER_ID_BASE + p.no}" for p in papers()),
        *(f"project_{LEGACY_PREFIX}project_{p.no:03d}" for p in projects()),
        *(f"patent_{LEGACY_PREFIX}patent_{p.no:03d}" for p in patents()),
    ]


NAMES = (
    "陈明远",
    "李思源",
    "王海峰",
    "张若琳",
    "刘博文",
    "赵清扬",
    "周雨辰",
    "吴静怡",
    "徐志恒",
    "孙晓彤",
    "胡嘉伟",
    "朱雅宁",
    "高俊杰",
    "林诗涵",
    "何宇航",
    "郭欣然",
    "马致远",
    "罗婉清",
    "梁子墨",
    "宋安琪",
    "郑凯文",
    "谢雨桐",
    "韩东升",
    "唐梦洁",
    "冯浩然",
    "于佳宁",
    "董承泽",
    "萧语晨",
    "程瑞阳",
    "曹芷晴",
    "袁景行",
    "邓书瑶",
    "许文昊",
    "傅心怡",
    "沈嘉树",
    "曾可欣",
    "彭一帆",
    "吕思琪",
    "苏景明",
    "卢晓月",
    "蒋天佑",
    "蔡依然",
    "贾正阳",
    "丁若曦",
    "魏泽宇",
    "薛安然",
    "叶星河",
    "阎舒雅",
    "余嘉诚",
    "潘语柔",
    "杜明哲",
    "戴欣妍",
    "夏承宇",
    "钟灵犀",
    "汪睿哲",
    "田可心",
    "任子轩",
    "姜悦宁",
    "范嘉航",
    "方楚涵",
    "石俊熙",
    "姚诗雨",
    "谭皓轩",
    "廖心语",
    "邹景程",
    "熊若兰",
    "金宇泽",
    "陆清妍",
    "郝文轩",
    "孔令仪",
    "白子谦",
    "孟书宁",
    "秦嘉木",
    "邱婉仪",
    "侯景然",
    "龚静姝",
    "尹泽楷",
    "黎晓晴",
    "段承恩",
    "雷雨薇",
    "温景澄",
    "乔语珊",
    "莫子昂",
    "顾清妍",
    "江睿航",
    "汤婉宁",
    "施承泽",
    "洪雅琪",
    "邵俊驰",
    "万思涵",
    "陶景曜",
    "武清歌",
    "翟宇辰",
    "安若彤",
    "易明轩",
    "常舒宁",
    "文嘉佑",
    "裴诗雅",
    "章皓然",
    "康雨晴",
)


def people() -> list[Person]:
    """生成100人：保留原80人边界场景，并追加20位多院校专家。"""
    schools = (
        (56, "清华大学", "Tsinghua University"),
        (6, "华中科技大学", "Huazhong University of Science and Technology"),
        (4, "北京大学", "Peking University"),
        (2, "复旦大学", "Fudan University"),
        (2, "燕山大学", "Yanshan University"),
    )
    degrees = (("博士", "PhD"), ("硕士", "Master"), ("学士", "Bachelor"))
    dates = ("2008-2012", "2010.09-2014.06", "2012", "2014-2018", "2018.09-2022.06", "2023-2026")
    rows: list[Person] = []
    number = 1
    for count, school_zh, school_en in schools:
        for _ in range(count):
            degree_zh, degree_en = degrees[(number - 1) % len(degrees)]
            rows.append(
                Person(
                    number,
                    NAMES[number - 1],
                    school_zh,
                    school_en,
                    degree_zh,
                    degree_en,
                    dates[(number - 1) % len(dates)],
                )
            )
            number += 1

    special = (
        (" 清华大学 ", "Tsinghua University", "博士", "PhD", "2010-2014"),
        ("清华大学　", "Tsinghua University", "硕士", "Master", "2012-2016"),
        (None, "Tsinghua University", "博士", "PhD", "2011-2015"),
        ("清华大学研究生院", "Graduate School of Tsinghua University", "博士", "PhD", "2013-2017"),
        ("清华大学", "Tsinghua University", None, None, None),
        ("清华大学", "Tsinghua University", None, None, None),
        (None, None, "博士", "PhD", "2010-2014"),
        (None, None, "硕士", "Master", "2012-2016"),
        (None, None, None, None, None),
        (None, None, None, None, None),
    )
    for school_zh, school_en, degree_zh, degree_en, date in special:
        rows.append(
            Person(number, NAMES[number - 1], school_zh, school_en, degree_zh, degree_en, date)
        )
        number += 1
    extra_schools = (
        ("清华大学", "Tsinghua University"),
        ("北京大学", "Peking University"),
        ("浙江大学", "Zhejiang University"),
        ("上海交通大学", "Shanghai Jiao Tong University"),
    )
    for extra_no in range(20):
        school_zh, school_en = extra_schools[extra_no % len(extra_schools)]
        degree_zh, degree_en = degrees[extra_no % len(degrees)]
        rows.append(
            Person(
                number,
                NAMES[number - 1],
                school_zh,
                school_en,
                degree_zh,
                degree_en,
                dates[extra_no % len(dates)],
            )
        )
        number += 1
    assert len(rows) == EXPECTED_PERSONS
    return rows


def papers() -> list[Paper]:
    rows = [
        Paper(
            1,
            "面向复杂网络的可信知识推理方法",
            "Trustworthy Knowledge Reasoning for Complex Networks",
            2020,
            (1, 2),
            ("知识图谱", "可信推理"),
        ),
        Paper(
            2,
            "多源科技文献实体消歧研究",
            "Entity Disambiguation for Multi-source Scientific Literature",
            2021,
            (1, 3),
            ("实体消歧",),
        ),
        Paper(
            3,
            "大规模异构图表示学习框架",
            "Representation Learning for Large Heterogeneous Graphs",
            2023,
            (1, 3),
            ("图表示学习",),
        ),
        Paper(
            4,
            "科研合作网络的演化规律分析",
            "Evolution of Scientific Collaboration Networks",
            2022,
            (1, 4),
            ("合作网络",),
        ),
        Paper(
            5,
            "知识图谱增量更新关键技术",
            "Incremental Updating for Knowledge Graphs",
            2018,
            (1, 5),
            ("增量计算",),
        ),
        Paper(
            6,
            "跨语言学术知识融合方法",
            "Cross-lingual Academic Knowledge Fusion",
            2021,
            (1, 5),
            ("知识融合",),
        ),
        Paper(
            7,
            "亿级图数据并行查询优化",
            "Parallel Query Optimization for Billion-scale Graphs",
            2024,
            (1, 5),
            ("图查询", "并行计算"),
            ("科技创新优秀成果奖",),
        ),
        Paper(
            8,
            "弱监督条件下的专家画像构建",
            "Expert Profiling under Weak Supervision",
            None,
            (1, 6),
            ("专家画像",),
        ),
        Paper(
            9,
            "科技成果语义检索模型",
            "Semantic Retrieval for Scientific Achievements",
            2019,
            (1, 7),
            ("语义检索",),
        ),
        Paper(
            10,
            "可解释科研主题发现算法",
            "Interpretable Research Topic Discovery",
            2025,
            (1, 8),
            ("主题发现",),
        ),
        Paper(
            11,
            "面向材料设计的图神经网络",
            "Graph Neural Networks for Materials Design",
            2024,
            (9, 10),
            ("材料计算",),
        ),
        Paper(
            12,
            "科研数据质量评估指标体系",
            "Quality Metrics for Scientific Data",
            2022,
            (1, 4),
            ("数据治理",),
            ("优秀论文奖",),
        ),
    ]
    topics = (
        ("可信人工智能", "Trustworthy Artificial Intelligence"),
        ("多模态知识计算", "Multimodal Knowledge Computing"),
        ("科学智能", "AI for Science"),
        ("智能制造", "Intelligent Manufacturing"),
        ("先进材料计算", "Advanced Materials Computing"),
        ("生物信息分析", "Bioinformatics Analysis"),
        ("低碳能源优化", "Low-carbon Energy Optimization"),
        ("时空数据挖掘", "Spatiotemporal Data Mining"),
    )
    methods = ("建模方法", "推理框架", "评测体系", "优化算法", "应用研究")
    targets = (
        "复杂工业场景",
        "开放科学数据",
        "跨学科科研协作",
        "高端装备运维",
        "新材料研发",
        "精准健康管理",
        "新能源系统",
        "城市智能治理",
        "空天信息处理",
        "生态环境监测",
    )
    aspects = (
        "可信性分析",
        "协同优化",
        "知识增强",
        "可解释机制",
        "鲁棒学习",
        "动态演化",
        "工程验证",
    )
    for no in range(13, 81):
        topic_zh, topic_en = topics[(no - 13) % len(topics)]
        method = methods[(no - 13) % len(methods)]
        target = targets[(no - 13) % len(targets)]
        aspect = aspects[(no - 13) % len(aspects)]
        first = 1 + ((no - 13) % 20)
        second = 21 + ((no * 7) % 60)
        year = 2017 + ((no - 13) % 10)
        rows.append(
            Paper(
                no,
                f"面向{target}的{topic_zh}{method}与{aspect}研究",
                f"{topic_en} for {target}: {aspect}",
                year,
                (first, second),
                (topic_zh, method),
                ("青年科技创新奖",) if no % 17 == 0 else (),
            )
        )
    return rows


def projects() -> list[Project]:
    rows = [
        Project(
            1,
            "国家科技知识图谱关键技术研发",
            2020,
            1,
            (4,),
            ("知识图谱", "科技情报"),
            ("数字科技应用示范奖",),
        ),
        Project(2, "高性能图数据库查询引擎研制", 2024, 1, (7,), ("图数据库", "高性能计算")),
        Project(3, "跨领域科研成果智能发现平台", 2023, 4, (1,), ("成果发现", "人工智能")),
        Project(4, "先进材料智能设计与验证平台", 2024, 9, (10,), ("先进材料", "智能设计")),
    ]
    project_topics = (
        "可信人工智能",
        "科学数据治理",
        "智能制造",
        "低碳能源",
        "生物计算",
        "空天信息",
    )
    for no in range(5, 11):
        host = 11 + no
        participant = 31 + no
        topic = project_topics[no - 5]
        rows.append(
            Project(
                no,
                f"{topic}关键技术研发与示范应用",
                2017 + no,
                host,
                (participant,),
                (topic, "联合攻关"),
                ("产学研协同创新奖",) if no % 3 == 0 else (),
            )
        )
    return rows


def patents() -> list[Patent]:
    rows = [
        Patent(
            1,
            "一种基于异构图的科技实体关联方法",
            "Method for Scientific Entity Linking Based on Heterogeneous Graphs",
            2022,
            (1, 4),
            ("异构图", "实体关联"),
        ),
        Patent(
            2,
            "一种分布式图查询任务调度方法",
            "Distributed Graph Query Task Scheduling Method",
            2024,
            (1, 6),
            ("分布式计算", "任务调度"),
        ),
        Patent(
            3,
            "一种科研文献语义去重方法及系统",
            "Semantic Deduplication Method and System for Scientific Literature",
            2023,
            (1, 4),
            ("语义计算", "数据治理"),
        ),
        Patent(
            4,
            "一种材料性能预测模型训练方法",
            "Training Method for Material Property Prediction Models",
            2024,
            (9, 10),
            ("材料性能", "机器学习"),
        ),
    ]
    patent_topics = (
        "可信模型评估",
        "科技文本分类",
        "工业缺陷检测",
        "能源负荷预测",
        "蛋白质分析",
        "遥感影像识别",
    )
    for no in range(5, 11):
        first = 21 + no
        second = 51 + no
        topic = patent_topics[no - 5]
        rows.append(
            Patent(
                no,
                f"一种基于知识增强的{topic}方法、装置及存储介质",
                f"Knowledge-enhanced Method, Apparatus and Storage Medium for {topic}",
                2016 + no,
                (first, second),
                (topic, "发明专利"),
            )
        )
    return rows


COAUTHORS: tuple[tuple[int, int, int], ...] = (
    (1, 2, 1),  # 合著边 + 共同论文
    (1, 4, 2),  # 合著边 + 论文/项目/专利多类型互动
    (1, 11, 1),  # 只有合著边，无共同成果
)


ALLOWED_GRAPH_SPACES = frozenset({"dev", "test"})


def guard_targets() -> None:
    database = os.getenv("MYSQL_DATABASE", "gkx_element")
    space = os.getenv("TRS_GRAPH_SPACE", "dev")
    if database != "gkx_element" or space not in ALLOWED_GRAPH_SPACES:
        raise SystemExit(
            f"拒绝非测试目标：MYSQL_DATABASE={database!r}, TRS_GRAPH_SPACE={space!r}；"
            f"仅允许 gkx_element + {sorted(ALLOWED_GRAPH_SPACES)}"
        )


def scenario_manifest() -> dict[str, list[str]]:
    """脚本自校验使用的覆盖目录，也是测试人员选择数据组合的说明。"""
    return {
        "校友关系": [
            "同校/异校",
            "同学历/不同学历",
            "教育日期完全重叠/部分重叠/边界相交/不重叠",
            "中文院校/英文院校",
            "半角空格/全角空格/研究生院扩展名",
            "仅院校/仅学历日期/教育字段全空",
            "列表数量超过50",
            "学校过滤/学历过滤/组合过滤/无结果过滤",
            "有合著边/无合著边",
            "共同论文/共同项目/共同专利/多类型互动/完全无互动",
        ],
        "两点合作成果": [
            "无共同成果",
            "仅1篇论文",
            "多篇论文",
            "仅专利",
            "仅项目",
            "论文+专利+项目",
            "单类型合作",
            "多类型合作",
            "长期稳定型合作",
            "成果获奖统计",
            "开始年份/结束年份/区间过滤",
            "无法解析或缺失时间",
            "成果类型过滤",
            "每类数量限制",
            "同一专家",
            "源专家不存在",
            "目标专家不存在",
        ],
    }


def plan() -> dict[str, Any]:
    ps, pas, prs, pts = people(), papers(), projects(), patents()
    assert len(pas) + len(prs) + len(pts) == EXPECTED_ACHIEVEMENTS
    return {
        "dryRun": True,
        "batch": BATCH,
        "targets": {
            "mysql": "gkx_element",
            "graphSpace": os.getenv("TRS_GRAPH_SPACE", "dev"),
        },
        "counts": {
            "persons": len(ps),
            "papers": len(pas),
            "projects": len(prs),
            "patents": len(pts),
            "coauthorEdges": len(COAUTHORS),
            "authoredByEdges": sum(len(x.authors) for x in pas),
            "projectPersonEdges": sum(1 + len(x.participants) for x in prs),
            "inventedByEdges": sum(len(x.inventors) for x in pts),
        },
        "sampleIds": {
            "person1": ps[0].vid,
            "person4": ps[3].vid,
            "paper1": pas[0].vid,
            "project1": prs[0].vid,
            "patent1": pts[0].vid,
            "scholarId1": ps[0].scholar_id,
        },
        "scenarios": scenario_manifest(),
    }


def _delete_mysql(con) -> None:
    """按白名单删除本批次；并兼容清理旧版 PREFIX / 9930… 残留。"""
    scholar_ids = fixture_scholar_ids()
    paper_ids = fixture_paper_ids()
    project_ids = fixture_project_ids()
    patent_ids = fixture_patent_ids()
    sid_in, sid_params = _sql_in("scholar_id", scholar_ids, "s")
    cosid_in, cosid_params = _sql_in("co_scholar_id", scholar_ids, "c")
    paper_in, paper_params = _sql_in("paper_id", paper_ids, "p")
    paper_id_in, paper_id_params = _sql_in("id", paper_ids, "pi")
    proj_in, proj_params = _sql_in("id", project_ids, "pj")
    patent_in, patent_params = _sql_in("patent_id", patent_ids, "pt")
    scholar_row_in, scholar_row_params = _sql_in("scholar_id", scholar_ids, "sr")

    legacy = {
        "legacy_prefix": LEGACY_PREFIX + "%",
        "legacy_paper_low": LEGACY_PAPER_ID_BASE + 1,
        "legacy_paper_high": LEGACY_PAPER_ID_BASE + 99,
    }

    con.execute(
        text(
            f"DELETE FROM dwd_scholar_coauthor WHERE ({sid_in}) OR ({cosid_in}) "
            "OR scholar_id LIKE :legacy_prefix OR co_scholar_id LIKE :legacy_prefix"
        ),
        {**sid_params, **cosid_params, **legacy},
    )
    con.execute(
        text(
            f"DELETE FROM dwd_scholar_paper_relation WHERE ({sid_in}) OR ({paper_in}) "
            "OR scholar_id LIKE :legacy_prefix OR paper_id BETWEEN :legacy_paper_low AND :legacy_paper_high"
        ),
        {**sid_params, **paper_params, **legacy},
    )
    con.execute(
        text(
            f"DELETE FROM dwd_scholar_papers WHERE ({paper_id_in}) "
            "OR id BETWEEN :legacy_paper_low AND :legacy_paper_high"
        ),
        {**paper_id_params, **legacy},
    )
    con.execute(
        text(f"DELETE FROM dwd_zh_project_output WHERE ({proj_in}) OR id LIKE :legacy_prefix"),
        {**proj_params, **legacy},
    )
    con.execute(
        text(f"DELETE FROM dwd_zh_project WHERE ({proj_in}) OR id LIKE :legacy_prefix"),
        {**proj_params, **legacy},
    )
    con.execute(
        text(f"DELETE FROM dwd_patent_title WHERE ({patent_in}) OR patent_id LIKE :legacy_prefix"),
        {**patent_params, **legacy},
    )
    con.execute(
        text(f"DELETE FROM dwd_patent WHERE ({patent_in}) OR patent_id LIKE :legacy_prefix"),
        {**patent_params, **legacy},
    )
    con.execute(
        text(f"DELETE FROM dwd_scholar WHERE ({scholar_row_in}) OR scholar_id LIKE :legacy_prefix"),
        {**scholar_row_params, **legacy},
    )


def write_mysql() -> dict[str, int]:
    """事务内幂等重建权威数据；失败时整体回滚。"""
    now = datetime.now()
    client = MySQLClient(database="gkx_element")
    try:
        with client.engine.begin() as con:
            _delete_mysql(con)
            con.execute(
                text("""INSERT INTO dwd_scholar
                (scholar_id,name_en,name_zh,avatar,scholar_org_name_en,scholar_org_name_zh,bio,bio_zh,
                 education_background_date,education_background_institution_en,education_background_degree_en,
                 education_background_institution_zh,education_background_degree_zh,paper_nums,citation_nums,h_index,
                 status,create_time,update_time)
                VALUES (:sid,:name_en,:name_zh,'','Future Intelligence Research Center','未来智能研究中心',
                 :bio,:bio_zh,:edu_date,:school_en,:degree_en,:school_zh,:degree_zh,0,0,0,1,:now,:now)"""),
                [
                    {
                        "sid": p.scholar_id,
                        "name_en": f"Scholar {p.scholar_id}",
                        "name_zh": p.name,
                        "bio": f"synthetic fixture; batch={BATCH}",
                        "bio_zh": f"虚构端到端测试数据；批次={BATCH}",
                        "edu_date": p.education_date,
                        "school_en": p.school_en,
                        "degree_en": p.degree_en,
                        "school_zh": p.school_zh,
                        "degree_zh": p.degree_zh,
                        "now": now,
                    }
                    for p in people()
                ],
            )
            con.execute(
                text("""INSERT INTO dwd_scholar_coauthor
                (scholar_id,co_scholar_id,co_scholar_name_en,co_scholar_name_zh,co_scholar_avatar,
                 co_scholar_org_name_en,co_scholar_org_name_zh,co_paper_count,status,create_time,update_time)
                VALUES (:source,:target,:name_en,:name_zh,'','Future Intelligence Research Center','未来智能研究中心',
                 :count,1,:now,:now)"""),
                [
                    {
                        "source": people()[a - 1].scholar_id,
                        "target": people()[b - 1].scholar_id,
                        "name_en": f"Scholar {people()[b - 1].scholar_id}",
                        "name_zh": people()[b - 1].name,
                        "count": count,
                        "now": now,
                    }
                    for a, b, count in COAUTHORS
                ],
            )
            con.execute(
                text("""INSERT INTO dwd_scholar_papers
                (id,zh_name,en_name,authors,paper_url,cover_date_start,create_time,update_time,status,
                 zh_abstract,en_abstract,doi,publication_en_name)
                VALUES (:id,:zh,:en,:authors,:url,:published,:now,:now,1,:abstract_zh,:abstract_en,:doi,'Journal of Knowledge Engineering')"""),
                [
                    {
                        "id": p.mysql_id,
                        "zh": p.title,
                        "en": p.title_en,
                        "authors": json.dumps(
                            [people()[n - 1].scholar_id for n in p.authors], ensure_ascii=False
                        ),
                        "url": f"https://example.invalid/{BATCH}/paper/{p.no}",
                        "published": datetime(p.year, 6, 1) if p.year else None,
                        "abstract_zh": f"研究领域：{'、'.join(p.fields)}；测试奖项：{'、'.join(p.awards) or '无'}",
                        "abstract_en": "Synthetic fixture record.",
                        "doi": f"10.1000/fxkg.{p.mysql_id}",
                        "now": now,
                    }
                    for p in papers()
                ],
            )
            paper_relations = [
                {
                    "paper_id": p.mysql_id,
                    "year": p.year or 0,
                    "sid": people()[n - 1].scholar_id,
                    "published": datetime(p.year, 6, 1) if p.year else None,
                    "now": now,
                }
                for p in papers()
                for n in p.authors
            ]
            con.execute(
                text("""INSERT INTO dwd_scholar_paper_relation
                (paper_id,year,scholar_id,citations,publish_time,status,create_time,update_time,publication_id,related_paper_id)
                VALUES (:paper_id,:year,:sid,0,:published,1,:now,:now,0,:paper_id)"""),
                paper_relations,
            )
            con.execute(
                text("""INSERT INTO dwd_zh_project
                (id,project_number,title,project_source,funded_institution,project_level,funded_amount,discipline,
                 approval_year,approval_time,research_period,project_host,participants,keywords,abstract,
                 project_page_url,updated_time,create_time)
                VALUES (:id,:number,:title,:batch,'未来智能研究中心','国家级',1000000,'计算机科学',
                 :approval_year,:approval_time,'36个月',:host,:participants,:keywords,:abstract,:url,:now,:now)"""),
                [
                    {
                        "id": p.mysql_id,
                        "number": f"NSFC-8899-{p.no:04d}",
                        "title": p.title,
                        "batch": BATCH,
                        "approval_year": p.year,
                        "approval_time": datetime(p.year, 3, 1).date(),
                        "host": people()[p.host - 1].scholar_id,
                        "participants": json.dumps(
                            [people()[n - 1].scholar_id for n in p.participants], ensure_ascii=False
                        ),
                        "keywords": json.dumps(list(p.fields), ensure_ascii=False),
                        "abstract": f"{p.title}的虚构测试记录",
                        "url": f"https://example.invalid/{BATCH}/project/{p.no}",
                        "now": now,
                    }
                    for p in projects()
                ],
            )
            con.execute(
                text("""INSERT INTO dwd_zh_project_output
                (id,total_outputs,journal_articles_count,conference_papers_count,books_count,degree_papers_count,
                 patents_count,awards_count,reports_count,other_outputs_count,output_awards,create_time,updated_time)
                VALUES (:id,:total,0,0,0,0,0,:award_count,0,0,:awards,:now,:now)"""),
                [
                    {
                        "id": p.mysql_id,
                        "total": len(p.awards),
                        "award_count": len(p.awards),
                        "awards": json.dumps(
                            [{"year": p.year, "title": name} for name in p.awards],
                            ensure_ascii=False,
                        ),
                        "now": now,
                    }
                    for p in projects()
                ],
            )
            con.execute(
                text("""INSERT INTO dwd_patent
                (id,patent_id,publication_number,country_code,country,publication_reference,inventors,
                 first_inventor_name,keywords,main_classification_ipcr,db_source,create_time,update_time)
                VALUES (:row_id,:patent_id,:publication_number,'CN','中国',:publication_reference,:inventors,
                 :first_inventor,:keywords,'G06F16/36',:batch,:now,:now)"""),
                [
                    {
                        "row_id": p.row_id,
                        "patent_id": p.patent_id,
                        "publication_number": f"CN{p.year}8899{p.no:04d}A",
                        "publication_reference": json.dumps(
                            {"year": p.year, "date": f"{p.year}-09-01"}, ensure_ascii=False
                        ),
                        "inventors": json.dumps(
                            [
                                {
                                    "scholar_id": people()[n - 1].scholar_id,
                                    "name": people()[n - 1].name,
                                }
                                for n in p.inventors
                            ],
                            ensure_ascii=False,
                        ),
                        "first_inventor": people()[p.inventors[0] - 1].name,
                        "keywords": json.dumps(list(p.fields), ensure_ascii=False),
                        "batch": BATCH,
                        "now": now,
                    }
                    for p in patents()
                ],
            )
            con.execute(
                text("""INSERT INTO dwd_patent_title
                (id,patent_id,titles,title_localized,title_zh,db_source,create_time,update_time)
                VALUES (:row_id,:patent_id,:titles,:title_en,:title_zh,:batch,:now,:now)"""),
                [
                    {
                        "row_id": p.title_row_id,
                        "patent_id": p.patent_id,
                        "titles": json.dumps({"zh": p.title, "en": p.title_en}, ensure_ascii=False),
                        "title_en": p.title_en,
                        "title_zh": p.title,
                        "batch": BATCH,
                        "now": now,
                    }
                    for p in patents()
                ],
            )
    finally:
        client.dispose()
    return plan()["counts"]


def sync_graph_from_mysql() -> dict[str, int]:
    """只从刚写入 MySQL 的隔离记录回读，再幂等同步到当前 TRS_GRAPH_SPACE；不使用内存定义直接写图。"""
    scholar_ids = fixture_scholar_ids()
    paper_ids = fixture_paper_ids()
    project_ids = fixture_project_ids()
    patent_ids = fixture_patent_ids()
    sid_in, sid_params = _sql_in("scholar_id", scholar_ids, "s")
    paper_id_in, paper_id_params = _sql_in("id", paper_ids, "pi")
    paper_in, paper_params = _sql_in("paper_id", paper_ids, "p")
    proj_in, proj_params = _sql_in("id", project_ids, "pj")
    patent_in, patent_params = _sql_in("p.patent_id", patent_ids, "pt")

    client = MySQLClient(database="gkx_element")
    try:
        with client.engine.connect() as con:
            scholar_rows = (
                con.execute(
                    text(f"SELECT * FROM dwd_scholar WHERE {sid_in} ORDER BY scholar_id"),
                    sid_params,
                )
                .mappings()
                .all()
            )
            paper_rows = (
                con.execute(
                    text(f"SELECT * FROM dwd_scholar_papers WHERE {paper_id_in} ORDER BY id"),
                    paper_id_params,
                )
                .mappings()
                .all()
            )
            paper_rel_rows = (
                con.execute(
                    text(
                        f"SELECT paper_id,scholar_id FROM dwd_scholar_paper_relation WHERE {paper_in}"
                    ),
                    paper_params,
                )
                .mappings()
                .all()
            )
            project_rows = (
                con.execute(
                    text(f"SELECT * FROM dwd_zh_project WHERE {proj_in} ORDER BY id"),
                    proj_params,
                )
                .mappings()
                .all()
            )
            project_output_rows = (
                con.execute(
                    text(f"SELECT id,output_awards FROM dwd_zh_project_output WHERE {proj_in}"),
                    proj_params,
                )
                .mappings()
                .all()
            )
            patent_rows = (
                con.execute(
                    text(
                        "SELECT p.*,t.title_zh,t.title_localized FROM dwd_patent p "
                        f"LEFT JOIN dwd_patent_title t ON t.patent_id=p.patent_id WHERE {patent_in} "
                        "ORDER BY p.patent_id"
                    ),
                    patent_params,
                )
                .mappings()
                .all()
            )
            coauthor_rows = (
                con.execute(
                    text(
                        "SELECT scholar_id,co_scholar_id,co_paper_count FROM dwd_scholar_coauthor "
                        f"WHERE {sid_in}"
                    ),
                    sid_params,
                )
                .mappings()
                .all()
            )
    finally:
        client.dispose()

    graph = get_trs_graph_client()
    now = datetime.now().strftime("%F %T")
    output_awards = {r["id"]: r["output_awards"] for r in project_output_rows}

    for fixture_vid in [*legacy_fixture_vids(), *fixture_vids()]:
        graph.delete_node(fixture_vid, detach=True)

    def merge_edge(
        source: str, target: str, edge_type: str, key: str, props: dict[str, Any] | None = None
    ) -> None:
        graph.create_edge(source, target, edge_type, props or {})

    try:
        for row in scholar_rows:
            sid = row["scholar_id"]
            graph.merge_node(
                ["Person"],
                {"vid": f"person_{sid}"},
                {
                    "name_zh": row["name_zh"] or "",
                    "name_en": row["name_en"] or "",
                    "scholar_org": row["scholar_org_name_zh"] or row["scholar_org_name_en"] or "",
                    "biography": row["bio"] or "",
                    "bio_zh": row["bio_zh"] or "",
                    "education_background_date": row["education_background_date"] or "",
                    "education_background_institution_en": row[
                        "education_background_institution_en"
                    ]
                    or "",
                    "education_background_degree_en": row["education_background_degree_en"] or "",
                    "education_background_institution_zh": row[
                        "education_background_institution_zh"
                    ]
                    or "",
                    "education_background_degree_zh": row["education_background_degree_zh"] or "",
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "source_record_id": sid,
                    "ingest_batch": BATCH,
                    "ingest_time": now,
                    "scholar_status": int(row["status"] or 0),
                },
            )
        paper_defs = {p.mysql_id: p for p in papers()}
        for row in paper_rows:
            definition = paper_defs[row["id"]]
            graph.merge_node(
                ["Paper"],
                {"vid": definition.vid},
                {
                    "title_zh": row["zh_name"],
                    "title_en": row["en_name"],
                    "publication_year": str(definition.year or ""),
                    "publication_date": row["cover_date_start"].strftime("%F")
                    if row["cover_date_start"]
                    else "",
                    "doi": row["doi"],
                    "source": BATCH,
                },
            )
        for row in paper_rel_rows:
            merge_edge(
                f"paper_{row['paper_id']}",
                f"person_{row['scholar_id']}",
                "AUTHORED_BY",
                f"paper:{row['paper_id']}:author:{row['scholar_id']}",
            )
        for query in (
            "ALTER TAG Project ADD (output_awards string)",
            "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_zh_idx ON Person(education_background_institution_zh(256))",
            "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_en_idx ON Person(education_background_institution_en(256))",
            "REBUILD TAG INDEX person_edu_inst_zh_idx",
            "REBUILD TAG INDEX person_edu_inst_en_idx",
        ):
            try:
                graph.execute_write(query)
            except Exception as exc:  # noqa: BLE001
                print(f"skip ddl: {query[:80]} | {exc}")

        for row in project_rows:
            pvid = f"project_{row['id']}"
            raw_awards = output_awards.get(row["id"])
            if isinstance(raw_awards, (list, dict)):
                awards_json = json.dumps(raw_awards, ensure_ascii=False)
            else:
                awards_json = str(raw_awards or "[]").strip() or "[]"
            try:
                parsed_awards = json.loads(awards_json)
                awards_n = (
                    len(parsed_awards)
                    if isinstance(parsed_awards, list)
                    else (1 if parsed_awards else 0)
                )
            except json.JSONDecodeError:
                awards_n = 0 if awards_json in ("", "[]") else 1
            graph.merge_node(
                ["Project"],
                {"vid": pvid},
                {
                    "title": row["title"],
                    "approval_year": str(row["approval_year"] or ""),
                    "abstract": row["abstract"] or "",
                    "awards_count": awards_n,
                    "output_awards": awards_json,
                    "source_system": "gkx_element",
                    "source_table": "dwd_zh_project",
                    "source_record_id": row["id"],
                    "ingest_batch": BATCH,
                    "ingest_time": now,
                },
            )
            host = row["project_host"]
            if host:
                merge_edge(pvid, f"person_{host}", "LEADS", f"project:{row['id']}:lead:{host}")
            for sid in json.loads(row["participants"] or "[]"):
                merge_edge(
                    pvid,
                    f"person_{sid}",
                    "HAS_PARTICIPANT",
                    f"project:{row['id']}:participant:{sid}",
                )
        for row in patent_rows:
            pvid = f"patent_{row['patent_id']}"
            publication = (
                row["publication_reference"]
                if isinstance(row["publication_reference"], dict)
                else json.loads(row["publication_reference"] or "{}")
            )
            keywords = (
                row["keywords"]
                if isinstance(row["keywords"], list)
                else json.loads(row["keywords"] or "[]")
            )
            graph.merge_node(
                ["Patent"],
                {"vid": pvid},
                {
                    "title_zh": row["title_zh"] or "",
                    "title_en": row["title_localized"] or "",
                    "publication_date": int(
                        str(publication.get("date") or "").replace("-", "") or 0
                    ),
                    "keywords": json.dumps(keywords, ensure_ascii=False),
                    "publication_number": row["publication_number"],
                    "patent_id": row["patent_id"],
                    "db_source": BATCH,
                },
            )
            inventors = (
                row["inventors"]
                if isinstance(row["inventors"], list)
                else json.loads(row["inventors"] or "[]")
            )
            for inventor in inventors:
                sid = inventor.get("scholar_id")
                if sid:
                    merge_edge(
                        pvid,
                        f"person_{sid}",
                        "INVENTED_BY",
                        f"patent:{row['patent_id']}:inventor:{sid}",
                    )
        for row in coauthor_rows:
            merge_edge(
                f"person_{row['scholar_id']}",
                f"person_{row['co_scholar_id']}",
                "COAUTHOR_WITH",
                f"coauthor:{row['scholar_id']}:{row['co_scholar_id']}",
                {"co_paper_count": int(row["co_paper_count"] or 0)},
            )
    finally:
        close_trs_graph_client()
    return plan()["counts"]


def verify() -> dict[str, Any]:
    """核对 MySQL、图谱、编码、字段一致性和关键业务场景；不写数据。"""
    expected = plan()["counts"]
    sid_in, sid_params = _sql_in("scholar_id", fixture_scholar_ids(), "s")
    paper_id_in, paper_id_params = _sql_in("id", fixture_paper_ids(), "pi")
    proj_in, proj_params = _sql_in("id", fixture_project_ids(), "pj")
    patent_in, patent_params = _sql_in("patent_id", fixture_patent_ids(), "pt")
    client = MySQLClient(database="gkx_element")
    with client.engine.connect() as con:
        mysql_counts = {
            "persons": con.execute(
                text(f"SELECT COUNT(*) FROM dwd_scholar WHERE {sid_in}"),
                sid_params,
            ).scalar_one(),
            "papers": con.execute(
                text(f"SELECT COUNT(*) FROM dwd_scholar_papers WHERE {paper_id_in}"),
                paper_id_params,
            ).scalar_one(),
            "projects": con.execute(
                text(f"SELECT COUNT(*) FROM dwd_zh_project WHERE {proj_in}"),
                proj_params,
            ).scalar_one(),
            "patents": con.execute(
                text(f"SELECT COUNT(*) FROM dwd_patent WHERE {patent_in}"),
                patent_params,
            ).scalar_one(),
        }
        encoding_errors = con.execute(
            text(
                f"SELECT COUNT(*) FROM dwd_scholar WHERE {sid_in} AND "
                "(name_zh LIKE '%æ%' OR name_zh LIKE '%�%' OR education_background_institution_zh LIKE '%æ%')"
            ),
            sid_params,
        ).scalar_one()
    client.dispose()
    graph = get_trs_graph_client()
    try:
        graph_nodes = {
            "persons": sum(graph.get_node(p.vid) is not None for p in people()),
            "papers": sum(graph.get_node(p.vid) is not None for p in papers()),
            "projects": sum(graph.get_node(p.vid) is not None for p in projects()),
            "patents": sum(graph.get_node(p.vid) is not None for p in patents()),
        }
        field_mismatches = []
        for p in people():
            node = graph.get_node(p.vid)
            props = node.properties if node else {}
            if props.get("name_zh", "") != p.name or props.get(
                "education_background_institution_zh", ""
            ) != (p.school_zh or ""):
                field_mismatches.append(p.scholar_id)
    finally:
        close_trs_graph_client()
    ok = (
        mysql_counts == {k: expected[k] for k in mysql_counts}
        and graph_nodes == mysql_counts
        and encoding_errors == 0
        and not field_mismatches
    )
    return {
        "ok": ok,
        "batch": BATCH,
        "mysql": mysql_counts,
        "graph": graph_nodes,
        "encodingErrors": encoding_errors,
        "fieldMismatches": field_mismatches,
        "sampleIds": plan()["sampleIds"],
        "scenarioManifest": scenario_manifest(),
    }


def cleanup() -> dict[str, Any]:
    """仅删除本批次节点和 MySQL 记录；detach 会一并删除本批次关联边。"""
    graph = get_trs_graph_client()
    try:
        for vid in [*legacy_fixture_vids(), *fixture_vids()]:
            graph.delete_node(vid, detach=True)
    finally:
        close_trs_graph_client()
    client = MySQLClient(database="gkx_element")
    try:
        with client.engine.begin() as con:
            _delete_mysql(con)
    finally:
        client.dispose()
    return {"cleaned": BATCH, "sampleIdsRemoved": plan()["sampleIds"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="两个专家模块的 MySQL -> TRSGraph(dev|test) 端到端测试数据闭环"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--apply",
        action="store_true",
        help="幂等重建 MySQL 数据并从 MySQL 回读同步到当前 TRS_GRAPH_SPACE（dev|test）",
    )
    action.add_argument(
        "--verify", action="store_true", help="只读校验 MySQL 与当前 TRS_GRAPH_SPACE"
    )
    action.add_argument("--cleanup", action="store_true", help="清理且仅清理本批次")
    parser.add_argument("--confirm-cleanup", help=f"清理确认值必须精确等于 {BATCH}")
    args = parser.parse_args()
    guard_targets()
    if args.apply:
        result = {"mysql": write_mysql(), "graph": sync_graph_from_mysql(), "verify": verify()}
    elif args.verify:
        result = verify()
    elif args.cleanup:
        if args.confirm_cleanup != BATCH:
            raise SystemExit(f"清理需要 --confirm-cleanup {BATCH}")
        result = cleanup()
    else:
        result = plan()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
