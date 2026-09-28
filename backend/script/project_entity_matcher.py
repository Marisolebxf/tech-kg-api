"""Strict candidate-driven graph matching for Project ETL."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from infra.graph_db import GraphRequestError, TRSGraphClient
from script.project_graph_utils import resolve_organization_id

logger = logging.getLogger("script.project_entity_matcher")

# 共享图库的瞬态拒绝：内存高水位（use space failed / watermark）与会话池被
# 其它租户瞬时占满（no extra session）。过一会儿自然恢复，读操作重试无副作用。
_TRANSIENT_GRAPH_ERROR_TOKENS = ("watermark", "use space failed", "no extra session")


def retry_transient(fn: Any, *, tries: int = 10, wait_seconds: float = 30.0) -> Any:
    """通用瞬态重试：仅用于幂等调用（读 / merge / update）。

    共享宿主内存贴近 0.80 高水位时，trs-graph 的 nGQL 或 schema REST 调用会在
    USE space 准入阶段被整批拒绝（400/500），会话池也可能被其它租户瞬时占满；
    这类失败过一会儿自然恢复，直接抛出会把长 ETL 在写入前整体打死。
    """
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except GraphRequestError as exc:
            text = f"{exc} {getattr(exc, 'body', '')}"
            if attempt < tries and any(token in text for token in _TRANSIENT_GRAPH_ERROR_TOKENS):
                logger.warning(
                    "共享图库水位/会话池瞬时不足（第 %d/%d 次），%.0fs 后重试: %s",
                    attempt,
                    tries - 1,
                    wait_seconds,
                    str(exc)[:200],
                )
                time.sleep(wait_seconds)
                continue
            raise


def _read_with_transient_retry(
    graph: TRSGraphClient,
    query: str,
    *,
    tries: int = 10,
    wait_seconds: float = 30.0,
) -> Any:
    """池加载查询的水位退避重试。"""
    return retry_transient(
        lambda: graph.execute_read(query), tries=tries, wait_seconds=wait_seconds
    )


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_doi(value: Any) -> str:
    value = normalize_text(value)
    value = re.sub(r"^https?://", "", value, count=1)
    for prefix in ("doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.strip()


def normalize_patent_number(value: Any) -> str:
    return re.sub(r"[\s\-./]", "", str(value or "").strip()).upper()


@dataclass(frozen=True)
class MatchResult:
    status: str
    vid: str | None = None
    method: str = ""
    evidence: str = ""


class ExactIndex:
    def __init__(self) -> None:
        self._values: dict[str, set[str]] = {}

    def add(self, value: Any, vid: str, *, normalizer=normalize_text) -> None:
        key = normalizer(value)
        if key:
            self._values.setdefault(key, set()).add(vid)

    def match(self, value: Any, *, method: str, normalizer=normalize_text) -> MatchResult:
        key = normalizer(value)
        vids = self._values.get(key, set()) if key else set()
        if len(vids) == 1:
            return MatchResult("matched", next(iter(vids)), method, key)
        return MatchResult("ambiguous" if len(vids) > 1 else "not_found", evidence=key)


class ProjectEntityMatcher:
    def __init__(self) -> None:
        self.organization = ExactIndex()
        self.person = ExactIndex()
        self.paper_doi = ExactIndex()
        self.paper_title = ExactIndex()
        self.paper_title_year = ExactIndex()
        self.patent_number = ExactIndex()
        self.patent_title = ExactIndex()
        self.report_title = ExactIndex()
        self.report_title_year = ExactIndex()
        # vid → 稳定 organization_id（来自 source_record_id / org_id 或 VID 解析）
        self.organization_ids: dict[str, str] = {}

    def organization_id(self, vid: str) -> str:
        return resolve_organization_id(vid, cache=self.organization_ids)

    def remember_organization(self, vid: str, row: dict[str, Any]) -> None:
        oid = resolve_organization_id(vid, node_props=row)
        if oid:
            self.organization_ids[str(vid)] = oid

    @classmethod
    def from_graph(
        cls, graph: TRSGraphClient, candidates: dict[str, set[str]]
    ) -> ProjectEntityMatcher:
        matcher = cls()
        for row in _candidate_rows(
            graph,
            "Organization",
            ("name_cn", "name_en", "source_record_id", "org_id"),
            {"name_cn": candidates["organization"], "name_en": candidates["organization"]},
        ):
            vid = str(row["vid"])
            for prop in ("name_cn", "name_en"):
                matcher.organization.add(row.get(prop), vid)
            matcher.remember_organization(vid, row)
        for row in _candidate_rows(
            graph,
            "Person",
            ("name_zh", "name_cn", "name_en"),
            {prop: candidates["person"] for prop in ("name_zh", "name_cn", "name_en")},
        ):
            for prop in ("name_zh", "name_cn", "name_en"):
                matcher.person.add(row.get(prop), row["vid"])
        for row in _candidate_rows(
            graph,
            "Paper",
            ("doi", "title_zh", "title_en", "publication_year"),
            {
                "doi": candidates["paper_doi"],
                "title_zh": candidates["paper_title"],
                "title_en": candidates["paper_title"],
            },
        ):
            matcher.paper_doi.add(row.get("doi"), row["vid"], normalizer=normalize_doi)
            year = normalize_text(row.get("publication_year"))
            for prop in ("title_zh", "title_en"):
                title = row.get(prop)
                matcher.paper_title.add(title, row["vid"])
                if normalize_text(title) and year:
                    matcher.paper_title_year.add(f"{title}|{year}", row["vid"])
        for row in _candidate_rows(
            graph,
            "Patent",
            (
                "application_number",
                "publication_number",
                "patent_id",
                "title_original",
                "title_zh",
                "title_en",
            ),
            {
                **{
                    prop: candidates["patent_number"]
                    for prop in ("application_number", "publication_number", "patent_id")
                },
                **{
                    prop: candidates["patent_title"]
                    for prop in ("title_original", "title_zh", "title_en")
                },
            },
        ):
            for prop in ("application_number", "publication_number", "patent_id"):
                matcher.patent_number.add(
                    row.get(prop), row["vid"], normalizer=normalize_patent_number
                )
            for prop in ("title_original", "title_zh", "title_en"):
                matcher.patent_title.add(row.get(prop), row["vid"])
        for row in _candidate_rows(
            graph,
            "Report",
            ("title_cn", "title_en", "publication_date"),
            {
                "title_cn": candidates["report_title"],
                "title_en": candidates["report_title"],
            },
        ):
            year = normalize_text(row.get("publication_date"))[:4]
            for prop in ("title_cn", "title_en"):
                title = row.get(prop)
                matcher.report_title.add(title, row["vid"])
                if normalize_text(title) and year:
                    matcher.report_title_year.add(f"{title}|{year}", row["vid"])
        return matcher

    def match_paper(self, item: dict[str, Any]) -> MatchResult:
        doi = item.get("doi")
        if normalize_doi(doi):
            result = self.paper_doi.match(doi, method="doi_exact", normalizer=normalize_doi)
            if result.status != "not_found":
                return result
        title, year = item.get("title"), item.get("year")
        if normalize_text(title) and normalize_text(year):
            result = self.paper_title_year.match(f"{title}|{year}", method="title_year_exact")
            if result.status != "not_found":
                return result
        return self.paper_title.match(title, method="title_exact")

    def match_patent(self, item: dict[str, Any]) -> MatchResult:
        number = (
            item.get("patent_number")
            or item.get("application_number")
            or item.get("publication_number")
            or item.get("patent_id")
        )
        if normalize_patent_number(number):
            result = self.patent_number.match(
                number,
                method="patent_number_exact",
                normalizer=normalize_patent_number,
            )
            if result.status != "not_found":
                return result
        return self.patent_title.match(
            item.get("patent_title") or item.get("title"), method="title_exact"
        )

    def match_report(self, item: dict[str, Any]) -> MatchResult:
        title, year = item.get("title"), item.get("year")
        if normalize_text(title) and normalize_text(year):
            result = self.report_title_year.match(f"{title}|{year}", method="title_year_exact")
            if result.status != "not_found":
                return result
        return self.report_title.match(title, method="title_exact")


def _candidate_rows(
    graph: TRSGraphClient,
    label: str,
    return_properties: tuple[str, ...],
    filters: dict[str, set[str]],
    *,
    chunk_size: int = 5000,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    projection = ", ".join(f"n.{label}.{prop} AS {prop}" for prop in return_properties)
    for filter_property, values in filters.items():
        clean_values = sorted({str(value).strip() for value in values if str(value).strip()})
        for offset in range(0, len(clean_values), chunk_size):
            literals = json.dumps(clean_values[offset : offset + chunk_size], ensure_ascii=False)
            query = (
                f"MATCH (n:{label}) WHERE n.{label}.{filter_property} IN {literals} "
                f"RETURN id(n) AS vid, {projection};"
            )
            try:
                result = _read_with_transient_retry(graph, query)
            except GraphRequestError as exc:
                if "IndexNotFound" not in exc.body:
                    raise
                return _scan_candidate_rows(graph, label, return_properties, filters)
            for row in result.records:
                rows[str(row["vid"])] = row
    return list(rows.values())


def _scan_candidate_rows(
    graph: TRSGraphClient,
    label: str,
    return_properties: tuple[str, ...],
    filters: dict[str, set[str]],
    *,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    """Fallback for shared Tags whose match properties do not have indexes."""
    projection = ", ".join(f"n.{label}.{prop} AS {prop}" for prop in return_properties)
    normalized_filters = {
        prop: {normalize_text(value) for value in values if normalize_text(value)}
        for prop, values in filters.items()
    }
    rows: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        query = (
            f"MATCH (n:{label}) RETURN id(n) AS vid, {projection} SKIP {offset} LIMIT {page_size};"
        )
        page = _read_with_transient_retry(graph, query).records
        for row in page:
            if any(
                normalize_text(row.get(prop)) in wanted
                for prop, wanted in normalized_filters.items()
            ):
                rows[str(row["vid"])] = row
        if len(page) < page_size:
            break
        offset += page_size
    return list(rows.values())
