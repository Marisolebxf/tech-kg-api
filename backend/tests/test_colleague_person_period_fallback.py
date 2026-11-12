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
