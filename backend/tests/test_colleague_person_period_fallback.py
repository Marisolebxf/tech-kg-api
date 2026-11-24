"""Regression cases for organization-checked Person employment date fallback."""
import asyncio
import copy
import unittest

from service.expert_colleague_relation import ExpertColleagueRelationService

ORG_NAME = "清华大学计算机科学与技术系"
ORG_ID = "org_fc9e99b88bc7173d"
A_ID = "person_0209a7v6"
B_ID = "person_1S5195f4"


def person(vid, name, period):
    return {
        "id": vid, "labels": ["Person"],
        "properties": {
            "name_zh": name,
            "work_experience_institution_zh": ORG_NAME,
            "work_experience_date": period,
        },
    }


class Gateway:
    """Represent hydrated nodes and real, property-less affiliation edges."""
    def __init__(self):
        self.a = person(A_ID, "赵刚", "2017-01 至 2024-12")
        self.b = person(B_ID, "朱保君", "2018-03 至 2024-12")
        self.org = {
            "id": ORG_ID, "labels": ["Organization"],
            "properties": {"name_cn": ORG_NAME},
        }
        self.edges = [
            {"source": vid, "target": ORG_ID, "type": "AFFILIATED_WITH", "properties": {}}
            for vid in (A_ID, B_ID)
        ]
        self.api_calls = []

    async def resolve_person(self, keyword, space):
        return copy.deepcopy({A_ID: self.a, B_ID: self.b}.get(keyword))

    async def subgraph(self, node_id, *, edge_type=None, **kwargs):
        if edge_type == "COAUTHOR_WITH":
            return {"nodes": [], "edges": []}
        rows = [
            e for e in self.edges
            if node_id in (e["source"], e["target"])
            and (edge_type is None or e["type"] == edge_type)
        ]
        return copy.deepcopy({"nodes": [self.a, self.b, self.org], "edges": rows})

    async def search_paths(self, body, *, space):
        return {"items": []}


class EmploymentPeriodFallbackTests(unittest.TestCase):
    def setUp(self):
        self.service = ExpertColleagueRelationService()
        self.gateway = Gateway()

    def query(self, period="2015-01～2026-08"):
        return asyncio.run(self.service._query_impl(
            self.gateway, expert_id=A_ID, target_expert_id=B_ID,
            overlap_period=period, space="kgcfg_1808ec65d",
        ))

    def test_pair_with_empty_edge_properties_returns_expected_overlap(self):
        result = self.query()
        self.assertEqual(result["total"], 1)
        item = result["colleagues"][0]
        self.assertEqual(item["colleague"]["id"], B_ID)
        self.assertEqual(item["effectivePeriod"], "2018-03 至 2024-12")
        self.assertEqual(item["organizationId"], ORG_ID)
        self.assertEqual(item["employmentEdges"], {"expert": {}, "colleague": {}})
        self.assertEqual(self.gateway.edges[0]["properties"], {})

    def test_graph_scores_use_endpoints_for_the_two_employment_edges(self):
        self.gateway.edges[0]["properties"]["confidence"] = 0.25
        self.gateway.b["properties"]["organization_id"] = ORG_ID
        self.gateway.org["properties"]["organization_id"] = ORG_ID
        self.gateway.a["properties"]["work_experience_department_zh"] = "智能计算研究室"
        self.gateway.b["properties"]["work_experience_department_zh"] = "智能计算研究室"
        paper_ids = [
            "paper_20129466",
            "paper_19585803",
            "paper_20511496",
            "paper_22810886",
            "paper_28790652",
            "paper_29847493",
            "paper_37148955",
        ]

        async def search_paths(body, *, space):
            return {
                "items": [
                    {
                        "nodes": [
                            {
                                "id": pid,
                                "labels": ["Paper"],
                                "properties": {"title": pid, "year": "2019"},
                            },
                            self.gateway.b,
                        ],
                        "edges": [
                            {
                                "source": pid,
                                "target": vid,
                                "type": "AUTHORED_BY",
                                "properties": {"confidence": 1.0},
                            }
                            for vid in (A_ID, B_ID)
                        ],
                    }
                    for pid in paper_ids
                ]
            }

        subgraph = self.gateway.subgraph

        async def subgraph_with_coauthor(node_id, *, edge_type=None, **kwargs):
            if edge_type == "COAUTHOR_WITH":
                return {
                    "nodes": [self.gateway.a, self.gateway.b],
                    "edges": [{"source": A_ID, "target": B_ID, "type": "COAUTHOR_WITH"}],
                }
            return await subgraph(node_id, edge_type=edge_type, **kwargs)

        self.gateway.search_paths = search_paths
        self.gateway.subgraph = subgraph_with_coauthor
        result = self.query()
        scores = {
            (edge["source"], edge["target"], edge["label"]): edge["data"].get("confidence")
            for edge in result["graph"]["edges"]
        }
        self.assertEqual(
            scores,
            {
                (A_ID, B_ID, "同事关系"): 0.76,
                (A_ID, ORG_ID, "AFFILIATED_WITH"): 0.60,
                (B_ID, ORG_ID, "AFFILIATED_WITH"): 0.60,
                **{(pid, vid, "AUTHORED_BY"): 1.0 for pid in paper_ids for vid in (A_ID, B_ID)},
            },
        )
        self.assertEqual(self.gateway.edges[0]["properties"]["confidence"], 0.25)

    def test_source_organization_id_outranks_name_and_edge_confidence(self):
        self.gateway.org["properties"]["org_id"] = "verified_org_id"
        self.gateway.a["properties"]["organization_id"] = "verified_org_id"
        self.gateway.b["properties"]["scholar_org_id"] = "another_org_id"
        for edge in self.gateway.edges:
            edge["properties"]["confidence"] = 0.9

        affiliation_data = {
            edge["source"]: edge["data"]
            for edge in self.query()["graph"]["edges"]
            if edge["label"] == "AFFILIATED_WITH"
        }
        self.assertEqual(affiliation_data[A_ID]["confidence"], 1.0)
        self.assertNotIn("confidence", affiliation_data[B_ID])

    def test_missing_endpoint_evidence_ignores_stored_edge_confidence(self):
        self.gateway.a["properties"].pop("work_experience_institution_zh")
        self.gateway.edges[0]["properties"].update(
            work_experience_date="2017-01 至 2024-12", confidence=0.9
        )
        affiliation = next(
            edge
            for edge in self.query()["graph"]["edges"]
            if edge["label"] == "AFFILIATED_WITH" and edge["source"] == A_ID
        )
        self.assertNotIn("confidence", affiliation["data"])

    def test_reverse_pair_also_uses_both_person_periods(self):
        result = asyncio.run(self.service._query_impl(
            self.gateway, expert_id=B_ID, target_expert_id=A_ID,
            overlap_period="2015-01～2026-08", space="kgcfg_1808ec65d",
        ))
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["colleagues"][0]["colleague"]["id"], A_ID)

    def test_edge_dates_take_priority(self):
        for edge in self.gateway.edges:
            edge["properties"]["work_experience_date"] = "2020-01 至 2020-12"
        self.assertEqual(
            self.query()["colleagues"][0]["effectivePeriod"], "2020-01 至 2020-12"
        )

    def test_one_edge_and_one_person_period(self):
        self.gateway.edges[0]["properties"]["work_experience_date"] = "2021-01 至 2022-12"
        self.assertEqual(
            self.query()["colleagues"][0]["effectivePeriod"], "2021-01 至 2022-12"
        )

    def test_first_person_other_institution_is_rejected(self):
        self.gateway.a["properties"]["work_experience_institution_zh"] = "另一所大学"
        self.assertEqual(self.query()["total"], 0)

    def test_second_person_other_institution_is_rejected(self):
        self.gateway.b["properties"]["work_experience_institution_zh"] = "另一所大学"
        self.assertEqual(self.query()["total"], 0)

    def test_missing_person_period_is_rejected_on_either_side(self):
        for side in ("a", "b"):
            with self.subTest(side=side):
                self.gateway = Gateway()
                getattr(self.gateway, side)["properties"]["work_experience_date"] = None
                self.assertEqual(self.query()["total"], 0)

    def test_disjoint_person_periods_are_rejected(self):
        self.gateway.b["properties"]["work_experience_date"] = "2025-01 至 2026-08"
        self.assertEqual(self.query()["total"], 0)

    def test_request_outside_overlap_is_rejected(self):
        self.assertEqual(self.query("2025-01～2026-08")["total"], 0)

    def test_same_person_properties_do_not_replace_missing_affiliation_edge(self):
        self.gateway.edges.pop()
        self.assertEqual(self.query()["total"], 0)

    def test_missing_work_institution_does_not_use_current_scholar_org(self):
        props = self.gateway.b["properties"]
        props.pop("work_experience_institution_zh")
        props["scholar_org_name_zh"] = ORG_NAME
        self.assertEqual(self.query()["total"], 0)

    def test_english_work_institution_can_match_english_org(self):
        node = person(A_ID, "赵刚", "2017-01 至 2024-12")
        node["properties"].pop("work_experience_institution_zh")
        node["properties"]["work_experience_institution_en"] = "Tsinghua University"
        self.assertEqual(
            self.service._employment_period(
                node, {}, organization_name="Tsinghua University"
            ),
            self.service._parse_period("2017-01 至 2024-12"),
        )

    def test_blank_or_unparseable_person_period_is_rejected(self):
        for value in ("", None, "未知"):
            with self.subTest(value=value):
                self.gateway.b["properties"]["work_experience_date"] = value
                self.assertEqual(self.query()["total"], 0)

    def test_missing_organization_name_is_rejected(self):
        self.assertIsNone(self.service._employment_period(
            self.gateway.a, {}, organization_name=""
        ))

    def test_edge_only_data_still_works_without_person_history(self):
        for node, edge in zip(
            (self.gateway.a, self.gateway.b), self.gateway.edges, strict=True
        ):
            node["properties"].pop("work_experience_date")
            node["properties"].pop("work_experience_institution_zh")
            edge["properties"]["work_experience_date"] = "2019-01 至 2023-12"
        self.assertEqual(
            self.query()["colleagues"][0]["effectivePeriod"], "2019-01 至 2023-12"
        )


if __name__ == "__main__":
    unittest.main()
