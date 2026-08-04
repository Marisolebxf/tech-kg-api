from datetime import date
from types import SimpleNamespace

from infra.graph_db.models import GraphEdge, GraphNode
from service.expert_alumni_relation import ExpertAlumniRelationService
from service.expert_colleague_relation import ExpertColleagueRelationService
from service.expert_cooperation_achievement import ExpertCooperationAchievementService
from service.expert_indirect_relation import ExpertIndirectRelationService
from service.industry_chain_panorama import IndustryChainPanoramaService
from service.industry_chain_topn_event import IndustryChainTopNEventService


def scholar(scholar_id: str, name: str, org: str, education: str = ""):
    return SimpleNamespace(
        scholar_id=scholar_id,
        name_zh=name,
        name_en=name,
        scholar_org_name_zh=org,
        scholar_org_name_en=org,
        scholar_org_id=f"org-{org}",
        work_experience_zh=org,
        work_experience_en=org,
        education_background_zh=education,
        education_background_en=education,
        paper_nums=10,
        citation_nums=20,
        h_index=5,
    )


class ScholarDAOStub:
    def __init__(self):
        self.items = {
            "a": scholar("a", "甲", "共同实验室", "共同大学"),
            "b": scholar("b", "乙", "共同实验室", "共同大学"),
            "c": scholar("c", "丙", "其他机构", "其他大学"),
        }

    def get_by_scholar_id(self, scholar_id):
        return self.items.get(scholar_id)

    def search_by_name(self, keyword, limit=20):
        return []

    def list_active(self, limit=500):
        return list(self.items.values())

    def list_direct_coauthor_relations(self, **kwargs):
        return [{"evidence_kind": "paper", "co_paper_count": 3, "evidence_titles": ["论文A"]}]

    def list_direct_patent_relations(self, **kwargs):
        return [{"evidence_kind": "patent", "evidence_count": 2, "evidence_titles": ["专利A"]}]

    def list_direct_project_relations(self, **kwargs):
        return [{"evidence_kind": "project", "evidence_count": 1, "evidence_titles": ["项目A"]}]


def test_colleague_and_alumni_services_return_evidence() -> None:
    dao = ScholarDAOStub()
    colleagues = ExpertColleagueRelationService(dao).query(expert_id="a", limit=10)
    alumni = ExpertAlumniRelationService(dao).query(expert_id="a", limit=10)

    assert colleagues["total"] == 1
    assert colleagues["items"][0]["expert"]["id"] == "b"
    assert "共同实验室" in colleagues["items"][0]["sharedInstitutions"]
    assert alumni["total"] == 1
    assert "共同大学" in alumni["items"][0]["sharedInstitutions"]


def test_cooperation_achievement_aggregates_all_categories() -> None:
    result = ExpertCooperationAchievementService(ScholarDAOStub()).query(
        expert_a_id="a", expert_b_id="b"
    )

    assert result["totalAchievements"] == 6
    assert result["categoryCounts"] == {"paper": 3, "patent": 2, "project": 1}


class GraphStub:
    def __init__(self):
        self.nodes = {
            key: GraphNode(id=key, labels=["Scholar"], properties={"name": key.upper()})
            for key in ("a", "b", "c", "d")
        }
        self.edges = {
            "a": [GraphEdge(id="a-b@0", type="COAUTHOR", source_id="a", target_id="b")],
            "b": [
                GraphEdge(id="a-b@0", type="COAUTHOR", source_id="a", target_id="b"),
                GraphEdge(id="b-c@0", type="COAUTHOR", source_id="b", target_id="c"),
                GraphEdge(id="b-d@0", type="PROJECT", source_id="b", target_id="d"),
            ],
        }

    def get_node(self, node_id):
        return self.nodes.get(str(node_id))

    def get_node_edges(self, node_id, **kwargs):
        return self.edges.get(str(node_id), [])


def test_indirect_relation_finds_two_hop_non_direct_nodes() -> None:
    result = ExpertIndirectRelationService(GraphStub()).query(
        expert_id="a", edge_types=["COAUTHOR"], limit=10
    )

    assert result["total"] == 1
    assert result["items"][0]["target"]["id"] == "c"
    assert result["items"][0]["paths"][0]["nodes"] == ["a", "b", "c"]


class IndustryDAOStub:
    def list_news(self, **kwargs):
        return [
            {
                "chain_code": "C1",
                "chain_name": "芯片",
                "news_id": "N1",
                "title": "芯片技术突破",
                "summary": "芯片产业取得突破",
                "relaese_date": date.today(),
                "source": "测试源",
            }
        ]

    def list_nodes(self, **kwargs):
        return [
            {"chain_code": "C1", "chain_name": "芯片", "node_id": "root", "node_name": "芯片"},
            {
                "chain_code": "C1",
                "chain_name": "芯片",
                "node_id": "design",
                "node_name": "设计",
                "parent_id": "root",
            },
        ]

    def list_organizations(self, **kwargs):
        return [{"chain_code": "C1", "node_id": "design", "antitypic": "O1", "chain_score": 90}]

    def list_patents(self, **kwargs):
        return [{"chain_code": "C1", "node_id": "design", "apno": "P1", "pat_name": "专利"}]

    def list_products(self, **kwargs):
        return [{"chain_code": "C1", "antitypic": "O1", "tech_product": "芯片产品"}]


def test_industry_event_ranking_and_panorama_are_data_backed() -> None:
    dao = IndustryDAOStub()
    events = IndustryChainTopNEventService(dao=dao).query(
        chain_code="C1",
        keyword="芯片",
        node_id=None,
        since=None,
        until=None,
        top_n=10,
        persist=False,
        space=None,
    )
    panorama = IndustryChainPanoramaService(dao=dao).query(
        chain_code="C1", keyword=None, include_events=True, limit_per_type=100
    )

    assert events["items"][0]["rank"] == 1
    assert events["items"][0]["score"] > 50
    assert panorama["counts"] == {
        "chainNodes": 2,
        "organizations": 1,
        "products": 1,
        "patents": 1,
        "events": 1,
    }
    assert any(edge["type"] == "HAS_ORGANIZATION" for edge in panorama["graph"]["edges"])
