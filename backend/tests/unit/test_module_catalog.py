from service.module_catalog import get_kg_construction_module, list_kg_construction_modules


def test_list_kg_construction_modules() -> None:
    modules = list_kg_construction_modules()

    assert len(modules) == 9
    assert {module["code"] for module in modules} == {
        "expert_direct_relation",
        "expert_indirect_relation",
        "expert_cooperation_achievement",
        "expert_colleague_relation",
        "expert_alumni_relation",
        "expert_paper_cooperation",
        "expert_enterprise_relation",
        "industry_chain_topn_event",
        "industry_chain_panorama",
    }


def test_get_kg_construction_module() -> None:
    module = get_kg_construction_module("expert_direct_relation")

    assert module is not None
    assert module["name"] == "科技专家/人才直接关系"


def test_get_unknown_kg_construction_module() -> None:
    assert get_kg_construction_module("unknown") is None
