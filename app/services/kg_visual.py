"""In-memory graph store for the ECharts knowledge graph visual demo."""

from __future__ import annotations

from app.schemas.kg_visual import KGVisualGraph, KGVisualLink, KGVisualNode

GraphPayload = dict[str, list[dict]]

_graph_data: GraphPayload = {"nodes": [], "links": []}


def graph_data() -> GraphPayload:
    return _graph_data


def graph_response(message: str = "ok") -> dict:
    return {"message": message, "data": graph_data()}


def find_node(node_id: str) -> dict | None:
    return next((node for node in _graph_data["nodes"] if node["id"] == node_id), None)


def find_link_idx(source: str, target: str, relation: str) -> int | None:
    for idx, link in enumerate(_graph_data["links"]):
        if (
            link["source"] == source
            and link["target"] == target
            and link["relation"] == relation
        ):
            return idx
    return None


def replace_graph(body: KGVisualGraph) -> dict:
    _graph_data["nodes"] = [node.model_dump() for node in body.nodes]
    _graph_data["links"] = [link.model_dump() for link in body.links]
    return graph_response("图谱已全量更新")


def clear_graph() -> dict:
    _graph_data["nodes"].clear()
    _graph_data["links"].clear()
    return graph_response("图谱已清空")


def add_node(body: KGVisualNode) -> dict:
    node = body.model_dump()
    if not node["name"]:
        node["name"] = node["id"]
    _graph_data["nodes"].append(node)
    return graph_response(f"节点 '{body.id}' 已添加")


def update_node(node: dict, *, name: str | None, category: str | None, properties: dict | None) -> dict:
    if name is not None:
        node["name"] = name
    if category is not None:
        node["category"] = category
    if properties is not None:
        node.setdefault("properties", {}).update(properties)
    return graph_response(f"节点 '{node['id']}' 已更新")


def delete_node(node_id: str) -> dict:
    _graph_data["nodes"] = [node for node in _graph_data["nodes"] if node["id"] != node_id]
    _graph_data["links"] = [
        link
        for link in _graph_data["links"]
        if link["source"] != node_id and link["target"] != node_id
    ]
    return graph_response(f"节点 '{node_id}' 及关联边已删除")


def add_link(body: KGVisualLink) -> dict:
    _graph_data["links"].append(body.model_dump())
    return graph_response(f"关系 '{body.source} -[{body.relation}]-> {body.target}' 已添加")


def update_link(link: dict, *, relation: str | None, properties: dict | None) -> dict:
    if relation is not None:
        link["relation"] = relation
    if properties is not None:
        link.setdefault("properties", {}).update(properties)
    return graph_response("关系已更新")


def delete_link(idx: int) -> dict:
    _graph_data["links"].pop(idx)
    return graph_response("关系已删除")


def load_example_graph() -> dict:
    _graph_data["nodes"] = [
        {
            "id": "李白",
            "name": "李白",
            "category": "人物",
            "properties": {"字": "太白", "号": "青莲居士", "朝代": "唐", "生卒年": "701-762", "籍贯": "碎叶城", "职业": "诗人"},
        },
        {
            "id": "杜甫",
            "name": "杜甫",
            "category": "人物",
            "properties": {"字": "子美", "号": "少陵野老", "朝代": "唐", "生卒年": "712-770", "籍贯": "巩县", "职业": "诗人"},
        },
        {
            "id": "白居易",
            "name": "白居易",
            "category": "人物",
            "properties": {"字": "乐天", "号": "香山居士", "朝代": "唐", "生卒年": "772-846", "籍贯": "新郑", "职业": "诗人"},
        },
        {
            "id": "唐朝",
            "name": "唐朝",
            "category": "朝代",
            "properties": {"起止": "618-907", "都城": "长安", "开国皇帝": "李渊"},
        },
        {
            "id": "长安",
            "name": "长安",
            "category": "地点",
            "properties": {"今名": "西安", "省份": "陕西", "地位": "十三朝古都"},
        },
        {
            "id": "蜀道难",
            "name": "蜀道难",
            "category": "作品",
            "properties": {"体裁": "乐府诗", "创作年份": "约742年", "名句": "蜀道之难，难于上青天"},
        },
        {
            "id": "春望",
            "name": "春望",
            "category": "作品",
            "properties": {"体裁": "五言律诗", "创作年份": "757年", "名句": "国破山河在，城春草木深"},
        },
        {
            "id": "长恨歌",
            "name": "长恨歌",
            "category": "作品",
            "properties": {"体裁": "长篇叙事诗", "创作年份": "806年", "名句": "天长地久有时尽，此恨绵绵无绝期"},
        },
    ]
    _graph_data["links"] = [
        {"source": "李白", "target": "唐朝", "relation": "生活于", "properties": {"时期": "盛唐"}},
        {"source": "杜甫", "target": "唐朝", "relation": "生活于", "properties": {"时期": "盛唐→中唐"}},
        {"source": "白居易", "target": "唐朝", "relation": "生活于", "properties": {"时期": "中唐"}},
        {"source": "李白", "target": "杜甫", "relation": "交友", "properties": {"描述": "李杜相遇，诗坛佳话", "相遇年份": "744年"}},
        {"source": "李白", "target": "蜀道难", "relation": "创作", "properties": {}},
        {"source": "杜甫", "target": "春望", "relation": "创作", "properties": {"背景": "安史之乱"}},
        {"source": "白居易", "target": "长恨歌", "relation": "创作", "properties": {"背景": "唐玄宗与杨贵妃故事"}},
        {"source": "唐朝", "target": "长安", "relation": "定都", "properties": {}},
    ]
    return graph_response("示例图谱已加载")
