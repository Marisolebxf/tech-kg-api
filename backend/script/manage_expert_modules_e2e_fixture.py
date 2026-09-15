"""两个专家模块的端到端测试数据闭环（MySQL gkx_element -> TRSGraph）。

覆盖模块：
1. 科技专家两点合作成果
2. 科技专家校友关系
3. 科技专家论文合作关系（合作论文被引链路：dwd_zh_paper_citation 源表 +
   图上 CITED_BY/CITES 双向边，被引次数=边数，引用方可经 AUTHORED_BY 追溯作者；
   期刊/会议分级链路：dwd_zh_journal 源表 + Journal 节点 + PUBLISHED_IN 边，
   SCIE 期刊显示 JCR 分区（虚构 Q1/Q2）、中文核心期刊（classify_list→zh_core）
   显示核心标识、其余如实显示“未分级”）

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
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from infra.graph_db import close_trs_graph_client, get_trs_graph_client
from infra.mysql import MySQLClient

HUAZHONG_UNIVERSITY = "华中科技大学"
PEKING_UNIVERSITY = "Peking University"
SHANGHAI_JIAO_TONG_UNIVERSITY = "上海交通大学"
TSINGHUA_UNIVERSITY = "Tsinghua University"

BATCH = "EXPERT_MODULES_E2E_V1"
# 预留号段：形态像真，与现网抽样不冲突；清理靠白名单 + BATCH 确认。
PAPER_ID_BASE = 889900000  # paper ids: 889900001 .. 889900080
EXPECTED_PERSONS = 100
EXPECTED_ACHIEVEMENTS = 100
# 旧版 ID（expert_e2e_v1_* / 9930…），apply/cleanup 时一并清除以免残留。
LEGACY_PREFIX = "expert_e2e_v1_"
LEGACY_PAPER_ID_BASE = 9930000000000000

# 校友邻域：Person -[STUDIED_AT]-> Organization；org vid 由院校名确定性生成。
_CANONICAL_SCHOOLS: dict[str, tuple[str, str]] = {
    "清华大学": ("清华大学", TSINGHUA_UNIVERSITY),
    HUAZHONG_UNIVERSITY: (HUAZHONG_UNIVERSITY, "Huazhong University of Science and Technology"),
    "北京大学": ("北京大学", PEKING_UNIVERSITY),
    "复旦大学": ("复旦大学", "Fudan University"),
    "燕山大学": ("燕山大学", "Yanshan University"),
    "浙江大学": ("浙江大学", "Zhejiang University"),
    SHANGHAI_JIAO_TONG_UNIVERSITY: (SHANGHAI_JIAO_TONG_UNIVERSITY, "Shanghai Jiao Tong University"),
}


def _normalize_school_key(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "")
    return re.sub(r"\s+", "", text.strip())


def school_org_vid(school_zh: str | None, school_en: str | None = None) -> str | None:
    raw = (school_zh or school_en or "").strip()
    if not raw:
        return None
    key = _normalize_school_key(raw)
    # 研究生院 / 带空格变体归并到主校名
    for canon in _CANONICAL_SCHOOLS:
        if _normalize_school_key(canon) in key or key in _normalize_school_key(canon):
            digest = hashlib.md5(canon.encode("utf-8")).hexdigest()[:12]
            return f"org_fx_{digest}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return f"org_fx_{digest}"


def school_org_names(school_zh: str | None, school_en: str | None) -> tuple[str, str]:
    raw_zh = (school_zh or "").strip()
    raw_en = (school_en or "").strip()
    key = _normalize_school_key(raw_zh or raw_en)
    for canon_zh, (zh, en) in _CANONICAL_SCHOOLS.items():
        if _normalize_school_key(canon_zh) in key or key in _normalize_school_key(canon_zh):
            return zh, en
    return raw_zh or raw_en, raw_en or raw_zh


def fixture_org_vids() -> list[str]:
    vids: list[str] = []
    seen: set[str] = set()
    for p in people():
        vid = school_org_vid(p.school_zh, p.school_en)
        if vid and vid not in seen:
            seen.add(vid)
            vids.append(vid)
    return vids


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
    # 发表期刊序号（1 起，对应 journals()）；决定期刊/会议级别显示 SCI 还是未分级。
    journal: int = 1

    @property
    def mysql_id(self) -> int:
        return PAPER_ID_BASE + self.no

    @property
    def vid(self) -> str:
        # 与正式论文加载器 paper_vid(paper_id) 保持一致。
        return f"paper_{self.mysql_id}"


@dataclass(frozen=True)
class Journal:
    """虚构期刊（PUBLISHED_IN 源表 dwd_zh_journal）。"""

    publication_id: int
    zh_name: str
    en_name: str
    name_abbr: str
    issn: str
    founding_time: int
    impact_factor: float
    cite_nums: int
    annual_publication: int
    is_sci: int
    publication_cycle: str
    # 中文核心分类（源列 classify_list→图属性 zh_core）：非 SCI 刊的级别显示来源。
    zh_core: str = ""
    # JCR/中科院分区（虚构值；源表无对应列，仅在图节点上展示 SCIE 刊的分级）。
    jcr_zone: str = ""
    scope_zone: str = ""

    @property
    def vid(self) -> str:
        # 与真实 ETL（load_paper_journal_graph.load_journals）一致：journal_{publication_id}。
        return f"journal_{self.publication_id}"


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
        # dwd_patent_title.id 为 varchar(20)
        return f"fxptt{self.no:04d}"

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


def journals() -> list[Journal]:
    """4 本虚构期刊：两本 SCIE（JCR-Q1/Q2）、一本中文核心（“北大核心”）、一本普通（“未分级”）。

    publication_id 使用预留号段 8899000x（真实 zh/en 期刊表与图上均无占用），
    节点为本批次私有，随 cleanup 一并删除。
    """
    return [
        Journal(
            88990001,
            "知识工程学报",
            "Journal of Knowledge Engineering",
            "JKE",
            "2096-1878",
            1987,
            3.2,
            5210,
            192,
            1,
            "月刊",
            jcr_zone="Q1",
            scope_zone="2区",
        ),
        Journal(
            88990002,
            "智能系统研究",
            "Journal of Intelligent Systems Research",
            "JISR",
            "2096-3921",
            1999,
            1.6,
            1830,
            96,
            1,
            "双月刊",
            jcr_zone="Q2",
            scope_zone="3区",
        ),
        Journal(
            88990003,
            "数据科学论坛",
            "Data Science Forum",
            "DSF",
            "2096-7408",
            2015,
            0.7,
            420,
            64,
            0,
            "季刊",
            "北大核心",
        ),
        Journal(
            88990004,
            "新兴科技评论",
            "Emerging Technology Review",
            "ETR",
            "2096-8216",
            2018,
            0.9,
            260,
            48,
            0,
            "双月刊",
        ),
    ]


def fixture_journal_vids() -> list[str]:
    return [j.vid for j in journals()]


def fixture_vids() -> list[str]:
    return [
        *(p.vid for p in people()),
        *(p.vid for p in papers()),
        *(p.vid for p in projects()),
        *(p.vid for p in patents()),
        *fixture_journal_vids(),
        *fixture_org_vids(),
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
        (56, "清华大学", TSINGHUA_UNIVERSITY),
        (6, HUAZHONG_UNIVERSITY, "Huazhong University of Science and Technology"),
        (4, "北京大学", PEKING_UNIVERSITY),
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
        (" 清华大学 ", TSINGHUA_UNIVERSITY, "博士", "PhD", "2010-2014"),
        ("清华大学　", TSINGHUA_UNIVERSITY, "硕士", "Master", "2012-2016"),
        (None, TSINGHUA_UNIVERSITY, "博士", "PhD", "2011-2015"),
        ("清华大学研究生院", "Graduate School of Tsinghua University", "博士", "PhD", "2013-2017"),
        ("清华大学", TSINGHUA_UNIVERSITY, None, None, None),
        ("清华大学", TSINGHUA_UNIVERSITY, None, None, None),
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
        ("清华大学", TSINGHUA_UNIVERSITY),
        ("北京大学", PEKING_UNIVERSITY),
        ("浙江大学", "Zhejiang University"),
        (SHANGHAI_JIAO_TONG_UNIVERSITY, "Shanghai Jiao Tong University"),
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
    # journal 序号：论文 1-12 显式指定（论文合作用例的论文 4/5/6/7/12 落在 JCR 分区期刊，
    # 年份缺失的论文 8 落在普通期刊覆盖“未分级”）；13-80 轮换前三本期刊，
    # 其中 no%3==2 的论文落在中文核心期刊覆盖“北大核心”。
    rows = [
        Paper(
            1,
            "面向复杂网络的可信知识推理方法",
            "Trustworthy Knowledge Reasoning for Complex Networks",
            2020,
            (1, 2),
            ("知识图谱", "可信推理"),
            journal=1,
        ),
        Paper(
            2,
            "多源科技文献实体消歧研究",
            "Entity Disambiguation for Multi-source Scientific Literature",
            2021,
            (1, 3),
            ("实体消歧",),
            journal=1,
        ),
        Paper(
            3,
            "大规模异构图表示学习框架",
            "Representation Learning for Large Heterogeneous Graphs",
            2023,
            (1, 3),
            ("图表示学习",),
            journal=2,
        ),
        Paper(
            4,
            "科研合作网络的演化规律分析",
            "Evolution of Scientific Collaboration Networks",
            2022,
            (1, 4),
            ("合作网络",),
            journal=1,
        ),
        Paper(
            5,
            "知识图谱增量更新关键技术",
            "Incremental Updating for Knowledge Graphs",
            2018,
            (1, 5),
            ("增量计算",),
            journal=2,
        ),
        Paper(
            6,
            "跨语言学术知识融合方法",
            "Cross-lingual Academic Knowledge Fusion",
            2021,
            (1, 5),
            ("知识融合",),
            journal=1,
        ),
        Paper(
            7,
            "亿级图数据并行查询优化",
            "Parallel Query Optimization for Billion-scale Graphs",
            2024,
            (1, 5),
            ("图查询", "并行计算"),
            ("科技创新优秀成果奖",),
            journal=2,
        ),
        Paper(
            8,
            "弱监督条件下的专家画像构建",
            "Expert Profiling under Weak Supervision",
            None,
            (1, 6),
            ("专家画像",),
            journal=4,
        ),
        Paper(
            9,
            "科技成果语义检索模型",
            "Semantic Retrieval for Scientific Achievements",
            2019,
            (1, 7),
            ("语义检索",),
            journal=1,
        ),
        Paper(
            10,
            "可解释科研主题发现算法",
            "Interpretable Research Topic Discovery",
            2025,
            (1, 8),
            ("主题发现",),
            journal=2,
        ),
        Paper(
            11,
            "面向材料设计的图神经网络",
            "Graph Neural Networks for Materials Design",
            2024,
            (9, 10),
            ("材料计算",),
            journal=1,
        ),
        Paper(
            12,
            "科研数据质量评估指标体系",
            "Quality Metrics for Scientific Data",
            2022,
            (1, 4),
            ("数据治理",),
            ("优秀论文奖",),
            journal=2,
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
                1 + (no % 3),
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

# 论文引用（引用方论文 no，被引论文 no）。引用方年份均晚于被引方，符合引用时序。
# 链路与真实 ETL 一致：MySQL dwd_zh_paper_citation 为权威源（id=被引论文、doi=引用方 DOI），
# 图上建 CITED_BY（被引→引用方，citation_identifier=引用方 DOI）与 CITES（引用方→被引，
# reference_identifier=被引 DOI）双向边；引用方均为库内真实 Paper，再经 AUTHORED_BY
# 关联到作者，"哪篇被引、谁引用"全程可溯。论文合作模块的被引次数即 CITED_BY 边数。
# 覆盖：person 1/5 的三篇合作论文（5/6/7）分别被引 3/2/1 次，总被引 6、最高 3。
CITATIONS: tuple[tuple[int, int], ...] = (
    (2, 5),  # 多源消歧(2021) 引用 增量更新(2018)
    (3, 5),  # 异构图表示学习(2023) 引用 增量更新(2018)
    (7, 5),  # 并行查询优化(2024) 引用 增量更新(2018)
    (3, 6),  # 异构图表示学习(2023) 引用 知识融合(2021)
    (10, 6),  # 主题发现(2025) 引用 知识融合(2021)
    (10, 7),  # 主题发现(2025) 引用 并行查询优化(2024)
    (4, 1),  # 合作网络(2022) 引用 可信推理(2020)
    (12, 1),  # 数据质量(2022) 引用 可信推理(2020)
    (11, 3),  # 材料GNN(2024) 引用 异构图表示学习(2023)
    (11, 4),  # 材料GNN(2024) 引用 合作网络(2022)
)


def cited_counts() -> dict[int, int]:
    """每篇论文的被引次数（= 图上 CITED_BY 入边数，也回填 MySQL 关系表 citations）。"""
    counts: dict[int, int] = {}
    for _citing, cited in CITATIONS:
        counts[cited] = counts.get(cited, 0) + 1
    return counts


def research_fields_by_person() -> dict[int, list[str]]:
    """专家研究方向 = 本人全部成果领域（论文/项目/专利 fields）的并集，保序去重。

    与项目结构对齐：MySQL 写 dwd_scholar_research_direction.fields（分号分隔，
    老实现与图 Person.research_fields 回退都按分号切分）。
    """
    fields: dict[int, list[str]] = {}

    def add(person_no: int, items: tuple[str, ...]) -> None:
        bucket = fields.setdefault(person_no, [])
        for item in items:
            if item and item not in bucket:
                bucket.append(item)

    for p in papers():
        for n in p.authors:
            add(n, p.fields)
    for prj in projects():
        add(prj.host, prj.fields)
        for n in prj.participants:
            add(n, prj.fields)
    for pt in patents():
        for n in pt.inventors:
            add(n, pt.fields)
    return fields


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
        "论文合作关系": [
            "合作论文被引次数（CITED_BY 边数）",
            "被引论文与引用论文互链（CITED_BY/CITES 双向）",
            "引用论文经 AUTHORED_BY 关联引用作者",
            "被引次数为 0（未被引用的论文）",
            "论文主题（HAS_KEYWORD→Keyword，源表 dwd_zh_paper_classification）",
            "专家研究方向（dwd_scholar_research_direction → Person.research_fields 回退）",
            "期刊/会议级别（PUBLISHED_IN→Journal，源表 dwd_zh_journal，JCR 分区/中文核心/未分级期刊覆盖）",
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
            "citationRows": len(CITATIONS),
            "citedByEdges": len(CITATIONS),
            "citesEdges": len(CITATIONS),
            "classificationRows": sum(1 for x in pas if x.fields),
            "keywordEdges": sum(len(x.fields) for x in pas if x.fields),
            "researchDirectionRows": len(research_fields_by_person()),
            "journalRows": len(pas),
            "journalNodes": len(journals()),
            "publishedInEdges": len(pas),
        },
        "sampleIds": {
            "person1": ps[0].vid,
            "person4": ps[3].vid,
            "paper1": pas[0].vid,
            "project1": prs[0].vid,
            "patent1": pts[0].vid,
            "scholarId1": ps[0].scholar_id,
            "journal1": journals()[0].vid,
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
    # 引用表：id 为 varchar，按本批次号段字符串删除；data_source 兜底防残留。
    cit_id_in, cit_id_params = _sql_in("id", [str(i) for i in paper_ids], "cit")
    con.execute(
        text(f"DELETE FROM dwd_zh_paper_citation WHERE ({cit_id_in}) OR data_source = :batch"),
        {**cit_id_params, "batch": BATCH},
    )
    # 论文关键词分类表（HAS_KEYWORD 源表），同样按号段字符串 + 批次删除。
    con.execute(
        text(
            f"DELETE FROM dwd_zh_paper_classification WHERE ({cit_id_in}) OR data_source = :batch"
        ),
        {**cit_id_params, "batch": BATCH},
    )
    # 期刊映射表（PUBLISHED_IN 源表）：paper_id 为 varchar，按号段字符串 + 批次删除。
    jpaper_in, jpaper_params = _sql_in("paper_id", [str(i) for i in paper_ids], "jp")
    con.execute(
        text(f"DELETE FROM dwd_zh_journal WHERE ({jpaper_in}) OR data_source = :batch"),
        {**jpaper_params, "batch": BATCH},
    )
    con.execute(
        text(f"DELETE FROM dwd_scholar_research_direction WHERE ({sid_in})"),
        sid_params,
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
                    # citations=该论文被引次数，与图上 CITED_BY 边数一致（同一作者多行同值）。
                    "citations": cited_counts().get(p.no, 0),
                    "published": datetime(p.year, 6, 1) if p.year else None,
                    "now": now,
                }
                for p in papers()
                for n in p.authors
            ]
            con.execute(
                text("""INSERT INTO dwd_scholar_paper_relation
                (paper_id,year,scholar_id,citations,publish_time,status,create_time,update_time,publication_id,related_paper_id)
                VALUES (:paper_id,:year,:sid,:citations,:published,1,:now,:now,0,:paper_id)"""),
                paper_relations,
            )
            # 引用权威源：id=被引论文 id、doi/zh_name=引用方论文（真实 ETL 的 CITED_BY 数据源）。
            con.execute(
                text("""INSERT INTO dwd_zh_paper_citation
                (id,publication_id,doi,zh_name,publication_zh_name,data_source,created_time,updated_time)
                VALUES (:id,0,:doi,:zh_name,'Journal of Knowledge Engineering',:batch,:now,:now)"""),
                [
                    {
                        "id": str(papers()[cited - 1].mysql_id),
                        "doi": f"10.1000/fxkg.{papers()[citing - 1].mysql_id}",
                        "zh_name": papers()[citing - 1].title,
                        "batch": BATCH,
                        "now": now,
                    }
                    for citing, cited in CITATIONS
                ],
            )
            # 论文关键词权威源：逗号分隔（真实 ETL 的 HAS_KEYWORD 数据源），仅写有领域的论文。
            con.execute(
                text("""INSERT INTO dwd_zh_paper_classification
                (id,keywords,data_source,created_time,updated_time)
                VALUES (:id,:keywords,:batch,:now,:now)"""),
                [
                    {
                        "id": str(p.mysql_id),
                        "keywords": ",".join(p.fields),
                        "batch": BATCH,
                        "now": now,
                    }
                    for p in papers()
                    if p.fields
                ],
            )
            # 期刊权威源（真实 ETL 的 Journal 节点 + PUBLISHED_IN 边数据源）：
            # 每篇论文一行 paper_id→publication_id 映射，附带刊名/ISSN/影响因子等元数据。
            con.execute(
                text("""INSERT INTO dwd_zh_journal
                (paper_id,publication_id,zh_name,en_name,name_abbr,issn,country,founding_time,
                 impact_factor,cite_nums,annual_publication,is_sci,publication_cycle,classify_list,
                 data_source,created_time,updated_time)
                VALUES (:paper_id,:pub_id,:zh_name,:en_name,:abbr,:issn,'中国',:founded,
                 :impact,:cites,:annual,:is_sci,:cycle,:zh_core,:batch,:now,:now)"""),
                [
                    {
                        "paper_id": str(p.mysql_id),
                        "pub_id": j.publication_id,
                        "zh_name": j.zh_name,
                        "en_name": j.en_name,
                        "abbr": j.name_abbr,
                        "issn": j.issn,
                        "founded": j.founding_time,
                        "impact": j.impact_factor,
                        "cites": j.cite_nums,
                        "annual": j.annual_publication,
                        "is_sci": j.is_sci,
                        "cycle": j.publication_cycle,
                        "zh_core": j.zh_core or None,
                        "batch": BATCH,
                        "now": now,
                    }
                    for p in papers()
                    for j in (journals()[p.journal - 1],)
                ],
            )
            # 专家研究方向：分号分隔（老实现与图 Person.research_fields 回退均按分号切分）。
            con.execute(
                text("""INSERT INTO dwd_scholar_research_direction
                (scholar_id,fields,create_time,update_time)
                VALUES (:sid,:fields,:now,:now)"""),
                [
                    {
                        "sid": people()[person_no - 1].scholar_id,
                        "fields": ";".join(fields),
                        "now": now,
                    }
                    for person_no, fields in sorted(research_fields_by_person().items())
                ],
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
            citation_rows = (
                con.execute(
                    text(
                        "SELECT id,doi FROM dwd_zh_paper_citation "
                        "WHERE data_source = :batch ORDER BY id,doi"
                    ),
                    {"batch": BATCH},
                )
                .mappings()
                .all()
            )
            classification_rows = (
                con.execute(
                    text(
                        "SELECT id,keywords FROM dwd_zh_paper_classification "
                        "WHERE data_source = :batch ORDER BY id"
                    ),
                    {"batch": BATCH},
                )
                .mappings()
                .all()
            )
            research_rows = (
                con.execute(
                    text(
                        "SELECT scholar_id,fields FROM dwd_scholar_research_direction "
                        f"WHERE {sid_in} ORDER BY scholar_id"
                    ),
                    sid_params,
                )
                .mappings()
                .all()
            )
            journal_rows = (
                con.execute(
                    text(
                        "SELECT paper_id,publication_id FROM dwd_zh_journal "
                        "WHERE data_source = :batch ORDER BY paper_id"
                    ),
                    {"batch": BATCH},
                )
                .mappings()
                .all()
            )
    finally:
        client.dispose()

    graph = get_trs_graph_client()
    now = datetime.now().strftime("%F %T")
    output_awards = {r["id"]: r["output_awards"] for r in project_output_rows}
    research_fields_by_sid = {r["scholar_id"]: r["fields"] or "" for r in research_rows}

    for fixture_vid in [*legacy_fixture_vids(), *fixture_vids()]:
        graph.delete_node(fixture_vid, detach=True)

    def merge_edge(
        source: str, target: str, edge_type: str, key: str, props: dict[str, Any] | None = None
    ) -> None:
        _ = key
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
                    # 研究方向（分号分隔）：论文合作模块在无 HAS_KEYWORD 边时的主题回退来源。
                    "research_fields": research_fields_by_sid.get(sid, ""),
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
        # 引用链路：引用方 DOI 在库内时对齐到真实 Paper vid（与真实 ETL 的对齐形态一致，
        # 不建 paper_cit_ 桩）；CITED_BY 被引→引用方，CITES 引用方→被引，互为反向。
        paper_doi_by_vid = {f"paper_{row['id']}": str(row["doi"] or "") for row in paper_rows}
        paper_vid_by_doi = {doi: vid for vid, doi in paper_doi_by_vid.items() if doi}
        for row in citation_rows:
            cited_vid = f"paper_{row['id']}"
            citing_doi = str(row["doi"] or "")
            citing_vid = paper_vid_by_doi.get(citing_doi)
            if not citing_vid or citing_vid == cited_vid:
                continue
            merge_edge(
                cited_vid,
                citing_vid,
                "CITED_BY",
                f"cited_by:{citing_vid}:{cited_vid}",
                {"citation_identifier": citing_doi, "confidence": 1.0},
            )
            merge_edge(
                citing_vid,
                cited_vid,
                "CITES",
                f"cites:{cited_vid}:{citing_vid}",
                {"reference_identifier": paper_doi_by_vid.get(cited_vid, ""), "confidence": 1.0},
            )
        # 论文关键词（HAS_KEYWORD 源表 dwd_zh_paper_classification，逗号分隔）：
        # Keyword 桩 vid 与真实 ETL（load_paper_relation.load_has_keyword）同为
        # keyword_{md5(keyword)}，是跨批次共享维度节点——已存在则不覆盖，也不进
        # fixture_vids（cleanup 删论文时 detach 掉本批次的边即可，节点留给真实数据）。
        for row in classification_rows:
            keywords = [kw.strip() for kw in str(row["keywords"] or "").split(",") if kw.strip()]
            for kw in keywords:
                kvid = f"keyword_{hashlib.md5(kw.encode('utf-8')).hexdigest()}"
                if graph.get_node(kvid) is None:
                    graph.merge_node(["Keyword"], {"vid": kvid}, {"keyword": kw})
                merge_edge(
                    f"paper_{row['id']}",
                    kvid,
                    "HAS_KEYWORD",
                    f"has_keyword:paper_{row['id']}:{kvid}",
                    {
                        "source_table": "dwd_zh_paper_classification",
                        "source_record_id": str(row["id"]),
                        "ingest_batch": BATCH,
                        "ingest_time": now,
                    },
                )
        # 论文期刊（PUBLISHED_IN 源表 dwd_zh_journal）：Journal 桩 vid 与真实 ETL
        # （load_paper_journal_graph.load_journals）同为 journal_{publication_id}，节点
        # 属性按中文期刊 ETL 映射（classify_list→zh_core 中文核心；SCIE 刊的
        # jcr_zone/scope_zone 源表无对应列，按定义写入虚构 Q1/Q2；dev 的 Journal
        # TAG 无溯源属性，故只写 TAG 内属性），PUBLISHED_IN 边带 confidence=1.0。
        # 预留号段内的期刊节点为本批次私有，已进 fixture_vids 随 cleanup 一并删除。
        journal_defs = {j.publication_id: j for j in journals()}
        for row in journal_rows:
            definition = journal_defs[int(row["publication_id"])]
            jvid = definition.vid
            if graph.get_node(jvid) is None:
                graph.merge_node(
                    ["Journal"],
                    {"vid": jvid},
                    {
                        "name_zh": definition.zh_name,
                        "name_en": definition.en_name,
                        "name_abbr": definition.name_abbr,
                        "issn": definition.issn,
                        "country": "中国",
                        "founding_time": str(definition.founding_time),
                        "impact_factor": str(definition.impact_factor),
                        "is_sci": str(definition.is_sci),
                        "zh_core": definition.zh_core,
                        "jcr_zone": definition.jcr_zone,
                        "scope_zone": definition.scope_zone,
                        "cite_nums": str(definition.cite_nums),
                        "annual_publication": str(definition.annual_publication),
                        "publication_cycle": definition.publication_cycle,
                        "source": "zh_journal",
                    },
                )
            merge_edge(
                f"paper_{row['paper_id']}",
                jvid,
                "PUBLISHED_IN",
                f"published_in:paper_{row['paper_id']}:{jvid}",
                {"confidence": 1.0},
            )
        for query in (
            "CREATE EDGE IF NOT EXISTS STUDIED_AT("
            "degree_zh string, degree_en string, education_date string, "
            "institution_zh string, institution_en string, confidence double, "
            "match_method string, match_evidence string, source_system string, "
            "source_table string, source_record_id string, ingest_batch string, ingest_time string)",
            "ALTER TAG Project ADD (output_awards string)",
            "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_zh_idx ON Person(education_background_institution_zh(256))",
            "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_en_idx ON Person(education_background_institution_en(256))",
            "REBUILD TAG INDEX person_edu_inst_zh_idx",
            "REBUILD TAG INDEX person_edu_inst_en_idx",
        ):
            try:
                graph.execute_write(query)
                if query.startswith("CREATE EDGE"):
                    time.sleep(3)
            except Exception as exc:  # noqa: BLE001
                print(f"skip ddl: {query[:80]} | {exc}")

        # 院校 Organization + STUDIED_AT（校友邻域）
        org_props: dict[str, tuple[str, str]] = {}
        for p in people():
            ovid = school_org_vid(p.school_zh, p.school_en)
            if not ovid:
                continue
            if ovid not in org_props:
                org_props[ovid] = school_org_names(p.school_zh, p.school_en)
        for ovid, (name_zh, name_en) in org_props.items():
            graph.merge_node(
                ["Organization"],
                {"vid": ovid},
                {
                    "name_cn": name_zh,
                    "name_en": name_en,
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "ingest_batch": BATCH,
                    "ingest_time": now,
                },
            )
        for row in scholar_rows:
            sid = row["scholar_id"]
            inst_zh = row["education_background_institution_zh"] or ""
            inst_en = row["education_background_institution_en"] or ""
            ovid = school_org_vid(inst_zh, inst_en)
            if not ovid:
                continue
            merge_edge(
                f"person_{sid}",
                ovid,
                "STUDIED_AT",
                f"studied:{sid}:{ovid}",
                {
                    "degree_zh": row["education_background_degree_zh"] or "",
                    "degree_en": row["education_background_degree_en"] or "",
                    "education_date": row["education_background_date"] or "",
                    "institution_zh": inst_zh,
                    "institution_en": inst_en,
                    "confidence": 1.0,
                    "match_method": "fixture",
                    "match_evidence": "e2e fixture school org",
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "source_record_id": f"{sid}|studied|{ovid}",
                    "ingest_batch": BATCH,
                    "ingest_time": now,
                },
            )

        for row in project_rows:
            pvid = f"project_{row['id']}"
            raw_awards = output_awards.get(row["id"])
            if isinstance(raw_awards, (list, dict)):
                awards_json = json.dumps(raw_awards, ensure_ascii=False)
            else:
                awards_json = str(raw_awards or "[]").strip() or "[]"
            try:
                parsed_awards = json.loads(awards_json)
                if isinstance(parsed_awards, list):
                    awards_n = len(parsed_awards)
                else:
                    awards_n = int(bool(parsed_awards))
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
    paper_in, paper_params = _sql_in("paper_id", fixture_paper_ids(), "p")
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
        citation_rows = con.execute(
            text("SELECT COUNT(*) FROM dwd_zh_paper_citation WHERE data_source = :batch"),
            {"batch": BATCH},
        ).scalar_one()
        classification_rows = con.execute(
            text("SELECT COUNT(*) FROM dwd_zh_paper_classification WHERE data_source = :batch"),
            {"batch": BATCH},
        ).scalar_one()
        research_rows = con.execute(
            text(f"SELECT COUNT(*) FROM dwd_scholar_research_direction WHERE {sid_in}"),
            sid_params,
        ).scalar_one()
        journal_rows = con.execute(
            text("SELECT COUNT(*) FROM dwd_zh_journal WHERE data_source = :batch"),
            {"batch": BATCH},
        ).scalar_one()
        relation_citations = dict(
            con.execute(
                text(
                    f"SELECT paper_id,MAX(citations) FROM dwd_scholar_paper_relation "
                    f"WHERE {paper_in} GROUP BY paper_id"
                ),
                paper_params,
            ).all()
        )
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
        # 抽样：源专家应有 STUDIED_AT 出边（校友邻域）
        sample = people()[0]
        sample_org = school_org_vid(sample.school_zh, sample.school_en)
        studied_ok = False
        if sample_org:
            try:
                out_edges = graph.get_node_edges(
                    sample.vid, direction="out", edge_type="STUDIED_AT", limit=20
                )
            except Exception:  # noqa: BLE001
                out_edges = []
            studied_ok = any(
                str(getattr(e, "target_id", "") or "") == sample_org
                or str(getattr(e, "source_id", "") or "") == sample.vid
                for e in (out_edges or [])
            )
        # 被引链路一致性：图上 CITED_BY/CITES 边数 = MySQL 引用行数 = 关系表 citations 值，
        # 且每条 CITED_BY 的目标都是库内真实论文（无 paper_cit_ 桩）。
        citation_edges_ok = True
        for p in papers():
            expected_cites = cited_counts().get(p.no, 0)
            try:
                cited_by = graph.get_node_edges(
                    p.vid, direction="out", edge_type="CITED_BY", limit=100
                )
                cites_in = graph.get_node_edges(p.vid, direction="in", edge_type="CITES", limit=100)
            except Exception:  # noqa: BLE001
                citation_edges_ok = False
                continue
            if len(cited_by or []) != expected_cites or len(cites_in or []) != expected_cites:
                citation_edges_ok = False
            for edge in cited_by or []:
                if not str(getattr(edge, "target_id", "") or "").startswith("paper_8899"):
                    citation_edges_ok = False
            if int(relation_citations.get(p.mysql_id, 0)) != expected_cites:
                citation_edges_ok = False
        # 论文主题链路：每篇种子论文的 HAS_KEYWORD 出边数 = 源表关键词数，
        # 且关键词目标节点真实存在（keyword_{md5} 共享维度节点）。
        keyword_edges_ok = True
        keyword_sample: list[str] = []
        for p in papers():
            try:
                kw_edges = graph.get_node_edges(
                    p.vid, direction="out", edge_type="HAS_KEYWORD", limit=50
                )
            except Exception:  # noqa: BLE001
                keyword_edges_ok = False
                continue
            if len(kw_edges or []) != len(p.fields):
                keyword_edges_ok = False
            for edge in kw_edges or []:
                kvid = str(getattr(edge, "target_id", "") or "")
                knode = graph.get_node(kvid) if kvid else None
                kprops = (knode.properties if knode else None) or {}
                if not kprops.get("keyword"):
                    keyword_edges_ok = False
                elif kprops["keyword"] not in keyword_sample:
                    keyword_sample.append(str(kprops["keyword"]))
        # 研究方向回退：有成果领域的专家，Person.research_fields 必须非空。
        research_fields_ok = True
        for person_no in research_fields_by_person():
            node = graph.get_node(people()[person_no - 1].vid)
            if not ((node.properties if node else None) or {}).get("research_fields"):
                research_fields_ok = False
        # 期刊分级链路：每篇种子论文恰有 1 条 PUBLISHED_IN 出边，目标 Journal 节点
        # 存在且刊名/SCI/JCR 分区标记与定义一致（级别显示 JCR/中文核心/未分级的数据基础）。
        published_in_ok = True
        venue_sample: list[str] = []
        for p in papers():
            definition = journals()[p.journal - 1]
            try:
                pub_edges = graph.get_node_edges(
                    p.vid, direction="out", edge_type="PUBLISHED_IN", limit=10
                )
            except Exception:  # noqa: BLE001
                published_in_ok = False
                continue
            if len(pub_edges or []) != 1:
                published_in_ok = False
                continue
            jvid = str(getattr(pub_edges[0], "target_id", "") or "")
            jnode = graph.get_node(jvid) if jvid else None
            jprops = (jnode.properties if jnode else None) or {}
            if jprops.get("name_zh") != definition.zh_name or str(
                jprops.get("is_sci") or "0"
            ) != str(definition.is_sci):
                published_in_ok = False
            if jprops.get("jcr_zone") != definition.jcr_zone:
                published_in_ok = False
            if definition.jcr_zone:
                level = f"JCR-{definition.jcr_zone}"
            elif definition.is_sci:
                level = "SCI"
            else:
                level = definition.zh_core or "未分级"
            label = f"{definition.zh_name}（{level}）"
            if label not in venue_sample:
                venue_sample.append(label)
    finally:
        close_trs_graph_client()
    ok = (
        mysql_counts == {k: expected[k] for k in mysql_counts}
        and graph_nodes == mysql_counts
        and encoding_errors == 0
        and not field_mismatches
        and studied_ok
        and citation_rows == expected["citationRows"]
        and citation_edges_ok
        and classification_rows == expected["classificationRows"]
        and research_rows == expected["researchDirectionRows"]
        and journal_rows == expected["journalRows"]
        and keyword_edges_ok
        and research_fields_ok
        and published_in_ok
    )
    return {
        "ok": ok,
        "batch": BATCH,
        "mysql": mysql_counts,
        "graph": graph_nodes,
        "encodingErrors": encoding_errors,
        "fieldMismatches": field_mismatches,
        "studiedAtSampleOk": studied_ok,
        "citationRows": citation_rows,
        "citationEdgesOk": citation_edges_ok,
        "classificationRows": classification_rows,
        "researchDirectionRows": research_rows,
        "journalRows": journal_rows,
        "keywordEdgesOk": keyword_edges_ok,
        "keywordSample": sorted(keyword_sample),
        "researchFieldsOk": research_fields_ok,
        "publishedInOk": published_in_ok,
        "venueSample": venue_sample,
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
