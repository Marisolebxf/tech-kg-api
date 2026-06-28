from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict
from typing import Any

import pymysql

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.base_module import KGModuleScaffoldService


TOPIC_ALIAS_MAP = {
    "academic graph": "学术图谱",
    "scholarly graph": "学术图谱",
    "knowledge graph": "知识图谱",
    "collaboration network": "合作网络",
    "coauthorship network": "合作网络",
    "community detection": "社区发现",
    "network evolution": "网络演化",
    "scholarly evaluation": "学术评价",
    "academic evaluation": "学术评价",
    "research evaluation": "科研评价",
    "impact evaluation": "影响力评估",
    "h index": "h指数",
    "h-index": "h指数",
    "core team": "团队识别",
    "stable team": "团队识别",
    "core personnel": "团队识别",
    "team identification": "团队识别",
    "cross-institution collaboration": "跨机构合作",
    "graph alignment": "图谱对齐",
}

TOPIC_EXCLUDE_SET = {
    "科研评价",
    "学术评价",
    "影响力评估",
    "影响力评价",
    "h指数",
    "h-index",
    "核心团队",
    "核心人员",
    "稳定团队",
    "团队识别",
    "核心合作人员",
}

SHARED_CONTRIBUTION_THEME_MAP = {
    "知识图谱": "知识图谱联合研究",
    "学术图谱": "学术图谱联合研究",
    "合作网络": "合作网络分析方法研究",
    "社区发现": "社区发现方法研究",
    "网络演化": "合作网络演化研究",
    "跨机构合作": "跨机构协同研究",
}


class ExpertPaperCooperationService(KGModuleScaffoldService):
    module_code = "expert_paper_cooperation"

    def analyze_demo(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return _build_analyze_result(body)

    def analyze_mysql_demo(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return _build_analyze_result(body)

    def build_structured_result_only(
        self, body: ExpertPaperCooperationDemoRequest
    ) -> dict[str, Any]:
        result = _build_analyze_result(body)
        return {"structuredResult": result["structuredResult"]}

    def build_graph_view(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        result = _build_analyze_result(body)
        structured = result["structuredResult"]
        citation = structured["citation"]
        contribution_cards: list[str] = []
        if structured["journalLevelCount"] or structured["conferenceLevelCount"]:
            contribution_cards.append(
                _format_level_summary(
                    structured["journalLevelCount"], structured["conferenceLevelCount"]
                )
            )
        contribution_cards.append(f"总被引{citation['total']}")
        contribution_cards.append(f"最高{citation['max']}")
        contribution_cards.append(f"评分{structured['academicImpactScore']}")

        return {
            "taskName": "科技专家论文合作关系图谱视图",
            "input": body.model_dump(),
            "nodes": [
                {
                    "id": "expertA",
                    "type": "expert",
                    "label": f"专家A：{result['expertA']['name']}",
                    "subtitle": result["expertA"]["organization"],
                    "color": "blue",
                    "x": 120,
                    "y": 80,
                    "items": [],
                    "data": result["expertA"],
                },
                {
                    "id": "expertB",
                    "type": "expert",
                    "label": f"专家B：{result['expertB']['name']}",
                    "subtitle": result["expertB"]["organization"],
                    "color": "green",
                    "x": 760,
                    "y": 80,
                    "items": [],
                    "data": result["expertB"],
                },
                {
                    "id": "cooperation",
                    "type": "summary",
                    "label": "合作论文",
                    "subtitle": f"共同论文{structured['cooperationPaperCount']}篇 / 合作频次{structured['cooperationFrequency']}次",
                    "color": "purple",
                    "x": 430,
                    "y": 290,
                    "items": [],
                    "data": {},
                },
                {
                    "id": "topics",
                    "type": "topicGroup",
                    "label": "论文主题",
                    "subtitle": None,
                    "color": "green",
                    "x": 110,
                    "y": 570,
                    "items": structured["paperTopics"],
                    "data": {"distribution": result["topicDistribution"]},
                },
                {
                    "id": "period",
                    "type": "period",
                    "label": "合作周期",
                    "subtitle": structured["cooperationTimeRange"]["displayText"],
                    "color": "orange",
                    "x": 500,
                    "y": 610,
                    "items": [],
                    "data": {"yearDistribution": result["yearDistribution"]},
                },
                {
                    "id": "contribution",
                    "type": "contribution",
                    "label": "共同贡献",
                    "subtitle": None,
                    "color": "orange",
                    "x": 810,
                    "y": 590,
                    "items": contribution_cards,
                    "data": result["sharedContribution"],
                },
            ],
            "edges": [
                {
                    "source": "expertA",
                    "target": "expertB",
                    "label": "论文合作",
                    "color": "purple",
                    "lineType": "solid",
                    "data": {},
                },
                {
                    "source": "expertA",
                    "target": "cooperation",
                    "label": "",
                    "color": "blue",
                    "lineType": "solid",
                    "data": {},
                },
                {
                    "source": "expertB",
                    "target": "cooperation",
                    "label": "",
                    "color": "green",
                    "lineType": "solid",
                    "data": {},
                },
                {
                    "source": "cooperation",
                    "target": "topics",
                    "label": "",
                    "color": "green",
                    "lineType": "solid",
                    "data": {},
                },
                {
                    "source": "cooperation",
                    "target": "period",
                    "label": "",
                    "color": "gray",
                    "lineType": "dashed",
                    "data": {},
                },
                {
                    "source": "cooperation",
                    "target": "contribution",
                    "label": "",
                    "color": "orange",
                    "lineType": "solid",
                    "data": {},
                },
            ],
            "metrics": {
                "paperCount": structured["cooperationPaperCount"],
                "citationTotal": citation["total"],
                "citationMax": citation["max"],
                "cooperationFrequency": structured["cooperationFrequency"],
                "academicImpactScore": structured["academicImpactScore"],
            },
            "structuredResult": structured,
            "source": {
                "mode": "mysql_demo_graph_view",
                "baseEndpoint": "/api/v1/kg-construction/expert-paper-cooperation-relations/demo/analyze",
                "mysqlDatabase": _paper_coop_database(),
                "mysqlTables": [
                    "scholar",
                    "paper",
                    "paper_author",
                    "venue",
                    "scholar_paper_cooperation",
                ],
            },
        }


def _paper_coop_database() -> str:
    return (
        os.getenv("PAPER_COOP_MYSQL_DATABASE")
        or os.getenv("LOCAL_MYSQL_DATABASE")
        or os.getenv("MYSQL_DATABASE")
        or "techkg"
    )


def _paper_coop_mysql_settings() -> dict[str, Any]:
    return {
        "host": os.getenv("PAPER_COOP_MYSQL_HOST") or os.getenv("LOCAL_MYSQL_HOST") or "127.0.0.1",
        "port": int(os.getenv("PAPER_COOP_MYSQL_PORT") or os.getenv("LOCAL_MYSQL_PORT") or 3306),
        "user": os.getenv("PAPER_COOP_MYSQL_USERNAME")
        or os.getenv("LOCAL_MYSQL_USERNAME")
        or "root",
        "password": os.getenv("PAPER_COOP_MYSQL_PASSWORD")
        or os.getenv("LOCAL_MYSQL_PASSWORD")
        or "123456789",
        "database": _paper_coop_database(),
        "charset": "utf8mb4",
        "autocommit": True,
    }


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    return int(value[:4])


def _sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return [str(value)] if str(value).strip() else []
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return [str(parsed)] if str(parsed).strip() else []


def _json_dict(value: Any) -> dict[str, int]:
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(key): int(val) for key, val in value.items()}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): int(val) for key, val in parsed.items()}


def _json_object_list(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _normalize_topic(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in TOPIC_ALIAS_MAP:
        return TOPIC_ALIAS_MAP[lowered]
    return value


def _is_research_topic(topic: str) -> bool:
    value = topic.strip()
    if not value:
        return False
    return value.lower() not in TOPIC_EXCLUDE_SET and value not in TOPIC_EXCLUDE_SET


def _run_mysql_json_query(sql: str) -> list[dict[str, Any]]:
    settings = _paper_coop_mysql_settings()
    try:
        connection = pymysql.connect(**settings)
    except pymysql.MySQLError as exc:
        raise RuntimeError(
            f"论文合作关系 MySQL 连接失败: {settings['host']}:{settings['port']}/{settings['database']} - {exc}"
        ) from exc

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    except pymysql.MySQLError as exc:
        raise RuntimeError(f"论文合作关系 MySQL 查询失败: {exc}") from exc
    finally:
        connection.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        payload = row[0] if isinstance(row, tuple) else next(iter(row.values()))
        if payload:
            result.append(json.loads(payload))
    return result


def _source_filter_sql(data_source: str) -> str:
    if data_source == "web_of_science":
        return " AND p.paper_language = 'en'"
    if data_source in {"cnki", "wanfang"}:
        return " AND p.paper_language = 'cn'"
    return ""


def _sql_in(values: list[str]) -> str:
    if not values:
        return "('')"
    return "(" + ", ".join(_sql_literal(value) for value in values) + ")"


def _empty_distribution(start_year: int, end_year: int) -> list[dict[str, int]]:
    return [
        {"year": year, "paperCount": 0, "citationCount": 0}
        for year in range(start_year, end_year + 1)
    ]


def _build_expert_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "expertId": row["scholarId"],
        "name": row["name"],
        "organization": row.get("organization") or "未知机构",
        "title": row.get("title") or "未知职称",
        "researchDirection": _json_list(row.get("researchDirection")),
        "paperCount": int(row.get("paperCount") or 0),
        "citationCount": int(row.get("citationCount") or 0),
        "hIndex": float(row.get("hIndex") or 0),
    }


def _fetch_experts(expert_a_id: str, expert_b_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sql = f"""
    SELECT JSON_OBJECT(
        'scholarId', scholar_id,
        'name', name_zh,
        'organization', org_name_zh,
        'title', title,
        'researchDirection', research_direction,
        'paperCount', paper_nums,
        'citationCount', citation_nums,
        'hIndex', h_index
    )
    FROM scholar
    WHERE scholar_id IN ({_sql_literal(expert_a_id)}, {_sql_literal(expert_b_id)});
    """
    rows = _run_mysql_json_query(sql)
    by_id = {row["scholarId"]: row for row in rows}
    if expert_a_id not in by_id or expert_b_id not in by_id:
        raise ValueError("MySQL techkg 中不存在输入的专家ID")
    return _build_expert_payload(by_id[expert_a_id]), _build_expert_payload(by_id[expert_b_id])


def _fetch_pair_summary(expert_a_id: str, expert_b_id: str) -> dict[str, Any]:
    sql = f"""
    SELECT JSON_OBJECT(
        'expertAId', expert_a_id,
        'expertBId', expert_b_id,
        'paperCount', paper_count,
        'firstYear', first_year,
        'lastYear', last_year,
        'citationTotal', citation_total,
        'citationMax', citation_max,
        'cooperationFrequency', cooperation_frequency,
        'academicImpactScore', academic_impact_score,
        'journalLevelCount', journal_level_count_json,
        'conferenceLevelCount', conference_level_count_json,
        'commonTopics', common_topics_json,
        'authorUnits', author_units_json,
        'teamFlag', team_flag,
        'stableTeamName', stable_team_name,
        'stableTeamMembers', stable_team_members_json,
        'coreCollaborators', core_collaborators_json,
        'sharedContribution', shared_contribution_json
    )
    FROM scholar_paper_cooperation
    WHERE (expert_a_id = {_sql_literal(expert_a_id)} AND expert_b_id = {_sql_literal(expert_b_id)})
       OR (expert_a_id = {_sql_literal(expert_b_id)} AND expert_b_id = {_sql_literal(expert_a_id)})
    LIMIT 1;
    """
    rows = _run_mysql_json_query(sql)
    return rows[0] if rows else {}


def _fetch_shared_papers(body: ExpertPaperCooperationDemoRequest) -> list[dict[str, Any]]:
    start_year = _parse_year(body.startTime)
    end_year = _parse_year(body.endTime)
    filters: list[str] = []
    if start_year is not None:
        filters.append(f"p.publish_year >= {start_year}")
    if end_year is not None:
        filters.append(f"p.publish_year <= {end_year}")
    filters_sql = "".join(f" AND {item}" for item in filters) + _source_filter_sql(body.dataSource)

    sql = f"""
    SELECT JSON_OBJECT(
        'paperId', p.paper_id,
        'title', p.title,
        'paperLanguage', p.paper_language,
        'publishYear', p.publish_year,
        'publishDate', DATE_FORMAT(p.publish_date, '%Y-%m-%d'),
        'venueId', p.venue_id,
        'venue', COALESCE(p.venue_name, v.venue_name, '未知期刊/会议'),
        'venueType', COALESCE(p.venue_type, v.venue_type, 'journal'),
        'venueLevel', COALESCE(p.venue_level, v.venue_level, '未分级'),
        'citationCount', COALESCE(p.citation_count, 0),
        'keywords', p.keywords,
        'doi', p.doi,
        'paperUrl', p.paper_url,
        'abstractText', p.abstract_text
    )
    FROM paper p
    JOIN paper_author pa ON pa.paper_id = p.paper_id AND pa.scholar_id = {_sql_literal(body.expertAId)}
    JOIN paper_author pb ON pb.paper_id = p.paper_id AND pb.scholar_id = {_sql_literal(body.expertBId)}
    LEFT JOIN venue v ON v.venue_id = p.venue_id
    WHERE 1 = 1 {filters_sql}
    ORDER BY p.publish_year ASC, COALESCE(p.citation_count, 0) DESC, p.paper_id;
    """
    return _run_mysql_json_query(sql)


def _fetch_paper_authors(paper_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not paper_ids:
        return {}
    sql = f"""
    SELECT JSON_OBJECT(
        'paperId', paper_id,
        'scholarId', scholar_id,
        'authorName', author_name,
        'authorOrder', author_order,
        'orgName', org_name,
        'isCorresponding', is_corresponding,
        'authorRole', author_role
    )
    FROM paper_author
    WHERE paper_id IN {_sql_in(paper_ids)}
    ORDER BY paper_id, author_order;
    """
    rows = _run_mysql_json_query(sql)
    by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_paper[row["paperId"]].append(
            {
                "scholarId": row.get("scholarId"),
                "name": row.get("authorName"),
                "order": int(row.get("authorOrder") or 0),
                "organization": row.get("orgName"),
                "isCorresponding": bool(int(row.get("isCorresponding") or 0)),
                "role": row.get("authorRole") or "",
            }
        )
    return dict(by_paper)


def _format_level_summary(journal_levels: dict[str, int], conference_levels: dict[str, int]) -> str:
    parts: list[str] = []
    if journal_levels:
        parts.extend(f"{key}×{value}" for key, value in journal_levels.items())
    if conference_levels:
        parts.extend(f"{key}×{value}" for key, value in conference_levels.items())
    return " / ".join(parts)


def _score_paper(paper: dict[str, Any]) -> float:
    level = paper.get("venueLevel") or ""
    level_weight = {
        "CCF-A": 12,
        "CCF-A1": 12,
        "CCF-A2": 10,
        "CCF-B": 8,
        "CCF-B1": 8,
        "CCF-C": 5,
    }.get(level, 4)
    return float(level_weight + int(paper.get("citationCount") or 0) / 12)


def _build_analyze_result(body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
    expert_a, expert_b = _fetch_experts(body.expertAId, body.expertBId)
    pair_summary = _fetch_pair_summary(body.expertAId, body.expertBId)
    paper_rows = _fetch_shared_papers(body)
    author_map = _fetch_paper_authors([row["paperId"] for row in paper_rows])

    papers: list[dict[str, Any]] = []
    topic_counter: Counter[str] = Counter()
    year_counter: dict[int, dict[str, int]] = defaultdict(
        lambda: {"paperCount": 0, "citationCount": 0}
    )
    journal_level_counter: Counter[str] = Counter()
    conference_level_counter: Counter[str] = Counter()
    coauthor_counter: Counter[str] = Counter()
    coauthor_meta: dict[str, dict[str, Any]] = {}
    citation_total = 0
    citation_max = 0

    for row in paper_rows:
        raw_topics = _json_list(row.get("keywords"))
        topics = [_normalize_topic(item) for item in raw_topics]
        authors = author_map.get(row["paperId"], [])
        paper = {
            "paperId": row["paperId"],
            "title": row.get("title") or "未命名论文",
            "year": int(row.get("publishYear") or 0),
            "publishDate": row.get("publishDate"),
            "venue": row.get("venue") or "未知期刊/会议",
            "venueType": row.get("venueType") or "journal",
            "venueLevel": row.get("venueLevel") or "未分级",
            "citationCount": int(row.get("citationCount") or 0),
            "topics": topics,
            "doi": row.get("doi"),
            "paperUrl": row.get("paperUrl"),
            "abstractText": row.get("abstractText"),
            "authors": authors,
        }
        papers.append(paper)

        topic_counter.update(topic for topic in topics if _is_research_topic(topic))
        citation_total += paper["citationCount"]
        citation_max = max(citation_max, paper["citationCount"])
        year_counter[paper["year"]]["paperCount"] += 1
        year_counter[paper["year"]]["citationCount"] += paper["citationCount"]

        if "conference" in (paper["venueType"] or "").lower():
            conference_level_counter[paper["venueLevel"]] += 1
        else:
            journal_level_counter[paper["venueLevel"]] += 1

        paper_topics = [topic for topic in topics if _is_research_topic(topic)][:4]
        for author in authors:
            scholar_id = author.get("scholarId")
            if scholar_id in {body.expertAId, body.expertBId} or not scholar_id:
                continue
            coauthor_counter[scholar_id] += 1
            meta = coauthor_meta.setdefault(
                scholar_id,
                {
                    "expertId": scholar_id,
                    "name": author.get("name"),
                    "organization": author.get("organization"),
                    "sharedPaperCount": 0,
                    "topics": Counter(),
                },
            )
            meta["sharedPaperCount"] += 1
            meta["topics"].update(paper_topics)

    paper_count = len(papers)
    if paper_count == 0:
        citation_total = int(pair_summary.get("citationTotal") or 0)
        citation_max = int(pair_summary.get("citationMax") or 0)

    years = [paper["year"] for paper in papers if paper["year"]]
    start_year = (
        min(years)
        if years
        else int(pair_summary.get("firstYear") or _parse_year(body.startTime) or 0)
    )
    end_year = (
        max(years) if years else int(pair_summary.get("lastYear") or _parse_year(body.endTime) or 0)
    )

    topic_list = [name for name, _ in topic_counter.most_common()]
    if not topic_list:
        topic_list = [
            _normalize_topic(item)
            for item in _json_list(pair_summary.get("commonTopics"))
            if _is_research_topic(_normalize_topic(item))
        ]

    if not journal_level_counter:
        journal_level_counter.update(_json_dict(pair_summary.get("journalLevelCount")))
    if not conference_level_counter:
        conference_level_counter.update(_json_dict(pair_summary.get("conferenceLevelCount")))

    journal_level_dict = dict(journal_level_counter)
    conference_level_dict = dict(conference_level_counter)
    journal_summary = _format_level_summary(journal_level_dict, conference_level_dict)

    coauthor_items = sorted(
        (
            {
                "expertId": meta["expertId"],
                "name": meta["name"],
                "organization": meta["organization"],
                "sharedPaperCount": meta["sharedPaperCount"],
                "topics": [name for name, _ in meta["topics"].most_common(4)],
            }
            for meta in coauthor_meta.values()
        ),
        key=lambda item: (-item["sharedPaperCount"], item["name"] or ""),
    )
    if not coauthor_items:
        coauthor_items = _json_object_list(pair_summary.get("coreCollaborators"))

    stable_team_threshold = 2 if paper_count >= 2 else math.inf
    stable_team_members = [
        item for item in coauthor_items if item["sharedPaperCount"] >= stable_team_threshold
    ]
    if not stable_team_members:
        stable_team_members = _json_object_list(pair_summary.get("stableTeamMembers"))

    shared_contribution_tags: list[str] = []
    if paper_count:
        venue_weight_score = sum(_score_paper(paper) for paper in papers)
        average_venue_score = venue_weight_score / max(1, paper_count)
        if average_venue_score >= 70:
            shared_contribution_tags.append("高水平论文产出")
        else:
            shared_contribution_tags.append("联合论文产出")

        if citation_total >= 100:
            shared_contribution_tags.append("高被引合作成果")
        elif citation_total > 0:
            shared_contribution_tags.append("持续学术影响")

        if expert_a["organization"] != expert_b["organization"]:
            shared_contribution_tags.append("跨机构协同研究")

        for topic in topic_list:
            mapped = SHARED_CONTRIBUTION_THEME_MAP.get(topic)
            if mapped and mapped not in shared_contribution_tags:
                shared_contribution_tags.append(mapped)
            if len(shared_contribution_tags) >= 4:
                break

    if not shared_contribution_tags:
        shared_contribution_tags = [
            tag for tag in _json_list(pair_summary.get("sharedContribution")) if tag
        ]

    if paper_count:
        venue_weight_score = sum(_score_paper(paper) for paper in papers)
        academic_impact_score = min(
            99.5,
            round(
                paper_count * 6.5
                + citation_total / max(18, paper_count * 3)
                + venue_weight_score / max(1, paper_count)
                + len(stable_team_members) * 1.8,
                1,
            ),
        )
    else:
        academic_impact_score = float(pair_summary.get("academicImpactScore") or 0)

    cooperation_frequency = paper_count or int(pair_summary.get("cooperationFrequency") or 0)

    structured_result = {
        "authorList": [expert_a["name"], expert_b["name"]],
        "authorUnits": [expert_a["organization"], expert_b["organization"]],
        "cooperationTimeRange": {
            "startYear": int(start_year) if start_year else 0,
            "endYear": int(end_year) if end_year else 0,
            "displayText": f"{int(start_year)} - {int(end_year)}"
            if start_year and end_year
            else "",
        },
        "paperTopics": topic_list[:8],
        "cooperationPaperCount": paper_count,
        "journalLevelCount": journal_level_dict,
        "conferenceLevelCount": conference_level_dict,
        "citation": {"total": citation_total, "max": citation_max},
        "cooperationFrequency": cooperation_frequency,
        "academicImpactScore": float(academic_impact_score),
        "stableTeamName": pair_summary.get("stableTeamName")
        or (f"{expert_a['name']}—{expert_b['name']}长期合作团队" if stable_team_members else None),
        "stableTeamMembers": [item["name"] for item in stable_team_members],
        "coreCollaborators": [item["name"] for item in coauthor_items[:5]],
        "sharedContribution": shared_contribution_tags,
    }

    if start_year and end_year:
        year_distribution = _empty_distribution(start_year, end_year)
        year_map = {item["year"]: item for item in year_distribution}
        for year, values in year_counter.items():
            if year in year_map:
                year_map[year].update(values)
    else:
        year_distribution = [
            {"year": year, **values} for year, values in sorted(year_counter.items())
        ]

    return {
        "taskName": "科技专家论文合作关系",
        "input": body.model_dump(),
        "expertA": expert_a,
        "expertB": expert_b,
        "structuredResult": structured_result,
        "papers": papers,
        "topicDistribution": [
            {"name": name, "value": value} for name, value in topic_counter.most_common()
        ],
        "yearDistribution": year_distribution,
        "stableTeam": {
            "teamFlag": bool(pair_summary.get("teamFlag")) or bool(stable_team_members),
            "teamName": structured_result["stableTeamName"],
            "members": stable_team_members,
        },
        "coreCollaborators": coauthor_items[:5],
        "sharedContribution": {
            "tags": shared_contribution_tags,
            "venueSummary": journal_summary,
            "citationSummary": f"总被引{citation_total} / 最高{citation_max}",
            "impactSummary": f"评分{academic_impact_score}",
        },
        "apiResultExample": {
            "endpoint": "/api/v1/kg-construction/expert-paper-cooperation-relations/demo/analyze",
            "method": "POST",
            "sourceMode": "mysql_demo_tables",
            "mysqlDatabase": _paper_coop_database(),
            "mysqlTables": [
                "scholar",
                "paper",
                "paper_author",
                "venue",
                "scholar_paper_cooperation",
            ],
            "note": "结构化结果与图谱预览均来源于 MySQL 合作论文原始数据聚合。",
        },
    }
