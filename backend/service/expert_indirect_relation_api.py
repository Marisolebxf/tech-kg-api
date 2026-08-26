from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

import httpx

from biz.schema.expert_indirect_relation import ExpertIndirectRelationRequest
from service.base_module import KGModuleScaffoldService

GRAPH_SPACE = os.getenv("KG_GRAPH_SPACE", "dev")
MAX_GRAPH_ITEMS = 200
MAX_CANDIDATE_PATHS = 1000
MAX_RESULT_PATHS = 50

# 60s 进程内结果缓存：读多写少，同参数请求复用，避免高并发打爆 graph-search/trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_result_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()


RELATION_GROUPS: tuple[tuple[str, set[str]], ...] = (
    (
        "项目关联",
        {"PARTICIPATES_IN", "HAS_PARTICIPANT", "FUNDED_BY", "OUTPUT_OF", "HAS_OUTPUT"},
    ),
    ("专利关联", {"INVENTED_BY", "APPLIED_BY", "BELONGS_TO_NODE"}),
    (
        "产业关联",
        {
            "INVESTS_IN",
            "SHAREHOLDER_OF",
            "SUBSIDIARY_OF",
            "ACQUIRES",
            "ACTUAL_CONTROLLER_OF",
            "BENEFICIAL_OWNER_OF",
            "PRODUCES",
        },
    ),
    (
        "机构关联",
        {"AFFILIATED_WITH", "EMPLOYED_BY", "EXECUTIVE_OF", "LEADS", "MEMBER_OF_FAMILY"},
    ),
    (
        "学术关联",
        {
            "COAUTHOR_WITH",
            "AUTHORED_BY",
            "CITES",
            "CITED_BY",
            "PUBLISHED_IN",
            "HAS_KEYWORD",
            "RELATED_TO",
        },
    ),
)

DEFAULT_EDGE_WEIGHTS = {
    "COAUTHOR_WITH": 0.84,
    "AFFILIATED_WITH": 0.88,
    "EMPLOYED_BY": 0.9,
    "PARTICIPATES_IN": 0.86,
    "HAS_PARTICIPANT": 0.86,
    "INVENTED_BY": 0.88,
    "AUTHORED_BY": 0.86,
    "PUBLISHED_IN": 0.8,
    "CITES": 0.72,
    "CITED_BY": 0.72,
}


class GraphQueryApiError(RuntimeError):
    """公开查图 API 调用失败。"""


class GraphQueryApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        auth_headers: Mapping[str, str] | None = None,
        app: Any = None,
    ) -> None:
        # 进程内 ASGI transport：替代真实 HTTP 回环 8200，消除 socket/accept 队列开销
        # 与高并发下的自调用饱和。方法体、路径、错误语义（raise_for_status/ValueError→404/
        # GraphQueryApiError）保持不变。app 由 handler 传 request.app，避免在 service 里 import main。
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver/api/v1",
            timeout=timeout,
            headers=auth_headers,
        )

    async def __aenter__(self) -> GraphQueryApiClient:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self._client.aclose()

    async def _get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success", False):
            message = payload.get("msg") or "查图 API 返回失败"
            if payload.get("code") == 404:
                raise ValueError(message)
            raise GraphQueryApiError(message)
        return payload.get("data") or {}

    async def get_node(self, node_id: str) -> dict[str, Any]:
        return await self._get(
            f"/graph-search/nodes/{node_id}",
            params={"space": GRAPH_SPACE},
        )

    async def get_subgraph(self, node_id: str, *, depth: int) -> dict[str, Any]:
        return await self._get(
            f"/graph-search/subgraph/{node_id}",
            params={
                "depth": depth,
                "limit": MAX_GRAPH_ITEMS,
                "direction": "both",
                "space": GRAPH_SPACE,
            },
        )


class ExpertIndirectRelationApiService(KGModuleScaffoldService):
    """仅通过 FastAPI 查图接口分析单节点间接关系。"""

    module_code = "expert_indirect_relation"

    async def build_structured_result_only(
        self,
        body: ExpertIndirectRelationRequest,
        *,
        api_base_url: str,
        auth_headers: Mapping[str, str] | None = None,
        app: Any = None,
    ) -> dict[str, Any]:
        core_id = _person_vid(body.core_node_id)
        cache_key = f"{core_id}|{tuple(body.relation_types)}|{body.path_depth}|{body.min_strength}"
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        async with GraphQueryApiClient(
            api_base_url, auth_headers=auth_headers, app=app
        ) as graph_api:
            # get_node 与 get_subgraph 入参都是 core_id，互不依赖，并行拉取。
            # return_exceptions + 节点不存在(ValueError→404)优先抛，保留原串行的错误码语义。
            core_node_r, subgraph_r = await asyncio.gather(
                graph_api.get_node(core_id),
                graph_api.get_subgraph(core_id, depth=body.path_depth),
                return_exceptions=True,
            )
        if isinstance(core_node_r, ValueError):
            raise core_node_r
        if isinstance(core_node_r, Exception):
            raise core_node_r
        if isinstance(subgraph_r, Exception):
            raise subgraph_r
        core_node, subgraph = core_node_r, subgraph_r
        result = _build_result(core_node, subgraph, body)
        payload = {
            "structuredResult": result,
            "provenance": _build_provenance(result),
            "rules": _build_rules(result),
        }
        with _result_cache_lock:
            _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, payload)
        return payload


def _person_vid(node_id: str) -> str:
    return node_id if node_id.startswith("person_") else f"person_{node_id}"


def _node_name(node: dict[str, Any]) -> str:
    props = node.get("properties") or {}
    for key in ("name_zh", "name_en", "title_zh", "title_en", "name", "keyword"):
        if props.get(key):
            return str(props[key])
    return str(node.get("id") or "未知节点")


def _entity_type(node: dict[str, Any]) -> str:
    labels = node.get("labels") or []
    label = str(labels[0]) if labels else "Entity"
    return {
        "Person": "科技专家",
        "Organization": "科研机构",
        "Project": "科研项目",
        "Paper": "论文成果",
        "Patent": "专利成果",
        "Product": "科技产品",
        "Keyword": "研究主题",
        "Event": "科技事件",
        "News": "新闻资讯",
        "Report": "研究报告",
    }.get(label, label)


def _node_brief(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(node.get("id") or ""),
        "name": _node_name(node),
        "entityType": _entity_type(node),
        "labels": list(node.get("labels") or []),
        "properties": node.get("properties") or {},
    }


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    return str(edge.get("type") or ""), min(source, target), max(source, target)


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target or source == target:
            continue
        key = _edge_key(edge)
        current = unique.get(key)
        if current is None or _edge_strength(edge) > _edge_strength(current):
            unique[key] = edge
    return list(unique.values())


def _numeric_property(properties: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        raw = properties.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _edge_strength(edge: dict[str, Any]) -> float:
    props = edge.get("properties") or {}
    confidence = _numeric_property(props, "confidence", "score", "relation_strength")
    if confidence is not None:
        if confidence > 1:
            confidence /= 100
        return min(1.0, max(0.0, confidence))

    cooperation_count = _numeric_property(props, "co_paper_count", "cooperation_count")
    if cooperation_count is not None and cooperation_count > 0:
        normalized = math.log1p(cooperation_count) / math.log1p(200)
        return min(0.95, 0.6 + normalized * 0.35)

    return DEFAULT_EDGE_WEIGHTS.get(str(edge.get("type") or ""), 0.75)


def _path_strength(edges: list[dict[str, Any]]) -> float:
    if not edges:
        return 0.0
    product = math.prod(max(_edge_strength(edge), 0.01) for edge in edges)
    geometric_mean = product ** (1 / len(edges))
    length_decay = 0.92 ** (len(edges) - 1)
    return round(min(1.0, geometric_mean * length_decay), 4)


def _relation_type(edges: list[dict[str, Any]]) -> str:
    edge_types = {str(edge.get("type") or "") for edge in edges}
    for label, members in RELATION_GROUPS:
        if edge_types & members:
            return label
    return "资源关联"


def _edge_brief(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(edge.get("id") or ""),
        "type": str(edge.get("type") or ""),
        "source": str(edge.get("source") or ""),
        "target": str(edge.get("target") or ""),
        "properties": edge.get("properties") or {},
    }


def _node_source(node: dict[str, Any]) -> tuple[str, str]:
    """按科技专家同事关系的口径返回 MySQL 源表和英文字段名。"""
    properties = node.get("properties") or {}
    source_table = properties.get("organization_base") or properties.get("source_table")
    labels = {str(label) for label in node.get("labels") or []}
    source_record_id = properties.get("source_record_id")
    organization_id = properties.get("organization_id")

    if labels & {"Person", "Scholar", "Expert"} and source_record_id not in (None, ""):
        source_field = "scholar_id" if source_table == "dwd_scholar" else "source_record_id"
    elif organization_id == "scholar_id" and source_record_id not in (None, ""):
        source_field = "scholar_id"
    elif organization_id not in (None, ""):
        source_field = "organization_id"
    else:
        source_field = "source_record_id"
    return str(source_table or "-"), source_field


def _build_provenance(result: dict[str, Any]) -> dict[str, Any]:
    """按实体的 MySQL 源表、源字段和图空间 VID 构造溯源证据。"""
    evidences: list[dict[str, str]] = []
    seen: set[str] = set()

    def append_node(node: dict[str, Any]) -> None:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen:
            return
        seen.add(node_id)
        source_table, source_field = _node_source(node)
        evidences.append(
            {
                "title": f"实体 · {node.get('name') or node_id}",
                "sourceTable": source_table,
                "sourceField": source_field,
                "graphVid": node_id,
            }
        )

    append_node(result["coreNode"])
    for path in result.get("paths", [])[:8]:
        for node in path.get("nodes", []):
            append_node(node)

    relation_types = "、".join(result.get("relationTypeCount", {}).keys()) or "无"
    return {
        "sourceDatabase": f"trs-graph / space={GRAPH_SPACE}",
        "summary": (
            f"命中 {result.get('pathCount', 0)} 条间接路径；"
            f"路径深度={result.get('pathDepth', 0)}；关系类型={relation_types}。"
        ),
        "evidences": evidences,
    }


def _matches_requested_types(
    requested: set[str],
    relation_type: str,
    edges: list[dict[str, Any]],
) -> bool:
    if not requested:
        return True
    edge_types = {str(edge.get("type") or "") for edge in edges}
    return relation_type in requested or bool(edge_types & requested)


def _enumerate_paths(
    core_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_depth: int,
    min_strength: float,
    requested_types: set[str],
) -> tuple[set[str], list[dict[str, Any]]]:
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        adjacency[source].append((target, edge))
        adjacency[target].append((source, edge))

    direct_ids = {neighbor for neighbor, _ in adjacency.get(core_id, [])}
    candidates: list[dict[str, Any]] = []
    stack: list[tuple[str, list[str], list[dict[str, Any]]]] = [(core_id, [core_id], [])]

    while stack and len(candidates) < MAX_CANDIDATE_PATHS:
        current, node_ids, path_edges = stack.pop()
        depth = len(path_edges)
        if depth >= 2 and current not in direct_ids:
            relation_type = _relation_type(path_edges)
            strength = _path_strength(path_edges)
            if strength >= min_strength and _matches_requested_types(
                requested_types, relation_type, path_edges
            ):
                path_nodes = [nodes_by_id[node_id] for node_id in node_ids]
                candidates.append(
                    {
                        "pathId": "path_" + "_".join(node_ids),
                        "depth": depth,
                        "relationType": relation_type,
                        "strength": strength,
                        "pathText": " → ".join(_node_name(node) for node in path_nodes),
                        "targetNode": _node_brief(path_nodes[-1]),
                        "nodes": [_node_brief(node) for node in path_nodes],
                        "edges": [_edge_brief(edge) for edge in path_edges],
                    }
                )
        if depth >= max_depth:
            continue
        for neighbor, edge in adjacency.get(current, []):
            if neighbor in node_ids:
                continue
            stack.append((neighbor, [*node_ids, neighbor], [*path_edges, edge]))

    deduped: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for path in candidates:
        edge_types = tuple(edge["type"] for edge in path["edges"])
        key = (path["targetNode"]["id"], edge_types)
        current = deduped.get(key)
        if current is None or path["strength"] > current["strength"]:
            deduped[key] = path
    paths = sorted(
        deduped.values(),
        key=lambda item: (-item["strength"], item["depth"], item["pathText"]),
    )[:MAX_RESULT_PATHS]
    return direct_ids, paths


def _build_result(
    core_node: dict[str, Any],
    subgraph: dict[str, Any],
    body: ExpertIndirectRelationRequest,
) -> dict[str, Any]:
    core_id = str(core_node.get("id") or _person_vid(body.core_node_id))
    raw_nodes = list(subgraph.get("nodes") or [])
    nodes_by_id = {
        str(node.get("id") or ""): node for node in [core_node, *raw_nodes] if node.get("id")
    }
    edges = _dedupe_edges(list(subgraph.get("edges") or []))
    direct_ids, paths = _enumerate_paths(
        core_id,
        nodes_by_id,
        edges,
        max_depth=body.path_depth,
        min_strength=body.min_strength,
        requested_types=set(body.relation_types),
    )

    indirect_by_id: dict[str, dict[str, Any]] = {}
    for path in paths:
        target = path["targetNode"]
        indirect_by_id[target["id"]] = target

    relation_counts = Counter(path["relationType"] for path in paths)
    strengths = [float(path["strength"]) for path in paths]
    direct_nodes = [
        _node_brief(nodes_by_id[node_id])
        for node_id in sorted(direct_ids)
        if node_id in nodes_by_id
    ]
    indirect_nodes = sorted(
        indirect_by_id.values(),
        key=lambda node: node["name"],
    )
    return {
        "coreNode": _node_brief(core_node),
        "pathDepth": body.path_depth,
        "minStrength": body.min_strength,
        "directNodeCount": len(direct_ids),
        "indirectNodeCount": len(indirect_nodes),
        "pathCount": len(paths),
        "relationTypeCount": dict(relation_counts),
        "averageStrength": round(sum(strengths) / len(strengths), 4) if strengths else 0.0,
        "maxStrength": max(strengths, default=0.0),
        "directNodes": direct_nodes[:20],
        "indirectNodes": indirect_nodes,
        "paths": paths,
    }


def _build_rules(result: dict[str, Any]) -> list[dict[str, Any]]:
    path_count = int(result.get("pathCount") or 0)
    path_depth = int(result.get("pathDepth") or 0)
    min_strength = float(result.get("minStrength") or 0)
    relation_types = "、".join(result.get("relationTypeCount", {}).keys()) or "无命中类型"
    audit = "代码未配置人工审核流；查询异常或未命中时按接口实际状态返回，不补造关系。"
    return [
        {
            "name": "间接路径发现规则",
            "type": "路径查询规则",
            "target": "核心 Person 节点及深度范围内的真实节点和关系边",
            "trigger": f"核心节点可定位，path_depth={path_depth}",
            "logic": "读取核心节点双向子图；同类型、同端点的边仅保留强度较高者；枚举不重复节点的简单路径，仅保留不少于 2 跳且终点不是核心节点直接邻居的路径。",
            "output": "直接节点、间接节点、完整路径节点和关系边",
            "threshold": "path_depth 仅允许 2 或 3；子图最多 200 项、候选路径最多 1000 条、最终最多 50 条",
            "audit": audit,
            "appliedCount": path_count,
        },
        {
            "name": "间接关系分类规则",
            "type": "关系类型映射规则",
            "target": "候选路径中的真实关系边类型",
            "trigger": "简单路径达到 2 跳或 3 跳",
            "logic": "按项目、专利、产业、机构、学术关系边集合依次归类；再按请求选择的学术关联、机构关联或项目关联过滤。",
            "output": f"路径关系类型及分类计数；本次命中：{relation_types}",
            "threshold": "relation_types 必须且只能选择学术关联、机构关联、项目关联中的一项",
            "audit": audit,
            "appliedCount": path_count,
        },
        {
            "name": "路径强度计算与排序规则",
            "type": "评分过滤规则",
            "target": "候选路径及其关系边",
            "trigger": "路径完成关系分类后",
            "logic": "边强度优先读取 confidence、score、relation_strength；百分制值除以 100。缺失时按合作次数对数归一化，再缺失时使用边类型默认权重。路径强度取边强度几何平均并乘以 0.92 的长度衰减。",
            "output": "路径强度、平均强度、最大强度及降序结果",
            "threshold": f"路径强度 >= min_strength（本次 {min_strength:g}）；同一目标和边类型序列仅保留最强路径",
            "audit": audit,
            "appliedCount": path_count,
        },
    ]
