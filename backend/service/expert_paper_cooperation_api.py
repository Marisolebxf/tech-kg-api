from __future__ import annotations

import asyncio
import os
from collections import Counter, defaultdict
from typing import Any

import httpx

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.base_module import KGModuleScaffoldService

MAX_SHARED_PAPERS = 1000
GRAPH_PAGE_SIZE = 200
GRAPH_SPACE = os.getenv("KG_GRAPH_SPACE", "dev")


class GraphSearchApiError(RuntimeError):
    """公开查图 API 调用失败。"""


class GraphSearchApiClient:
    """论文合作业务使用的公开 FastAPI 查图 API 客户端。"""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def __aenter__(self) -> GraphSearchApiClient:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, params=params, json=json)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", False):
            code = payload.get("code", 500)
            message = payload.get("msg") or "查图 API 返回失败"
            if code == 404:
                raise ValueError(message)
            raise GraphSearchApiError(message)
        return payload.get("data")

    async def get_node(self, node_id: str, *, space: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/graph-search/nodes/{node_id}",
            params={"space": space},
        )
        return data or {}

    async def search_paths(self, body: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/graph-search/paths/search", json=body)
        return data or {"items": [], "total": 0}

    async def get_subgraph(
        self,
        node_id: str,
        *,
        edge_type: str,
        direction: str,
        space: str,
        limit: int = 200,
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/graph-search/subgraph/{node_id}",
            params={
                "depth": 1,
                "limit": limit,
                "edge_type": edge_type,
                "direction": direction,
                "space": space,
            },
        )
        return data or {"nodes": [], "edges": []}


class ExpertPaperCooperationApiService(KGModuleScaffoldService):
    """仅通过 FastAPI 公开查图接口完成论文合作分析。"""

    module_code = "expert_paper_cooperation"

    async def build_structured_result_only(
        self,
        body: ExpertPaperCooperationDemoRequest,
        *,
        api_base_url: str,
    ) -> dict[str, Any]:
        async with GraphSearchApiClient(api_base_url) as graph_api:
            result = await _build_structured_result(graph_api, body)
        return {"structuredResult": result}


def _person_vid(expert_id: str) -> str:
    return expert_id if expert_id.startswith("person_") else f"person_{expert_id}"


def _display_name(node: dict[str, Any], fallback: str) -> str:
    props = node.get("properties") or {}
    return str(props.get("name_zh") or props.get("name_en") or fallback)


def _organization(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    return str(props.get("scholar_org") or "未知机构")


def _split_fields(value: Any) -> list[str]:
    if not value:
        return []
    normalized = str(value).replace("；", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _year_filters(body: ExpertPaperCooperationDemoRequest) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    if body.startTime:
        filters.append(
            {
                "property": "publication_year",
                "operator": "gte",
                "value": body.startTime[:4],
            }
        )
    if body.endTime:
        filters.append(
            {
                "property": "publication_year",
                "operator": "lte",
                "value": body.endTime[:4],
            }
        )
    return filters


def _path_request(
    body: ExpertPaperCooperationDemoRequest,
    *,
    offset: int,
) -> dict[str, Any]:
    return {
        "sourceId": _person_vid(body.expertAId),
        "targetId": _person_vid(body.expertBId),
        "steps": [
            {
                "edgeType": "AUTHORED_BY",
                "direction": "in",
                "targetLabel": "Paper",
                "targetFilters": _year_filters(body),
            },
            {
                "edgeType": "AUTHORED_BY",
                "direction": "out",
                "targetLabel": "Person",
                "targetFilters": [],
            },
        ],
        "limit": GRAPH_PAGE_SIZE,
        "offset": offset,
        "space": GRAPH_SPACE,
    }


async def _fetch_shared_paths(
    graph_api: GraphSearchApiClient,
    body: ExpertPaperCooperationDemoRequest,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while offset < MAX_SHARED_PAPERS:
        page = await graph_api.search_paths(_path_request(body, offset=offset))
        page_items = page.get("items") or []
        items.extend(page_items)
        total = int(page.get("total") or len(items))
        offset += len(page_items)
        if not page_items or offset >= total:
            break
    return items[:MAX_SHARED_PAPERS]


def _coauthor_request(
    body: ExpertPaperCooperationDemoRequest,
    *,
    directions: list[str],
) -> dict[str, Any]:
    return {
        "sourceId": _person_vid(body.expertAId),
        "targetId": _person_vid(body.expertBId),
        "steps": [
            {
                "edgeType": "COAUTHOR_WITH",
                "direction": direction,
                "targetLabel": "Person",
                "targetFilters": [],
            }
            for direction in directions
        ],
        "limit": GRAPH_PAGE_SIZE,
        "offset": 0,
        "space": GRAPH_SPACE,
    }


def _edge_cooperation_count(edge: dict[str, Any]) -> int:
    try:
        return int((edge.get("properties") or {}).get("co_paper_count") or 0)
    except (TypeError, ValueError):
        return 0


async def _fetch_coauthor_fallback(
    graph_api: GraphSearchApiClient,
    body: ExpertPaperCooperationDemoRequest,
) -> tuple[int, list[tuple[str, int]]]:
    """从已有合作边补足总量和共同合作者，不推断逐篇明细字段。"""
    direct, common = await asyncio.gather(
        graph_api.search_paths(_coauthor_request(body, directions=["out"])),
        graph_api.search_paths(_coauthor_request(body, directions=["out", "out"])),
    )

    direct_count = max(
        (
            _edge_cooperation_count(path["edges"][0])
            for path in direct.get("items") or []
            if path.get("edges")
        ),
        default=0,
    )

    collaborators: dict[str, int] = {}
    for path in common.get("items") or []:
        nodes = path.get("nodes") or []
        edges = path.get("edges") or []
        if len(nodes) < 3 or len(edges) < 2:
            continue
        name = _author_name(nodes[1])
        strength = min(_edge_cooperation_count(edges[0]), _edge_cooperation_count(edges[1]))
        collaborators[name] = max(collaborators.get(name, 0), strength)

    ranked = sorted(collaborators.items(), key=lambda item: (-item[1], item[0]))
    return direct_count, ranked[:5]


def _dedupe_shared_papers(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    papers: dict[str, dict[str, Any]] = {}
    for path in paths:
        nodes = path.get("nodes") or []
        if len(nodes) < 2:
            continue
        paper = nodes[1]
        paper_id = str(paper.get("id") or "")
        if not paper_id:
            continue
        item = papers.setdefault(
            paper_id,
            {
                "id": paper_id,
                "properties": paper.get("properties") or {},
                "pathEdges": path.get("edges") or [],
            },
        )
        if not item["properties"] and paper.get("properties"):
            item["properties"] = paper["properties"]
    return list(papers.values())


async def _fetch_paper_context(
    graph_api: GraphSearchApiClient,
    paper: dict[str, Any],
    *,
    space: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async def fetch(edge_type: str) -> dict[str, Any]:
        async with semaphore:
            return await graph_api.get_subgraph(
                paper["id"],
                edge_type=edge_type,
                direction="out",
                space=space,
            )

    authored, published, keywords, cited = await asyncio.gather(
        fetch("AUTHORED_BY"),
        fetch("PUBLISHED_IN"),
        fetch("HAS_KEYWORD"),
        fetch("CITED_BY"),
    )
    return {
        **paper,
        "authored": authored,
        "published": published,
        "keywords": keywords,
        "cited": cited,
    }


def _nodes_without_center(subgraph: dict[str, Any], center_id: str) -> list[dict[str, Any]]:
    return [node for node in subgraph.get("nodes") or [] if str(node.get("id") or "") != center_id]


def _paper_year(paper: dict[str, Any]) -> int:
    props = paper.get("properties") or {}
    raw = props.get("publication_year") or str(props.get("publication_date") or "")[:4]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _venue_type(paper: dict[str, Any]) -> str:
    props = paper.get("properties") or {}
    raw = str(props.get("publication_type") or props.get("document_type") or "").lower()
    conference_tokens = ("conference", "proceedings", "会议", "cvpr", "iccv", "eccv")
    return "conference" if any(token in raw for token in conference_tokens) else "journal"


def _venue_level(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    if props.get("jcr_zone"):
        return f"JCR-{props['jcr_zone']}"
    if props.get("scope_zone"):
        return f"中科院-{props['scope_zone']}"
    if props.get("sub_quartile") not in {None, ""}:
        return f"分区-{props['sub_quartile']}"
    if str(props.get("top") or "").lower() in {"1", "true"}:
        return "Top期刊"
    if str(props.get("is_sci") or "").lower() in {"1", "true"}:
        return "SCI"
    return "未分级"


def _paper_citations(paper: dict[str, Any]) -> int:
    values: list[int] = []
    for edge in paper.get("pathEdges") or []:
        raw = (edge.get("properties") or {}).get("citations")
        try:
            values.append(int(raw or 0))
        except (TypeError, ValueError):
            continue
    if values and max(values) > 0:
        return max(values)

    citation_keys = set()
    for edge in (paper.get("cited") or {}).get("edges") or []:
        props = edge.get("properties") or {}
        citation_keys.add(props.get("citation_identifier") or edge.get("target") or edge.get("id"))
    return len({key for key in citation_keys if key})


def _author_name(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    return str(props.get("name_zh") or props.get("name_en") or node.get("id") or "未知作者")


def _topic_name(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    return str(props.get("keyword") or props.get("name") or "").strip()


def _impact_score(paper_count: int, citation_total: int, high_level_count: int) -> float:
    if paper_count == 0:
        return 0.0
    raw = paper_count * 6.5 + citation_total / max(18, paper_count * 3) + high_level_count * 4
    return min(99.5, round(raw, 1))


async def _build_structured_result(
    graph_api: GraphSearchApiClient,
    body: ExpertPaperCooperationDemoRequest,
) -> dict[str, Any]:
    expert_a_vid = _person_vid(body.expertAId)
    expert_b_vid = _person_vid(body.expertBId)
    expert_a, expert_b = await asyncio.gather(
        graph_api.get_node(expert_a_vid, space=GRAPH_SPACE),
        graph_api.get_node(expert_b_vid, space=GRAPH_SPACE),
    )

    paths = await _fetch_shared_paths(graph_api, body)
    papers = _dedupe_shared_papers(paths)
    fallback_paper_count = 0
    fallback_collaborators: list[tuple[str, int]] = []
    if not papers and not body.startTime and not body.endTime:
        fallback_paper_count, fallback_collaborators = await _fetch_coauthor_fallback(
            graph_api, body
        )
    semaphore = asyncio.Semaphore(8)
    contexts = await asyncio.gather(
        *[
            _fetch_paper_context(
                graph_api,
                paper,
                space=GRAPH_SPACE,
                semaphore=semaphore,
            )
            for paper in papers
        ]
    )

    topic_counter: Counter[str] = Counter()
    journal_counter: Counter[str] = Counter()
    conference_counter: Counter[str] = Counter()
    collaborator_counter: Counter[str] = Counter()
    collaborator_years: dict[str, set[int]] = defaultdict(set)
    citation_counts: list[int] = []
    years: list[int] = []

    for name, strength in fallback_collaborators:
        collaborator_counter[name] = strength

    excluded_ids = {expert_a_vid, expert_b_vid}
    excluded_names = {
        _display_name(expert_a, body.expertAId),
        _display_name(expert_b, body.expertBId),
    }

    for paper in contexts:
        year = _paper_year(paper)
        if year:
            years.append(year)

        for node in _nodes_without_center(paper["keywords"], paper["id"]):
            topic = _topic_name(node)
            if topic:
                topic_counter[topic] += 1

        venues = _nodes_without_center(paper["published"], paper["id"])
        level = _venue_level(venues[0]) if venues else "未分级"
        if _venue_type(paper) == "conference":
            conference_counter[level] += 1
        else:
            journal_counter[level] += 1

        citation_counts.append(_paper_citations(paper))

        seen_authors: set[str] = set()
        for node in _nodes_without_center(paper["authored"], paper["id"]):
            node_id = str(node.get("id") or "")
            name = _author_name(node)
            if node_id in excluded_ids or name in excluded_names or name in seen_authors:
                continue
            seen_authors.add(name)
            collaborator_counter[name] += 1
            if year:
                collaborator_years[name].add(year)

    a_fields = _split_fields((expert_a.get("properties") or {}).get("research_fields"))
    b_fields = _split_fields((expert_b.get("properties") or {}).get("research_fields"))
    topics = [name for name, _ in topic_counter.most_common(8)]
    if not topics:
        common = [item for item in a_fields if item in set(b_fields)]
        topics = list(dict.fromkeys(common + a_fields + b_fields))[:8]

    ranked_collaborators = [
        name
        for name, _ in sorted(
            collaborator_counter.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    stable_members = [
        name
        for name in ranked_collaborators
        if collaborator_counter[name] >= 2 and len(collaborator_years[name]) >= 2
    ][:5]

    citation_total = sum(citation_counts)
    citation_max = max(citation_counts, default=0)
    high_level_count = sum(
        value for key, value in {**journal_counter, **conference_counter}.items() if key != "未分级"
    )

    shared_contribution: list[str] = []
    paper_count = len(papers) or fallback_paper_count
    if paper_count:
        shared_contribution.append("联合论文产出")
        if citation_total > 0:
            shared_contribution.append("持续学术影响")
        if _organization(expert_a) != _organization(expert_b):
            shared_contribution.append("跨机构协同研究")
        if topics:
            shared_contribution.append(f"{topics[0]}共同研究")

    start_year = min(years) if years else 0
    end_year = max(years) if years else 0
    return {
        "authorList": [
            _display_name(expert_a, body.expertAId),
            _display_name(expert_b, body.expertBId),
        ],
        "authorUnits": [_organization(expert_a), _organization(expert_b)],
        "cooperationTimeRange": {
            "startYear": start_year,
            "endYear": end_year,
            "displayText": f"{start_year} - {end_year}" if start_year and end_year else "",
        },
        "paperTopics": topics,
        "cooperationPaperCount": paper_count,
        "journalLevelCount": dict(journal_counter),
        "conferenceLevelCount": dict(conference_counter),
        "citation": {"total": citation_total, "max": citation_max},
        "cooperationFrequency": paper_count,
        "academicImpactScore": _impact_score(paper_count, citation_total, high_level_count),
        "stableTeamMembers": stable_members,
        "coreCollaborators": ranked_collaborators[:5],
        "sharedContribution": shared_contribution,
    }
