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

    def build_structured_result_only(
        self, body: ExpertPaperCooperationDemoRequest
    ) -> dict[str, Any]:
        result = _build_analyze_result(body)
        return {"structuredResult": result["structuredResult"]}


def _paper_coop_database() -> str:
    return (
        os.getenv("PAPER_COOP_MYSQL_DATABASE") or os.getenv("LOCAL_MYSQL_DATABASE") or "gkx_local"
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
        return " AND COALESCE(p.en_name, '') <> ''"
    if data_source in {"cnki", "wanfang"}:
        return " AND COALESCE(p.zh_name, '') <> ''"
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


def _is_usable_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    question_count = text.count("?") + text.count("�")
    return question_count == 0 or question_count / max(1, len(text)) < 0.25


def _pick_text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text and _is_usable_text(text):
            return text
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _split_semicolon_text(value: Any) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for chunk in str(value).replace("；", ";").split(";"):
        item = chunk.strip()
        if item and item not in items:
            items.append(item)
    return items


def _parse_author_names(value: Any) -> list[str]:
    if not value:
        return []
    normalized = str(value).replace("；", ",").replace(";", ",")
    names: list[str] = []
    for chunk in normalized.split(","):
        name = chunk.strip()
        if name and name not in names:
            names.append(name)
    return names


def _infer_venue_type(row: dict[str, Any]) -> str:
    raw = str(row.get("venueType") or "").lower()
    venue = str(row.get("venue") or "").lower()
    if "conference" in raw or "proceeding" in raw:
        return "conference"
    conference_tokens = ["conference", "proceedings", "cvpr", "iccv", "eccv", "aaai", "ijcai"]
    if any(token in venue for token in conference_tokens):
        return "conference"
    return "journal"


def _infer_venue_level(row: dict[str, Any]) -> str:
    jcr_zone = str(row.get("jcrZone") or "").strip()
    if jcr_zone:
        return f"JCR-{jcr_zone}"
    scope_zone = str(row.get("scopeZone") or "").strip()
    if scope_zone:
        return f"中科院-{scope_zone}"
    sub_quartile = row.get("subQuartile")
    if sub_quartile not in {None, ""}:
        return f"分区-{sub_quartile}"
    if int(row.get("top") or 0) == 1:
        return "Top期刊"
    if int(row.get("isSci") or 0) == 1:
        return "SCI"
    return "未分级"


def _build_level_count_key(paper: dict[str, Any]) -> str:
    level = paper.get("venueLevel") or "未分级"
    impact = paper.get("impactFactor")
    if impact not in {None, "", 0} and level == "未分级":
        return "IF收录"
    return level


def _build_expert_payload(row: dict[str, Any]) -> dict[str, Any]:
    research_direction = _split_semicolon_text(row.get("researchDirection"))
    return {
        "expertId": row["scholarId"],
        "name": _pick_text(row.get("nameZh"), row.get("nameEn"), default=row["scholarId"]),
        "organization": _pick_text(
            row.get("organizationZh"), row.get("organizationEn"), default="未知机构"
        ),
        "title": row.get("title") or "科技专家",
        "researchDirection": research_direction,
        "paperCount": int(row.get("paperCount") or 0),
        "citationCount": int(row.get("citationCount") or 0),
        "hIndex": float(row.get("hIndex") or 0),
    }


def _fetch_experts(expert_a_id: str, expert_b_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    sql = f"""
    SELECT JSON_OBJECT(
        'scholarId', s.scholar_id,
        'nameZh', s.name_zh,
        'nameEn', s.name_en,
        'organizationZh', s.scholar_org_name_zh,
        'organizationEn', s.scholar_org_name_en,
        'researchDirection', rd.fields,
        'paperCount', s.paper_nums,
        'citationCount', s.citation_nums,
        'hIndex', s.h_index
    )
    FROM dwd_scholar s
    LEFT JOIN dwd_scholar_research_direction rd ON rd.scholar_id = s.scholar_id
    WHERE s.scholar_id IN ({_sql_literal(expert_a_id)}, {_sql_literal(expert_b_id)})
      AND s.status = 1;
    """
    rows = _run_mysql_json_query(sql)
    by_id = {row["scholarId"]: row for row in rows}
    if expert_a_id not in by_id or expert_b_id not in by_id:
        raise ValueError("gkx_local 中不存在输入的专家ID，请使用 dwd_scholar.scholar_id")
    return _build_expert_payload(by_id[expert_a_id]), _build_expert_payload(by_id[expert_b_id])


def _fetch_pair_summary(expert_a_id: str, expert_b_id: str) -> dict[str, Any]:
    sql = f"""
    SELECT JSON_OBJECT(
        'cooperationFrequency', COALESCE(MAX(co_paper_count), 0)
    )
    FROM dwd_scholar_coauthor
    WHERE status = 1
      AND ((scholar_id = {_sql_literal(expert_a_id)} AND co_scholar_id = {_sql_literal(expert_b_id)})
        OR (scholar_id = {_sql_literal(expert_b_id)} AND co_scholar_id = {_sql_literal(expert_a_id)}));
    """
    rows = _run_mysql_json_query(sql)
    return rows[0] if rows else {}


def _fetch_shared_papers(body: ExpertPaperCooperationDemoRequest) -> list[dict[str, Any]]:
    start_year = _parse_year(body.startTime)
    end_year = _parse_year(body.endTime)
    filters: list[str] = ["r1.status = 1", "r2.status = 1", "p.status = 1"]
    if start_year is not None:
        filters.append(f"r1.year >= {start_year}")
    if end_year is not None:
        filters.append(f"r1.year <= {end_year}")
    filters_sql = " AND ".join(filters) + _source_filter_sql(body.dataSource)

    sql = f"""
    SELECT JSON_OBJECT(
        'paperId', p.id,
        'titleZh', p.zh_name,
        'titleEn', p.en_name,
        'publishYear', r1.year,
        'publishDate', DATE_FORMAT(COALESCE(r1.publish_time, r2.publish_time, p.cover_date_start), '%Y-%m-%d'),
        'venueId', r1.publication_id,
        'venue', COALESCE(NULLIF(p.publication_en_name, ''), ej.en_name, zj.en_name, zj.zh_name, '未知期刊/会议'),
        'venueType', COALESCE(ej.publication_type, zj.publication_type, ''),
        'jcrZone', ej.jcr_zone,
        'scopeZone', zj.scope_zone,
        'subQuartile', zj.sub_quartile,
        'top', COALESCE(ej.top, 0),
        'isSci', COALESCE(ej.is_sci, zj.is_sci, 0),
        'impactFactor', COALESCE(ej.impact_factor, zj.impact_factor, 0),
        'citationCount', GREATEST(COALESCE(r1.citations, 0), COALESCE(r2.citations, 0)),
        'authors', p.authors,
        'doi', p.doi,
        'paperUrl', p.paper_url,
        'abstractText', COALESCE(NULLIF(p.zh_abstract, ''), p.en_abstract, '')
    )
    FROM dwd_scholar_paper_relation r1
    JOIN dwd_scholar_paper_relation r2
      ON r1.paper_id = r2.paper_id
     AND r2.scholar_id = {_sql_literal(body.expertBId)}
    JOIN dwd_scholar_papers p ON p.id = r1.paper_id
    LEFT JOIN dwd_en_journal ej ON ej.id = r1.publication_id
    LEFT JOIN dwd_zh_journal zj ON zj.id = r1.publication_id
    WHERE r1.scholar_id = {_sql_literal(body.expertAId)}
      AND {filters_sql}
    ORDER BY r1.year ASC, GREATEST(COALESCE(r1.citations, 0), COALESCE(r2.citations, 0)) DESC, p.id
    LIMIT 1000;
    """
    return _run_mysql_json_query(sql)


def _fetch_paper_authors(paper_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for row in paper_rows:
        authors: list[dict[str, Any]] = []
        for index, name in enumerate(_parse_author_names(row.get("authors")), start=1):
            authors.append(
                {
                    "scholarId": None,
                    "name": name,
                    "order": index,
                    "organization": None,
                    "isCorresponding": False,
                    "role": "",
                }
            )
        by_paper[str(row["paperId"])] = authors
    return by_paper


def _fetch_pair_core_coauthors(expert_a_id: str, expert_b_id: str) -> list[dict[str, Any]]:
    sql = f"""
    SELECT JSON_OBJECT(
        'expertId', ca.co_scholar_id,
        'nameZh', ca.co_scholar_name_zh,
        'nameEn', ca.co_scholar_name_en,
        'organizationZh', ca.co_scholar_org_name_zh,
        'organizationEn', ca.co_scholar_org_name_en,
        'sharedPaperCount', LEAST(COALESCE(ca.co_paper_count, 0), COALESCE(cb.co_paper_count, 0))
    )
    FROM dwd_scholar_coauthor ca
    JOIN dwd_scholar_coauthor cb ON cb.co_scholar_id = ca.co_scholar_id
    WHERE ca.scholar_id = {_sql_literal(expert_a_id)}
      AND cb.scholar_id = {_sql_literal(expert_b_id)}
      AND ca.status = 1
      AND cb.status = 1
      AND ca.co_scholar_id NOT IN ({_sql_literal(expert_a_id)}, {_sql_literal(expert_b_id)})
    ORDER BY LEAST(COALESCE(ca.co_paper_count, 0), COALESCE(cb.co_paper_count, 0)) DESC
    LIMIT 10;
    """
    rows = _run_mysql_json_query(sql)
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "expertId": row.get("expertId"),
                "name": _pick_text(row.get("nameZh"), row.get("nameEn"), default="未知合作者"),
                "organization": _pick_text(
                    row.get("organizationZh"), row.get("organizationEn"), default=""
                ),
                "sharedPaperCount": int(row.get("sharedPaperCount") or 0),
                "topics": [],
            }
        )
    return result


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
        "JCR-Q1": 12,
        "JCR-Q2": 9,
        "JCR-Q3": 6,
        "JCR-Q4": 4,
        "Top期刊": 10,
        "SCI": 7,
        "中科院-1": 10,
        "中科院-2": 8,
        "中科院-3": 6,
        "中科院-4": 4,
    }.get(level, 4)
    impact_factor = float(paper.get("impactFactor") or 0)
    return float(
        level_weight + min(10.0, impact_factor) + int(paper.get("citationCount") or 0) / 12
    )


def _build_analyze_result(body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
    expert_a, expert_b = _fetch_experts(body.expertAId, body.expertBId)
    pair_summary = _fetch_pair_summary(body.expertAId, body.expertBId)
    paper_rows = _fetch_shared_papers(body)
    author_map = _fetch_paper_authors(paper_rows)

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
        topics = []
        authors = author_map.get(str(row["paperId"]), [])
        venue_type = _infer_venue_type(row)
        venue_level = _infer_venue_level(row)
        paper = {
            "paperId": str(row["paperId"]),
            "title": _pick_text(row.get("titleZh"), row.get("titleEn"), default="未命名论文"),
            "year": int(row.get("publishYear") or 0),
            "publishDate": row.get("publishDate"),
            "venue": row.get("venue") or "未知期刊/会议",
            "venueType": venue_type,
            "venueLevel": venue_level,
            "impactFactor": float(row.get("impactFactor") or 0),
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
            conference_level_counter[_build_level_count_key(paper)] += 1
        else:
            journal_level_counter[_build_level_count_key(paper)] += 1

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
        a_topics = [_normalize_topic(item) for item in expert_a.get("researchDirection", [])]
        b_topics = [_normalize_topic(item) for item in expert_b.get("researchDirection", [])]
        common_topics = [topic for topic in a_topics if topic in set(b_topics)]
        topic_list = [
            topic for topic in common_topics + a_topics + b_topics if _is_research_topic(topic)
        ]
        topic_list = list(dict.fromkeys(topic_list))

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
        coauthor_items = _fetch_pair_core_coauthors(body.expertAId, body.expertBId)
    if not coauthor_items:
        excluded_names = {expert_a["name"], expert_b["name"]}
        author_counter: Counter[str] = Counter()
        for paper in papers:
            for author in paper["authors"]:
                name = author.get("name")
                if name and name not in excluded_names:
                    author_counter[name] += 1
        coauthor_items = [
            {
                "expertId": name,
                "name": name,
                "organization": "",
                "sharedPaperCount": count,
                "topics": [],
            }
            for name, count in author_counter.most_common(10)
        ]

    stable_team_threshold = 2 if paper_count >= 2 else math.inf
    stable_team_members = [
        item for item in coauthor_items if item["sharedPaperCount"] >= stable_team_threshold
    ][:5]
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
            "endpoint": "/api/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result",
            "method": "POST",
            "sourceMode": "mysql_demo_tables",
            "mysqlDatabase": _paper_coop_database(),
            "mysqlTables": [
                "dwd_scholar",
                "dwd_scholar_paper_relation",
                "dwd_scholar_papers",
                "dwd_scholar_coauthor",
                "dwd_scholar_research_direction",
                "dwd_en_journal",
                "dwd_zh_journal",
            ],
            "note": "结构化结果由 gkx_local 中专家-论文关系表自连接计算，并用专家研究方向与期刊信息补充展示字段。",
        },
    }
