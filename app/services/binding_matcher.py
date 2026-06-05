"""Rule-based binding matcher for cross-database entity alignment.

Provides similarity functions and matching logic for:
- talent ↔ cn_paper author
- talent ↔ patent inventor
- cn_organization ↔ cn_organization
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def jaccard_similarity(a: str, b: str) -> float:
    """Character-level Jaccard similarity between two strings."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def edit_distance_similarity(a: str, b: str) -> float:
    """Normalized edit distance similarity (1 - normalized_distance)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    m, n = len(a), len(b)
    # Dynamic programming edit distance
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    distance = dp[n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len)


def name_match_score(name_a: str, name_b: str) -> float:
    """Score name similarity using both exact match and edit distance."""
    if not name_a or not name_b:
        return 0.0
    name_a = name_a.strip()
    name_b = name_b.strip()
    if name_a == name_b:
        return 1.0
    return edit_distance_similarity(name_a, name_b)


def org_similarity_score(org_a: str, org_b: str) -> float:
    """Score organization name similarity using Jaccard + edit distance."""
    if not org_a or not org_b:
        return 0.0
    org_a = org_a.strip()
    org_b = org_b.strip()
    if org_a == org_b:
        return 1.0
    jaccard = jaccard_similarity(org_a, org_b)
    edit_sim = edit_distance_similarity(org_a, org_b)
    # Containment check (e.g., "浙大" in "浙江大学")
    containment = 0.0
    if org_a in org_b or org_b in org_a:
        containment = min(len(org_a), len(org_b)) / max(len(org_a), len(org_b))
    return max(jaccard, edit_sim, containment)


class BindingMatcher:
    """Rule-based matcher for cross-database entity binding candidates."""

    TALENT_PAPER_WEIGHTS = {"name": 0.6, "org": 0.3, "field": 0.1}
    TALENT_PAPER_THRESHOLD = 0.5

    TALENT_PATENT_WEIGHTS = {"name": 0.7, "org": 0.3}
    TALENT_PATENT_THRESHOLD = 0.5

    ORG_ORG_THRESHOLD = 0.6

    def match_talent_paper(self, talents: list[dict[str, Any]], papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Match talent nodes to cn_paper author nodes.
        Returns list of candidate binding pairs with rule scores.
        """
        candidates = []
        w = self.TALENT_PAPER_WEIGHTS

        for talent in talents:
            for paper in papers:
                name_score = name_match_score(talent.get("name_zh", ""), paper.get("authors", ""))
                if name_score < 1.0:
                    en_score = name_match_score(talent.get("name_en", ""), paper.get("authors", ""))
                    name_score = max(name_score, en_score)

                org_score = org_similarity_score(talent.get("scholar_org_name_zh", ""), paper.get("institution", ""))
                if org_score < 1.0:
                    en_org_score = org_similarity_score(talent.get("scholar_org_name_en", ""), paper.get("institution", ""))
                    org_score = max(org_score, en_org_score)

                field_score = jaccard_similarity(talent.get("fields", ""), paper.get("keywords", ""))

                rule_score = w["name"] * name_score + w["org"] * org_score + w["field"] * field_score

                if rule_score >= self.TALENT_PAPER_THRESHOLD:
                    candidates.append({
                        "talent": talent, "paper": paper,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_score, 4),
                        "org_score": round(org_score, 4),
                        "field_score": round(field_score, 4),
                    })
        return candidates

    def match_talent_patent(self, talents: list[dict[str, Any]], patents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Match talent nodes to patent inventor nodes."""
        candidates = []
        w = self.TALENT_PATENT_WEIGHTS

        for talent in talents:
            for patent in patents:
                name_score = name_match_score(talent.get("name_zh", ""), patent.get("first_inventor_name", ""))
                org_score = org_similarity_score(talent.get("scholar_org_name_zh", ""), patent.get("first_applicant_name", ""))

                rule_score = w["name"] * name_score + w["org"] * org_score

                if rule_score >= self.TALENT_PATENT_THRESHOLD:
                    candidates.append({
                        "talent": talent, "patent": patent,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_score, 4),
                        "org_score": round(org_score, 4),
                    })
        return candidates

    def match_org_org(self, orgs_a: list[dict[str, Any]], orgs_b: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Match organization nodes across databases."""
        candidates = []

        for org_a in orgs_a:
            for org_b in orgs_b:
                if org_a.get("org_id") and org_a["org_id"] == org_b.get("org_id"):
                    continue

                name_sim = org_similarity_score(org_a.get("name_cn", ""), org_b.get("name_cn", ""))

                geo_bonus = 0.0
                if org_a.get("province") and org_a["province"] == org_b.get("province"):
                    geo_bonus += 0.1
                if org_a.get("city") and org_a["city"] == org_b.get("city"):
                    geo_bonus += 0.1

                type_bonus = 0.0
                if org_a.get("org_type") and org_a["org_type"] == org_b.get("org_type"):
                    type_bonus = 0.05

                rule_score = min(name_sim + geo_bonus + type_bonus, 1.0)

                if rule_score >= self.ORG_ORG_THRESHOLD:
                    candidates.append({
                        "org_a": org_a, "org_b": org_b,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_sim, 4),
                        "geo_bonus": round(geo_bonus, 4),
                        "type_bonus": round(type_bonus, 4),
                    })
        return candidates
