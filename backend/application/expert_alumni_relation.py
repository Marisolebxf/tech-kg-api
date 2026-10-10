"""科技专家校友关系 应用层:查询 + 判定结果落盘(ALUMNI 边 upsert)。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from service.expert_alumni_relation import ExpertAlumniRelationService
from service.graph_space_context import get_current_space, request_can_write

logger = logging.getLogger(__name__)


class ExpertAlumniRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertAlumniRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def query(
        self,
        *,
        expert_id: str,
        target_expert_id: str | None = None,
        school: str | None = None,
        education_stage: str | None = None,
        limit: int = 20,
    ) -> dict[str, object]:
        data = self._service.query(
            expert_id=expert_id,
            target_expert_id=target_expert_id,
            school=school,
            education_stage=education_stage,
            limit=limit,
        )
        # 当前空间允许写入才 upsert ALUMNI 边；公共空间只读查询不落盘。
        # 浅拷贝顶层 dict,避免把 persistence 键写进服务层共享缓存对象。
        persistence = (
            self._persist_relations(data)
            if request_can_write.get()
            else {
                "space": get_current_space(),
                "edgeType": "ALUMNI",
                "created": 0,
                "updated": 0,
                "total": 0,
                "readOnly": True,
            }
        )
        return {**data, "persistence": persistence}

    @staticmethod
    def _persist_relations(data: dict[str, Any]) -> dict[str, Any]:
        settings = TRSGraphSettings.from_env()
        settings.space = get_current_space()
        graph = TRSGraphClient(settings)
        graph.connect()
        created = updated = 0
        try:
            graph.execute_write(
                "CREATE EDGE IF NOT EXISTS ALUMNI("
                "shared_institutions string, dimensions_json string, "
                "educations_json string, paper_count int, patent_count int, "
                "project_count int, interactions_summary string, "
                "confidence double, evidence_json string, source string, "
                "updated_at string);"
            )
            expert_id = str(data["expert"]["id"])
            try:
                current_edges = graph.get_node_edges(
                    expert_id, direction="both", edge_type="ALUMNI", limit=1000
                )
            except Exception:  # noqa: BLE001 — 图库抖动时按无既有边处理,靠 upsert 幂等兜底
                current_edges = []
            existing = {
                str(edge.target_id if str(edge.source_id) == expert_id else edge.source_id): edge
                for edge in current_edges
            }
            now = datetime.now(UTC).isoformat()
            for item in data.get("items", []):
                target_id = str(item["alumniId"])
                interactions = item.get("interactions") or {}
                dimensions = item.get("dimensions") or []
                shared = item.get("sharedInstitutions") or []
                evidence = [
                    f"共同院校：{'、'.join(shared) or '—'}",
                    f"关系维度：{'、'.join(dimensions) or '同校'}",
                ]
                summary = str(interactions.get("summary") or "无互动")
                if summary != "无互动":
                    evidence.append(f"互动证据：{summary}")
                properties = {
                    "shared_institutions": json.dumps(shared, ensure_ascii=False),
                    "dimensions_json": json.dumps(dimensions, ensure_ascii=False),
                    "educations_json": json.dumps(item.get("educations") or [], ensure_ascii=False),
                    "paper_count": int(interactions.get("paperCount") or 0),
                    "patent_count": int(interactions.get("patentCount") or 0),
                    "project_count": int(interactions.get("projectCount") or 0),
                    "interactions_summary": summary,
                    "confidence": float(item.get("confidence") or 0),
                    "evidence_json": json.dumps(evidence, ensure_ascii=False),
                    "source": "expert_alumni_relation_service",
                    "updated_at": now,
                }
                edge = existing.get(target_id)
                source_id, destination_id = sorted((expert_id, target_id))
                if edge is None:
                    graph.create_edge(source_id, destination_id, "ALUMNI", properties)
                    created += 1
                else:
                    graph.update_edge(edge.id, properties, edge_type="ALUMNI")
                    updated += 1
        except Exception:  # noqa: BLE001 — 落盘失败不阻断查询响应,下次查询重试 upsert
            logger.exception("校友关系落盘 ALUMNI 边失败")
        finally:
            graph.close()
        return {
            "space": settings.space,
            "edgeType": "ALUMNI",
            "created": created,
            "updated": updated,
            "total": created + updated,
        }
