from __future__ import annotations

from typing import Any

from dao.industry_chain import IndustryChainDAO
from service.base_module import KGModuleService
from service.industry_chain_topn_event import IndustryChainTopNEventService


class IndustryChainPanoramaService(KGModuleService):
    module_code = "industry_chain_panorama"

    def __init__(self, dao: IndustryChainDAO | None = None) -> None:
        self._dao = dao or IndustryChainDAO()

    def query(
        self,
        *,
        chain_code: str | None,
        keyword: str | None,
        include_events: bool,
        limit_per_type: int,
    ) -> dict[str, Any]:
        if not chain_code and not keyword:
            raise ValueError("chainCode 和 keyword 至少提供一个")
        limit = max(1, min(limit_per_type, 500))
        chain_nodes = self._dao.list_nodes(chain_code=chain_code, keyword=keyword, limit=limit)
        if not chain_nodes:
            raise KeyError("未找到产业链")
        organizations = self._dao.list_organizations(
            chain_code=chain_code, keyword=keyword, limit=limit
        )
        patents = self._dao.list_patents(chain_code=chain_code, keyword=keyword, limit=limit)
        products = self._dao.list_products(chain_code=chain_code, keyword=keyword, limit=limit)
        news = (
            self._dao.list_news(chain_code=chain_code, keyword=keyword, limit=limit)
            if include_events
            else []
        )
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for item in chain_nodes:
            node_id = str(item.get("node_id") or item.get("chain_code"))
            nodes[node_id] = {"id": node_id, "type": "chainNode", "properties": item}
            if parent := item.get("parent_id"):
                edges.append({"source": str(parent), "target": node_id, "type": "CONTAINS"})
        for item in organizations:
            org_id = str(item.get("antitypic") or item.get("credit_code"))
            nodes[org_id] = {"id": org_id, "type": "organization", "properties": item}
            edges.append(
                {
                    "source": str(item.get("node_id") or item.get("chain_code")),
                    "target": org_id,
                    "type": "HAS_ORGANIZATION",
                    "properties": {"score": _number(item.get("chain_score"))},
                }
            )
        for item in products:
            product_id = f"product:{item.get('antitypic')}:{item.get('tech_product')}"
            nodes[product_id] = {"id": product_id, "type": "product", "properties": item}
            edges.append(
                {"source": str(item.get("antitypic")), "target": product_id, "type": "HAS_PRODUCT"}
            )
        for item in patents:
            patent_id = str(item.get("apno") or item.get("pat_name"))
            nodes[patent_id] = {"id": patent_id, "type": "patent", "properties": item}
            edges.append(
                {
                    "source": str(item.get("node_id") or item.get("chain_code")),
                    "target": patent_id,
                    "type": "HAS_PATENT",
                }
            )
        for index, item in enumerate(news):
            event = IndustryChainTopNEventService._event(item, keyword)
            event["rank"] = index + 1
            nodes[event["id"]] = {"id": event["id"], "type": "event", "properties": event}
            edges.append(
                {
                    "source": str(item.get("chain_code")),
                    "target": event["id"],
                    "type": "HAS_EVENT",
                }
            )
        return {
            "chain": {
                "code": chain_nodes[0].get("chain_code"),
                "name": chain_nodes[0].get("chain_name"),
            },
            "counts": {
                "chainNodes": len(chain_nodes),
                "organizations": len(organizations),
                "products": len(products),
                "patents": len(patents),
                "events": len(news),
            },
            "graph": {"nodes": list(nodes.values()), "edges": edges},
        }


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None
