"""MySQL → techkg 图 ETL：灌 Scholar、Organization 节点与 EMPLOYED_BY 边。

用法：python -m script.load_graph
"""

from __future__ import annotations

import logging

from dao.organization import OrganizationDAO
from dao.scholar import ScholarDAO
from infra.graph_db import get_techkg_client
from infra.mysql import get_mysql_client

logger = logging.getLogger("script.load_graph")


def build_scholar_node_props(s) -> dict:
    return {
        "scholar_id": s.scholar_id,
        "name_zh": s.name_zh or "",
        "name_en": s.name_en or "",
        "scholar_org_name_zh": s.scholar_org_name_zh or "",
        "scholar_org_name_en": s.scholar_org_name_en or "",
        "h_index": s.h_index or 0,
        "citation_nums": s.citation_nums or 0,
        "paper_nums": s.paper_nums or 0,
    }


def build_org_node_props(o) -> dict:
    return {
        "org_id": o.org_id,
        "name_cn": o.name_cn or "",
        "province": o.province or "",
        "city": o.city or "",
        "org_type": o.org_type or "",
        "listing_status": o.listing_status or "",
        "incorporation_year": o.incorporation_year or 0,
    }


def load_graph(batch_limit: int = 500) -> int:
    """灌图，返回写入的 Scholar 节点数。MySQL 空时返回 0。"""
    mysql = get_mysql_client()
    graph = get_techkg_client()

    session = mysql.session()
    try:
        scholar_dao = ScholarDAO(session)
        org_dao = OrganizationDAO(session)

        # 1) Organization 节点（先灌，便于边匹配）
        orgs = org_dao.list(limit=100000, offset=0)
        org_name_to_id: dict[str, object] = {}
        for o in orgs:
            node = graph.merge_node(["Organization"], {"org_id": o.org_id}, build_org_node_props(o))
            # name_cn 非唯一键；同名机构会覆盖映射（scholar 仅携带 org_name，按名称匹配是当前 schema 下的折中）
            org_name_to_id[o.name_cn] = node.id
        # 2) Scholar 节点 + EMPLOYED_BY 边
        count = 0
        offset = 0
        while True:
            scholars = scholar_dao.list(limit=batch_limit, offset=offset)
            if not scholars:
                break
            for s in scholars:
                snode = graph.merge_node(
                    ["Scholar"], {"scholar_id": s.scholar_id}, build_scholar_node_props(s)
                )
                count += 1
                org_name = s.scholar_org_name_zh or ""
                org_id = org_name_to_id.get(org_name)
                if org_id is None and org_name:
                    found = graph.find_nodes(["Organization"], {"name_cn": org_name}, limit=1)
                    if found.items:
                        org_id = found.items[0].id
                        org_name_to_id[org_name] = org_id
                if org_id is not None:
                    graph.merge_edge(
                        snode.id,
                        org_id,
                        "EMPLOYED_BY",
                        {},
                        {
                            "relation_type": "任职",
                            "role": "",
                            "start_date": "",
                            "end_date": "",
                            "source": "mysql",
                        },
                    )
            offset += len(scholars)
            if len(scholars) < batch_limit:
                break
        logger.info("loaded %d scholars, %d orgs", count, len(orgs))
        return count
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_graph()
