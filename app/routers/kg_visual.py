"""ECharts knowledge graph visual demo endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.kg_visual import (
    KGVisualGraph,
    KGVisualGraphResponse,
    KGVisualLink,
    KGVisualLinkUpdate,
    KGVisualNode,
    KGVisualNodeDetailResponse,
    KGVisualNodeUpdate,
)
from app.services import kg_visual

router = APIRouter(prefix="/kg-visual", tags=["KG Visual Demo"])
page_router = APIRouter(tags=["KG Visual Demo"])


@page_router.get("/kg-visual", response_class=FileResponse)
def kg_visual_page() -> FileResponse:
    html_path = Path(__file__).resolve().parents[1] / "static" / "kg_visual" / "index.html"
    return FileResponse(html_path)


@router.get("/graph", response_model=KGVisualGraphResponse)
def get_graph() -> dict:
    return kg_visual.graph_response()


@router.post("/graph", response_model=KGVisualGraphResponse)
def replace_graph(body: KGVisualGraph) -> dict:
    return kg_visual.replace_graph(body)


@router.delete("/graph", response_model=KGVisualGraphResponse)
def clear_graph() -> dict:
    return kg_visual.clear_graph()


@router.post("/graph/node", response_model=KGVisualGraphResponse)
def add_node(body: KGVisualNode) -> dict:
    if kg_visual.find_node(body.id):
        raise HTTPException(status_code=400, detail=f"节点 '{body.id}' 已存在")
    return kg_visual.add_node(body)


@router.get("/graph/node/{node_id}", response_model=KGVisualNodeDetailResponse)
def get_node(node_id: str) -> dict:
    node = kg_visual.find_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")
    related_links = [
        link
        for link in kg_visual.graph_data()["links"]
        if link["source"] == node_id or link["target"] == node_id
    ]
    return {"message": "ok", "data": {"node": node, "related_links": related_links}}


@router.put("/graph/node/{node_id}", response_model=KGVisualGraphResponse)
def update_node(node_id: str, body: KGVisualNodeUpdate) -> dict:
    node = kg_visual.find_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")
    return kg_visual.update_node(
        node,
        name=body.name,
        category=body.category,
        properties=body.properties,
    )


@router.delete("/graph/node/{node_id}", response_model=KGVisualGraphResponse)
def delete_node(node_id: str) -> dict:
    if not kg_visual.find_node(node_id):
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")
    return kg_visual.delete_node(node_id)


@router.delete("/graph/node/{node_id}/property/{key}", response_model=KGVisualGraphResponse)
def delete_node_property(node_id: str, key: str) -> dict:
    node = kg_visual.find_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")
    if key not in node.get("properties", {}):
        raise HTTPException(status_code=404, detail=f"属性 '{key}' 不存在")
    del node["properties"][key]
    return kg_visual.graph_response(f"节点 '{node_id}' 的属性 '{key}' 已删除")


@router.post("/graph/link", response_model=KGVisualGraphResponse)
def add_link(body: KGVisualLink) -> dict:
    if not kg_visual.find_node(body.source):
        raise HTTPException(status_code=400, detail=f"源节点 '{body.source}' 不存在")
    if not kg_visual.find_node(body.target):
        raise HTTPException(status_code=400, detail=f"目标节点 '{body.target}' 不存在")
    if kg_visual.find_link_idx(body.source, body.target, body.relation) is not None:
        raise HTTPException(status_code=400, detail="该关系已存在")
    return kg_visual.add_link(body)


@router.put("/graph/link", response_model=KGVisualGraphResponse)
def update_link(source: str, target: str, relation: str, body: KGVisualLinkUpdate) -> dict:
    idx = kg_visual.find_link_idx(source, target, relation)
    if idx is None:
        raise HTTPException(status_code=404, detail="未找到该关系")
    return kg_visual.update_link(
        kg_visual.graph_data()["links"][idx],
        relation=body.relation,
        properties=body.properties,
    )


@router.delete("/graph/link", response_model=KGVisualGraphResponse)
def delete_link(source: str, target: str, relation: str) -> dict:
    idx = kg_visual.find_link_idx(source, target, relation)
    if idx is None:
        raise HTTPException(status_code=404, detail="未找到该关系")
    return kg_visual.delete_link(idx)


@router.get("/graph/example", response_model=KGVisualGraphResponse)
def load_example() -> dict:
    return kg_visual.load_example_graph()
