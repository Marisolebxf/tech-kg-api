"""Organization-domain BM25, dense-vector and hybrid entity alignment."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rapidfuzz import fuzz

from infra.milvus import MilvusSearchHit, OrganizationMilvusStore

_ALNUM_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def normalize_alignment_text(value: Any) -> str:
    """Normalize text for matching without deleting legal entity suffixes."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    text = re.sub(r"[\s\u3000]+", " ", text)
    text = re.sub(r"[()（）【】\[\],，。.;；:：'\"“”‘’]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_alignment_text(value: Any) -> list[str]:
    """Tokenize mixed Chinese/English text for deterministic BM25 retrieval."""
    text = normalize_alignment_text(value)
    tokens = _ALNUM_RE.findall(text)
    for segment in _CJK_RE.findall(text):
        tokens.extend(segment)
        if len(segment) > 1:
            tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
        if len(segment) > 2:
            tokens.extend(segment[index : index + 3] for index in range(len(segment) - 2))
    return [token for token in tokens if token]


@dataclass
class BM25SparseEncoder:
    """Corpus-fitted BM25 encoder compatible with Milvus sparse vectors."""

    vocabulary: dict[str, int] = field(default_factory=dict)
    document_frequency: dict[str, int] = field(default_factory=dict)
    document_count: int = 0
    average_document_length: float = 0.0
    k1: float = 1.5
    b: float = 0.75

    @property
    def fitted(self) -> bool:
        return self.document_count > 0 and bool(self.vocabulary)

    def fit(self, documents: Sequence[str]) -> None:
        frequencies: Counter[str] = Counter()
        total_length = 0
        for document in documents:
            tokens = tokenize_alignment_text(document)
            total_length += len(tokens)
            frequencies.update(set(tokens))
        self.document_count = len(documents)
        self.average_document_length = (
            total_length / self.document_count if self.document_count else 0.0
        )
        self.document_frequency = dict(frequencies)
        self.vocabulary = {
            token: index for index, token in enumerate(sorted(self.document_frequency))
        }

    def _idf(self, token: str) -> float:
        frequency = self.document_frequency.get(token, 0)
        return math.log(1.0 + (self.document_count - frequency + 0.5) / (frequency + 0.5))

    def encode_document(self, document: str) -> dict[int, float]:
        if not self.fitted:
            raise RuntimeError("BM25 encoder must be fitted before encoding documents")
        tokens = tokenize_alignment_text(document)
        term_frequency = Counter(tokens)
        length = len(tokens)
        normalization = self.k1 * (
            1.0
            - self.b
            + self.b
            * (length / self.average_document_length if self.average_document_length else 0.0)
        )
        vector: dict[int, float] = {}
        for token, frequency in term_frequency.items():
            dimension = self.vocabulary.get(token)
            if dimension is None:
                continue
            value = self._idf(token) * (frequency * (self.k1 + 1.0) / (frequency + normalization))
            if value:
                vector[dimension] = float(value)
        return vector

    def encode_query(self, query: str) -> dict[int, float]:
        if not self.fitted:
            raise RuntimeError("BM25 encoder must be fitted before encoding queries")
        vector: dict[int, float] = {}
        for token in set(tokenize_alignment_text(query)):
            dimension = self.vocabulary.get(token)
            if dimension is not None:
                vector[dimension] = 1.0
        return vector

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "vocabulary": self.vocabulary,
            "document_frequency": self.document_frequency,
            "document_count": self.document_count,
            "average_document_length": self.average_document_length,
            "k1": self.k1,
            "b": self.b,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> BM25SparseEncoder:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            vocabulary={str(key): int(value) for key, value in payload["vocabulary"].items()},
            document_frequency={
                str(key): int(value) for key, value in payload["document_frequency"].items()
            },
            document_count=int(payload["document_count"]),
            average_document_length=float(payload["average_document_length"]),
            k1=float(payload.get("k1", 1.5)),
            b=float(payload.get("b", 0.75)),
        )


@dataclass(frozen=True)
class HashingDenseEncoder:
    """Deterministic multilingual character/word n-gram dense encoder.

    Organization names are dominated by lexical identity rather than broad
    topic semantics. Feature hashing therefore provides a local, reproducible
    dense vector and does not require an external model or API credential.
    """

    dimension: int = 384

    def encode(self, text: str) -> list[float]:
        if self.dimension <= 0:
            raise ValueError("dense dimension must be positive")
        vector = [0.0] * self.dimension
        tokens = tokenize_alignment_text(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector

    def encode_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.encode(text) for text in texts]


@dataclass(frozen=True)
class OrganizationAlignmentContext:
    """Structured evidence accompanying one unresolved organization mention."""

    name: str
    source_table: str
    source_record_id: str
    external_id: str | None = None
    country_code: str | None = None
    country: str | None = None
    province: str | None = None
    city: str | None = None
    address: str | None = None

    def query_text(self) -> str:
        return " ".join(
            value
            for value in (
                self.name,
                self.external_id,
                self.country_code,
                self.country,
                self.province,
                self.city,
                self.address,
            )
            if value
        )


@dataclass(frozen=True)
class ScoredOrganizationCandidate:
    vid: str
    canonical_name: str
    score: float
    retrieval_score: float
    name_score: float
    evidence: tuple[str, ...]
    fields: dict[str, Any]


@dataclass(frozen=True)
class OrganizationAlignmentDecision:
    status: str
    context: OrganizationAlignmentContext
    selected_vid: str | None
    score: float
    margin: float
    method: str
    candidates: tuple[ScoredOrganizationCandidate, ...] = ()
    reason: str = ""


class ExactNameResolver(Protocol):
    def resolve(self, name: Any, context: Mapping[str, Any] | None = None) -> str | None: ...


def _aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    return [item.strip() for item in re.split(r"[;；|]", raw) if item.strip()]


def _equal(left: Any, right: Any) -> bool:
    return bool(
        (normalized_left := normalize_alignment_text(left))
        and normalized_left == normalize_alignment_text(right)
    )


class OrganizationHybridMatcher:
    """Retrieve and conservatively score existing Organization candidates."""

    def __init__(
        self,
        store: OrganizationMilvusStore,
        bm25: BM25SparseEncoder,
        dense: HashingDenseEncoder,
        *,
        threshold: float = 0.88,
        margin: float = 0.08,
        top_k: int = 20,
    ) -> None:
        self.store = store
        self.bm25 = bm25
        self.dense = dense
        self.threshold = threshold
        self.margin = margin
        self.top_k = top_k

    def _score_hit(
        self,
        context: OrganizationAlignmentContext,
        hit: MilvusSearchHit,
    ) -> ScoredOrganizationCandidate:
        fields = hit.fields
        names = [
            fields.get("canonical_name"),
            *_aliases(fields.get("aliases")),
        ]
        name_score = max(
            (
                fuzz.WRatio(
                    normalize_alignment_text(context.name),
                    normalize_alignment_text(name),
                )
                / 100.0
                for name in names
                if name
            ),
            default=0.0,
        )
        retrieval_score = max(0.0, min(float(hit.score), 1.0))
        score = 0.60 * name_score + 0.25 * retrieval_score
        evidence: list[str] = []
        if name_score == 1.0:
            evidence.append("normalized_name_exact")
        elif name_score >= 0.9:
            evidence.append("name_high_similarity")

        structured_weight = 0.0
        for label, source_value, candidate_value, weight in (
            ("country_code", context.country_code, fields.get("country_code"), 0.06),
            ("country", context.country, fields.get("country"), 0.04),
            ("province", context.province, fields.get("province"), 0.04),
            ("city", context.city, fields.get("city"), 0.06),
        ):
            if source_value and candidate_value:
                if _equal(source_value, candidate_value):
                    structured_weight += weight
                    evidence.append(f"{label}_exact")
                elif label in {"country_code", "country"}:
                    structured_weight -= weight
                    evidence.append(f"{label}_conflict")
        if context.address and fields.get("address"):
            address_score = (
                fuzz.WRatio(
                    normalize_alignment_text(context.address),
                    normalize_alignment_text(fields["address"]),
                )
                / 100.0
            )
            structured_weight += 0.10 * address_score
            if address_score >= 0.85:
                evidence.append("address_high_similarity")
        score = max(0.0, min(score + structured_weight, 1.0))
        if name_score == 1.0 and not any(item.endswith("_conflict") for item in evidence):
            score = max(score, 0.95)
        return ScoredOrganizationCandidate(
            vid=hit.vid,
            canonical_name=str(fields.get("canonical_name") or ""),
            score=score,
            retrieval_score=retrieval_score,
            name_score=name_score,
            evidence=tuple(evidence),
            fields=fields,
        )

    def align(self, context: OrganizationAlignmentContext) -> OrganizationAlignmentDecision:
        if context.external_id:
            exact = self.store.query_by_external_id("Organization", context.external_id)
            if len(exact) == 1:
                return OrganizationAlignmentDecision(
                    status="matched",
                    context=context,
                    selected_vid=str(exact[0]["vid"]),
                    score=1.0,
                    margin=1.0,
                    method="external_id_exact",
                    reason="one Organization has the same external identifier",
                )
            if len(exact) > 1:
                return OrganizationAlignmentDecision(
                    status="review",
                    context=context,
                    selected_vid=None,
                    score=1.0,
                    margin=0.0,
                    method="external_id_conflict",
                    reason="multiple Organizations share the same external identifier",
                )

        query_text = context.query_text()
        sparse_vector = self.bm25.encode_query(query_text)
        if not sparse_vector:
            return OrganizationAlignmentDecision(
                status="rejected",
                context=context,
                selected_vid=None,
                score=0.0,
                margin=0.0,
                method="hybrid",
                reason="query has no term present in the fitted Organization corpus",
            )
        hits = self.store.hybrid_search(
            "Organization",
            dense_vector=self.dense.encode(query_text),
            sparse_vector=sparse_vector,
            limit=self.top_k,
        )
        candidates = tuple(
            sorted(
                (self._score_hit(context, hit) for hit in hits),
                key=lambda candidate: (-candidate.score, candidate.vid),
            )
        )
        if not candidates:
            return OrganizationAlignmentDecision(
                status="rejected",
                context=context,
                selected_vid=None,
                score=0.0,
                margin=0.0,
                method="hybrid",
                reason="Milvus returned no Organization candidate",
            )
        best = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        score_margin = best.score - second_score
        if best.score >= self.threshold and score_margin >= self.margin:
            status = "matched"
            selected_vid = best.vid
            reason = "score and top-1 margin satisfy automatic alignment policy"
        elif best.score >= self.threshold - 0.12:
            status = "review"
            selected_vid = None
            reason = "candidate is plausible but confidence or margin is insufficient"
        else:
            status = "rejected"
            selected_vid = None
            reason = "best candidate is below the conservative matching threshold"
        return OrganizationAlignmentDecision(
            status=status,
            context=context,
            selected_vid=selected_vid,
            score=best.score,
            margin=score_margin,
            method="bm25_dense_hybrid",
            candidates=candidates[:5],
            reason=reason,
        )


class AlignmentAuditWriter:
    """Append machine-readable decisions without changing graph ontology."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def write(self, decision: OrganizationAlignmentDecision) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(decision), ensure_ascii=False, default=str))
            handle.write("\n")


class HybridOrganizationResolver:
    """Use exact unique names first, then high-confidence Milvus alignment."""

    def __init__(
        self,
        exact: ExactNameResolver,
        matcher: OrganizationHybridMatcher,
        audit: AlignmentAuditWriter | None = None,
    ) -> None:
        self.exact = exact
        self.matcher = matcher
        self.audit = audit or AlignmentAuditWriter(None)

    @staticmethod
    def _org_id_from_vid(vid: str) -> str | None:
        return vid[4:] if vid.startswith("org_") and len(vid) > 4 else None

    def resolve(self, name: Any, context: Mapping[str, Any] | None = None) -> str | None:
        exact_id = self.exact.resolve(name, context)
        if exact_id is not None:
            return exact_id
        normalized_name = str(name).strip() if name is not None else ""
        if not normalized_name or context is None:
            return None
        alignment_context = OrganizationAlignmentContext(
            name=normalized_name,
            source_table=str(context.get("source_table") or ""),
            source_record_id=str(context.get("source_record_id") or ""),
            external_id=str(context["external_id"]) if context.get("external_id") else None,
            country_code=str(context["country_code"]) if context.get("country_code") else None,
            country=str(context["country"]) if context.get("country") else None,
            province=str(context["province"]) if context.get("province") else None,
            city=str(context["city"]) if context.get("city") else None,
            address=str(context["address"]) if context.get("address") else None,
        )
        decision = self.matcher.align(alignment_context)
        self.audit.write(decision)
        if decision.status != "matched" or decision.selected_vid is None:
            return None
        return self._org_id_from_vid(decision.selected_vid)

    def resolve_exact(self, name: Any) -> str | None:
        """Expose the cheap exact phase so stable source IDs never trigger Milvus."""
        resolver = getattr(self.exact, "resolve_exact", None)
        return resolver(name) if resolver is not None else self.exact.resolve(name)
