"""重点关注科技企业关系业务（九大业务之一）HTTP 端点。

对齐前端 service-modules.ts 的 enterprise-relation 契约：
POST /api/v1/kg-service/key-enterprise-relation，请求 {expert_id, enterprise_name, role_type,
industry}。围绕科技专家，通过查图 API 挖掘图谱中专家↔企业关联（governance + 项目合作 +
专利合作），运用角色定位算法标注角色/合作模式/合作时间，关联企业行业地位/技术方向/经营状况。
只调用后端 graph-search 查图 API，不直连图。
"""

from __future__ import annotations

from fastapi import APIRouter

from biz.schemas.common import ApiResponse
from biz.schemas.tech_enterprise_relation_business import (
    KeyEnterpriseRelationRequest,
)
from service.tech_enterprise_relation_business import KeyEnterpriseRelationService

router = APIRouter(prefix="/kg-service", tags=["kg-service"])
service = KeyEnterpriseRelationService()


@router.get("/key-enterprise-relation")
async def describe_key_enterprise_relation() -> dict[str, object]:
    return {
        "business": "重点关注科技企业关系",
        "endpoint": "POST /api/v1/kg-service/key-enterprise-relation",
        "request": ["expert_id(必)", "enterprise_name", "role_type", "industry"],
        "data_sources": [
            "governance: EXECUTIVE_OF/LEGAL_REP_OF/ACTUAL_CONTROLLER_OF/BENEFICIAL_OWNER_OF/SHAREHOLDER_OF/AFFILIATED_WITH",
            "project_cooperation: Person→Project→Organization（合作时间=Project.research_period）",
            "patent_cooperation: Person→Patent→Organization（合作时间=Patent.application_date）",
        ],
        "data_gaps": [
            "高管任职类(governance)边无任职起止时间；合作时间仅项目/专利/学者工作经历可取",
            "Person-Patent-Organization 路径在 dev 当前为 0 条",
        ],
    }


@router.post("/key-enterprise-relation", response_model=ApiResponse)
async def run_key_enterprise_relation(req: KeyEnterpriseRelationRequest) -> ApiResponse:
    try:
        data = await service.run(req)
        return ApiResponse(data=data.model_dump())
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(code=500, success=False, msg=f"重点关注科技企业关系业务执行失败: {exc}")
