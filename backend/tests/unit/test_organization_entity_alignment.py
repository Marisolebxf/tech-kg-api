from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from infra.milvus import MilvusSearchHit
from service.organization_entity_alignment import (
    BM25SparseEncoder,
    HashingDenseEncoder,
    HybridOrganizationResolver,
    OrganizationAlignmentContext,
    OrganizationHybridMatcher,
    normalize_alignment_text,
    tokenize_alignment_text,
)


class FakeStore:
    def __init__(
        self,
        *,
        external_matches: list[dict[str, Any]] | None = None,
        hits: list[MilvusSearchHit] | None = None,
    ) -> None:
        self.external_matches = external_matches or []
        self.hits = hits or []
        self.hybrid_calls = 0

    def query_by_external_id(
        self,
        entity_type: str,
        external_id: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        assert entity_type == "Organization"
        assert external_id
        return self.external_matches[:limit]

    def hybrid_search(self, *args: Any, **kwargs: Any) -> list[MilvusSearchHit]:
        self.hybrid_calls += 1
        return self.hits


class EmptyExactResolver:
    def resolve(self, name: Any, context: Any = None) -> None:
        return None


def fitted_bm25() -> BM25SparseEncoder:
    encoder = BM25SparseEncoder()
    encoder.fit(
        [
            "中国科学院计算技术研究所 北京",
            "Institute of Computing Technology Beijing",
            "北京科技有限公司 海淀区",
        ]
    )
    return encoder


def test_normalization_and_mixed_language_tokenization() -> None:
    assert normalize_alignment_text("  ＡＢＣ（中国）有限公司 ") == "abc 中国 有限公司"
    tokens = tokenize_alignment_text("ABC中国")
    assert "abc" in tokens
    assert "中国" in tokens


def test_bm25_state_round_trip(tmp_path: Path) -> None:
    encoder = fitted_bm25()
    query = encoder.encode_query("中国科学院")
    assert query
    path = tmp_path / "organization.bm25.json"
    encoder.save(path)
    loaded = BM25SparseEncoder.load(path)
    assert loaded.encode_query("中国科学院") == query
    assert loaded.encode_document("中国科学院计算技术研究所")


def test_hashing_dense_encoder_is_deterministic_and_normalized() -> None:
    encoder = HashingDenseEncoder(64)
    first = encoder.encode("中国科学院计算技术研究所")
    second = encoder.encode("中国科学院计算技术研究所")
    assert first == second
    assert len(first) == 64
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)


def test_external_id_unique_match_bypasses_hybrid_search() -> None:
    store = FakeStore(
        external_matches=[{"vid": "org_ict", "canonical_name": "计算所"}],
    )
    matcher = OrganizationHybridMatcher(
        store,  # type: ignore[arg-type]
        fitted_bm25(),
        HashingDenseEncoder(64),
    )
    decision = matcher.align(
        OrganizationAlignmentContext(
            name="任意名称",
            external_id="91310000",
            source_table="dwd_org_shareholder_info",
            source_record_id="row-1",
        )
    )
    assert decision.status == "matched"
    assert decision.method == "external_id_exact"
    assert decision.selected_vid == "org_ict"
    assert store.hybrid_calls == 0


def test_high_confidence_hybrid_match() -> None:
    store = FakeStore(
        hits=[
            MilvusSearchHit(
                vid="org_ict",
                score=1.0,
                fields={
                    "canonical_name": "中国科学院计算技术研究所",
                    "aliases": "[]",
                    "country_code": "CN",
                    "city": "北京",
                },
            ),
            MilvusSearchHit(
                vid="org_other",
                score=0.2,
                fields={
                    "canonical_name": "中国科学院物理研究所",
                    "aliases": "[]",
                    "country_code": "CN",
                    "city": "北京",
                },
            ),
        ]
    )
    matcher = OrganizationHybridMatcher(
        store,  # type: ignore[arg-type]
        fitted_bm25(),
        HashingDenseEncoder(64),
    )
    decision = matcher.align(
        OrganizationAlignmentContext(
            name="中国科学院计算技术研究所",
            country_code="CN",
            city="北京",
            source_table="dwd_forg_subsidiary_info",
            source_record_id="row-2",
        )
    )
    assert decision.status == "matched"
    assert decision.selected_vid == "org_ict"
    assert decision.margin >= 0.08


def test_ambiguous_candidates_are_not_auto_linked() -> None:
    store = FakeStore(
        hits=[
            MilvusSearchHit(
                vid="org_a",
                score=1.0,
                fields={"canonical_name": "北京科技有限公司", "aliases": "[]"},
            ),
            MilvusSearchHit(
                vid="org_b",
                score=0.99,
                fields={"canonical_name": "北京科技有限公司", "aliases": "[]"},
            ),
        ]
    )
    matcher = OrganizationHybridMatcher(
        store,  # type: ignore[arg-type]
        fitted_bm25(),
        HashingDenseEncoder(64),
        threshold=0.80,
        margin=0.08,
    )
    decision = matcher.align(
        OrganizationAlignmentContext(
            name="北京科技有限公司",
            source_table="dwd_org_invest_info",
            source_record_id="row-3",
        )
    )
    assert decision.status == "review"
    assert decision.selected_vid is None


def test_hybrid_resolver_returns_existing_organization_id_only() -> None:
    store = FakeStore(
        external_matches=[{"vid": "org_existing", "canonical_name": "目标公司"}],
    )
    matcher = OrganizationHybridMatcher(
        store,  # type: ignore[arg-type]
        fitted_bm25(),
        HashingDenseEncoder(64),
    )
    resolver = HybridOrganizationResolver(EmptyExactResolver(), matcher)
    resolved = resolver.resolve(
        "目标公司",
        {
            "source_table": "dwd_org_invest_info",
            "source_record_id": "row-4",
            "external_id": "target-001",
        },
    )
    assert resolved == "existing"
