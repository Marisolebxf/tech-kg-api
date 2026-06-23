KG_CONSTRUCTION_MODULES: tuple[dict[str, object], ...] = (
    {
        "code": "expert_direct_relation",
        "name": "科技专家/人才直接关系",
        "description": "识别并构建专家或人才之间的直接关联，记录关系类型、时间、场景和相关成果。",
        "status": "scaffold",
    },
    {
        "code": "expert_indirect_relation",
        "name": "科技单节点间接关系",
        "description": "以单个专家或人才为核心节点，推理间接关系、传递路径和关联强度。",
        "status": "scaffold",
    },
    {
        "code": "expert_cooperation_achievement",
        "name": "科技两点合作成果",
        "description": "针对两个专家或人才节点，汇总合作成果、成果分类、时间、领域和贡献模式。",
        "status": "scaffold",
    },
    {
        "code": "expert_colleague_relation",
        "name": "科技专家同事关系",
        "description": "基于任职单位、团队和时间匹配，推理专家之间的同事关系。",
        "status": "scaffold",
    },
    {
        "code": "expert_alumni_relation",
        "name": "科技专家校友关系",
        "description": "基于教育经历和院校信息，识别专家之间的校友关系及关联维度。",
        "status": "scaffold",
    },
    {
        "code": "expert_paper_cooperation",
        "name": "科技专家论文合作关系",
        "description": "基于论文作者、单位、主题和发表时间，构建专家论文合作关系。",
        "status": "scaffold",
    },
    {
        "code": "expert_enterprise_relation",
        "name": "重点关注科技企业关系",
        "description": "围绕专家或人才，构建其与重点科技企业之间的角色、领域和合作关系。",
        "status": "scaffold",
    },
    {
        "code": "relation_detail_annotation",
        "name": "角色与合作详情标注",
        "description": "对专家-企业关系补充角色身份、技术领域、合作任职时段等详情属性，精细化政企关系语义描述。",
        "status": "scaffold",
    },
    {
        "code": "enterprise_background_analysis",
        "name": "企业背景关联分析",
        "description": "基于企业ID，从行业地位、核心技术、经营财务、专利分类等维度开展背景关联分析，支撑产业链研究。",
        "status": "scaffold",
    },
    {
        "code": "industry_chain_topn_event",
        "name": "科技产业链点TOP-N事件关系",
        "description": "针对产业链节点筛选核心事件，构建事件与专家、人才、产业节点的关联。",
        "status": "scaffold",
    },
    {
        "code": "industry_chain_panorama",
        "name": "科技产业链全景图",
        "description": "整合产业链实体、关系和事件，支撑全景图展示、筛选和动态更新。",
        "status": "scaffold",
    },
)


def list_kg_construction_modules() -> list[dict[str, object]]:
    return [dict(module) for module in KG_CONSTRUCTION_MODULES]


def get_kg_construction_module(module_code: str) -> dict[str, object] | None:
    for module in KG_CONSTRUCTION_MODULES:
        if module["code"] == module_code:
            return dict(module)
    return None
