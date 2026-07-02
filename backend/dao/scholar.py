from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.domestic_project import OdsZhProject
from db_model.foreign_project import OdsEnProject
from db_model.patent import OdsPatent
from db_model.scholar import DwdScholar


class ScholarDAO(BaseDAO[DwdScholar]):
    """专家/人才数据查询封装。"""

    model = DwdScholar

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session=session)

    def get_by_id(self, scholar_pk: int) -> DwdScholar | None:
        return self.get(scholar_pk)

    def get_by_scholar_id(self, scholar_id: str) -> DwdScholar | None:
        statement = select(DwdScholar).where(DwdScholar.scholar_id == scholar_id)
        return self.first_by_statement(statement)

    def search_by_name(
        self,
        keyword: str,
        *,
        offset: int = 0,
        limit: int = 20,
        only_active: bool = True,
    ) -> list[DwdScholar]:
        keyword = keyword.strip()
        if not keyword:
            return []

        like_keyword = f"%{keyword}%"
        statement = (
            select(DwdScholar)
            .where(
                or_(DwdScholar.name_zh.like(like_keyword), DwdScholar.name_en.like(like_keyword))
            )
            .offset(offset)
            .limit(limit)
        )
        if only_active:
            statement = statement.where(DwdScholar.status == 1)
        return self.list_by_statement(statement)

    def list_direct_coauthor_relations(
        self,
        *,
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        session, should_close = self._get_session()
        try:
            normalized_limit = max(1, min(int(limit or 20), 100))
            params = {
                "expert_a": (expert_a_id or "").strip(),
                "expert_b": (expert_b_id or "").strip(),
                "institution": (institution or "").strip(),
                "start_time": (start_time or "").strip(),
                "end_time": (end_time or "").strip(),
                "limit": normalized_limit,
            }
            params.update(
                {
                    "expert_a_like": f"%{params['expert_a']}%",
                    "expert_b_like": f"%{params['expert_b']}%",
                    "institution_like": f"%{params['institution']}%",
                }
            )

            stmt = text(
                """
                WITH matched_relations AS (
                    SELECT
                        c.scholar_id,
                        c.co_scholar_id,
                        c.co_scholar_name_zh,
                        c.co_scholar_name_en,
                        c.co_scholar_org_name_zh,
                        c.co_scholar_org_name_en,
                        c.co_paper_count,
                        c.create_time,
                        c.update_time,
                        s.name_zh AS scholar_name_zh,
                        s.name_en AS scholar_name_en,
                        s.scholar_org_name_zh AS scholar_org_name_zh,
                        s.scholar_org_name_en AS scholar_org_name_en,
                        s.h_index AS scholar_h_index,
                        s.paper_nums AS scholar_paper_nums,
                        s.citation_nums AS scholar_citation_nums,
                        cs.name_zh AS co_name_zh,
                        cs.name_en AS co_name_en,
                        cs.scholar_org_name_zh AS co_org_name_zh,
                        cs.scholar_org_name_en AS co_org_name_en,
                        cs.h_index AS co_h_index,
                        cs.paper_nums AS co_paper_nums,
                        cs.citation_nums AS co_citation_nums,
                        CASE
                            WHEN :expert_a != ''
                                AND :expert_b = ''
                                AND (
                                    c.co_scholar_id = :expert_a
                                    OR COALESCE(cs.name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(cs.name_en, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_a_like
                                )
                                AND NOT (
                                    c.scholar_id = :expert_a
                                    OR COALESCE(s.name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(s.name_en, '') LIKE :expert_a_like
                                )
                            THEN 1
                            ELSE 0
                        END AS reverse_relation
                    FROM dwd_scholar_coauthor c
                    LEFT JOIN dwd_scholar s
                        ON s.scholar_id = c.scholar_id
                        AND COALESCE(s.status, 1) = 1
                    LEFT JOIN dwd_scholar cs
                        ON cs.scholar_id = c.co_scholar_id
                        AND COALESCE(cs.status, 1) = 1
                    WHERE COALESCE(c.status, 1) = 1
                        AND (
                            (
                                :expert_a = ''
                                AND :expert_b = ''
                            )
                            OR (
                                :expert_a != ''
                                AND :expert_b = ''
                                AND (
                                    c.scholar_id = :expert_a
                                    OR COALESCE(s.name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(s.name_en, '') LIKE :expert_a_like
                                    OR c.co_scholar_id = :expert_a
                                    OR COALESCE(cs.name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(cs.name_en, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_a_like
                                )
                            )
                            OR (
                                :expert_a != ''
                                AND :expert_b != ''
                                AND (
                                    (
                                        c.scholar_id = :expert_a
                                        OR COALESCE(s.name_zh, '') LIKE :expert_a_like
                                        OR COALESCE(s.name_en, '') LIKE :expert_a_like
                                    )
                                    AND (
                                        c.co_scholar_id = :expert_b
                                        OR COALESCE(cs.name_zh, '') LIKE :expert_b_like
                                        OR COALESCE(cs.name_en, '') LIKE :expert_b_like
                                        OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_b_like
                                        OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_b_like
                                    )
                                )
                                OR (
                                    (
                                        c.scholar_id = :expert_b
                                        OR COALESCE(s.name_zh, '') LIKE :expert_b_like
                                        OR COALESCE(s.name_en, '') LIKE :expert_b_like
                                    )
                                    AND (
                                        c.co_scholar_id = :expert_a
                                        OR COALESCE(cs.name_zh, '') LIKE :expert_a_like
                                        OR COALESCE(cs.name_en, '') LIKE :expert_a_like
                                        OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_a_like
                                        OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_a_like
                                    )
                                )
                            )
                        )
                        AND (
                            :expert_b = ''
                            OR :expert_a != ''
                            OR c.co_scholar_id = :expert_b
                            OR COALESCE(cs.name_zh, '') LIKE :expert_b_like
                            OR COALESCE(cs.name_en, '') LIKE :expert_b_like
                            OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_b_like
                            OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_b_like
                        )
                        AND (
                            :institution = ''
                            OR COALESCE(s.scholar_org_name_zh, '') LIKE :institution_like
                            OR COALESCE(s.scholar_org_name_en, '') LIKE :institution_like
                            OR COALESCE(cs.scholar_org_name_zh, '') LIKE :institution_like
                            OR COALESCE(cs.scholar_org_name_en, '') LIKE :institution_like
                            OR COALESCE(c.co_scholar_org_name_zh, '') LIKE :institution_like
                            OR COALESCE(c.co_scholar_org_name_en, '') LIKE :institution_like
                        )
                        AND (
                            :start_time = ''
                            OR COALESCE(c.update_time, c.create_time) >= STR_TO_DATE(:start_time, '%Y-%m-%d')
                        )
                        AND (
                            :end_time = ''
                            OR COALESCE(c.update_time, c.create_time) < DATE_ADD(STR_TO_DATE(:end_time, '%Y-%m-%d'), INTERVAL 1 DAY)
                        )
                )
                SELECT
                    CASE
                        WHEN reverse_relation = 1
                        THEN CONCAT('direct:', co_scholar_id, ':', scholar_id)
                        ELSE CONCAT('direct:', scholar_id, ':', co_scholar_id)
                    END AS relation_key,
                    CASE WHEN reverse_relation = 1 THEN co_scholar_id ELSE scholar_id END AS expert_a_id,
                    CASE
                        WHEN reverse_relation = 1
                        THEN COALESCE(NULLIF(co_name_zh, ''), NULLIF(co_name_en, ''), NULLIF(co_scholar_name_zh, ''), NULLIF(co_scholar_name_en, ''), co_scholar_id)
                        ELSE COALESCE(NULLIF(scholar_name_zh, ''), NULLIF(scholar_name_en, ''), scholar_id)
                    END AS expert_a_name,
                    CASE
                        WHEN reverse_relation = 1
                        THEN COALESCE(NULLIF(co_org_name_zh, ''), NULLIF(co_org_name_en, ''), NULLIF(co_scholar_org_name_zh, ''), NULLIF(co_scholar_org_name_en, ''))
                        ELSE COALESCE(NULLIF(scholar_org_name_zh, ''), NULLIF(scholar_org_name_en, ''))
                    END AS expert_a_org,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(co_h_index, 0) ELSE COALESCE(scholar_h_index, 0) END AS expert_a_h_index,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(co_paper_nums, 0) ELSE COALESCE(scholar_paper_nums, 0) END AS expert_a_paper_nums,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(co_citation_nums, 0) ELSE COALESCE(scholar_citation_nums, 0) END AS expert_a_citation_nums,
                    CASE WHEN reverse_relation = 1 THEN scholar_id ELSE co_scholar_id END AS expert_b_id,
                    CASE
                        WHEN reverse_relation = 1
                        THEN COALESCE(NULLIF(scholar_name_zh, ''), NULLIF(scholar_name_en, ''), scholar_id)
                        ELSE COALESCE(NULLIF(co_name_zh, ''), NULLIF(co_name_en, ''), NULLIF(co_scholar_name_zh, ''), NULLIF(co_scholar_name_en, ''), co_scholar_id)
                    END AS expert_b_name,
                    CASE
                        WHEN reverse_relation = 1
                        THEN COALESCE(NULLIF(scholar_org_name_zh, ''), NULLIF(scholar_org_name_en, ''))
                        ELSE COALESCE(NULLIF(co_org_name_zh, ''), NULLIF(co_org_name_en, ''), NULLIF(co_scholar_org_name_zh, ''), NULLIF(co_scholar_org_name_en, ''))
                    END AS expert_b_org,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(scholar_h_index, 0) ELSE COALESCE(co_h_index, 0) END AS expert_b_h_index,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(scholar_paper_nums, 0) ELSE COALESCE(co_paper_nums, 0) END AS expert_b_paper_nums,
                    CASE WHEN reverse_relation = 1 THEN COALESCE(scholar_citation_nums, 0) ELSE COALESCE(co_citation_nums, 0) END AS expert_b_citation_nums,
                    COALESCE(co_paper_count, 0) AS co_paper_count,
                    COALESCE(update_time, create_time) AS relation_time
                FROM matched_relations
                ORDER BY COALESCE(co_paper_count, 0) DESC, COALESCE(update_time, create_time) DESC
                LIMIT :limit
                """
            )
            return [dict(row) for row in session.execute(stmt, params).mappings().all()]
        finally:
            if should_close:
                session.close()

    def list_direct_patent_relations(
        self,
        *,
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        session, should_close = self._get_session()
        try:
            normalized_limit = max(1, min(int(limit or 20), 100))
            candidate_limit = max(50, min(normalized_limit * 20, 500))
            stmt = select(OdsPatent).limit(candidate_limit)
            rows = list(session.scalars(stmt).all())
            return self._build_pair_relations(
                session=session,
                rows=rows,
                expert_a_id=expert_a_id,
                expert_b_id=expert_b_id,
                institution=institution,
                start_time=start_time,
                end_time=end_time,
                limit=normalized_limit,
                row_kind="patent",
            )
        finally:
            if should_close:
                session.close()

    def list_direct_project_relations(
        self,
        *,
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        session, should_close = self._get_session()
        try:
            normalized_limit = max(1, min(int(limit or 20), 100))
            candidate_limit = max(50, min(normalized_limit * 20, 500))
            rows = list(session.scalars(select(OdsZhProject).limit(candidate_limit)).all())
            rows.extend(
                list(session.scalars(select(OdsEnProject).limit(candidate_limit)).all())
            )
            return self._build_pair_relations(
                session=session,
                rows=rows,
                expert_a_id=expert_a_id,
                expert_b_id=expert_b_id,
                institution=institution,
                start_time=start_time,
                end_time=end_time,
                limit=normalized_limit,
                row_kind="project",
            )
        finally:
            if should_close:
                session.close()

    def _build_pair_relations(
        self,
        *,
        session: Session,
        rows: Iterable[object],
        expert_a_id: str | None,
        expert_b_id: str | None,
        institution: str | None,
        start_time: str | None,
        end_time: str | None,
        limit: int,
        row_kind: str,
    ) -> list[dict[str, object]]:
        exact_name_map = self._load_exact_name_map(session)
        institution_keyword = (institution or "").strip().lower()
        expert_a_keyword = (expert_a_id or "").strip()
        expert_b_keyword = (expert_b_id or "").strip()

        pair_bucket: dict[tuple[str, str, str], dict[str, object]] = {}

        for row in rows:
            payload = self._extract_relation_payload(row, row_kind=row_kind)
            if payload is None:
                continue
            if (
                institution_keyword
                and institution_keyword not in payload["institution_text"].lower()
            ):
                continue
            if not self._within_time_range(payload["relation_time"], start_time, end_time):
                continue

            mapped = self._map_people_to_scholars(payload["people"], exact_name_map)
            unique_people = {item["scholar_id"]: item for item in mapped}.values()
            mapped_people = list(unique_people)
            if len(mapped_people) < 2:
                continue

            for left, right in combinations(mapped_people, 2):
                if not self._match_pair_filters(
                    left=left,
                    right=right,
                    expert_a_keyword=expert_a_keyword,
                    expert_b_keyword=expert_b_keyword,
                ):
                    continue

                ordered_left, ordered_right = self._order_pair(
                    left=left,
                    right=right,
                    expert_a_keyword=expert_a_keyword,
                )
                pair_key = (ordered_left["scholar_id"], ordered_right["scholar_id"], row_kind)
                bucket = pair_bucket.setdefault(
                    pair_key,
                    self._init_pair_bucket(
                        left=ordered_left,
                        right=ordered_right,
                        relation_time=payload["relation_time"],
                        institution=payload["institution"],
                        row_kind=row_kind,
                    ),
                )
                bucket["evidence_count"] = int(bucket["evidence_count"]) + 1
                bucket["evidence_titles"].append(payload["title"])
                if payload["relation_time"] and (
                    bucket["relation_time"] is None
                    or payload["relation_time"] > bucket["relation_time"]
                ):
                    bucket["relation_time"] = payload["relation_time"]
                if not bucket["institution"] and payload["institution"]:
                    bucket["institution"] = payload["institution"]

        results = list(pair_bucket.values())
        results.sort(
            key=lambda item: (
                int(item.get("evidence_count") or 0),
                item.get("relation_time") or "",
            ),
            reverse=True,
        )
        return results[:limit]

    def _load_exact_name_map(self, session: Session) -> dict[str, list[DwdScholar]]:
        scholars = list(
            session.scalars(select(DwdScholar).where(DwdScholar.status == 1)).all()
        )
        mapping: dict[str, list[DwdScholar]] = defaultdict(list)
        for scholar in scholars:
            for name in (scholar.name_zh, scholar.name_en):
                normalized = self._normalize_person_name(name)
                if normalized:
                    mapping[normalized].append(scholar)
        return mapping

    def _extract_relation_payload(
        self, row: object, *, row_kind: str
    ) -> dict[str, object] | None:
        if row_kind == "patent":
            inventors = self._extract_people_tokens(
                getattr(row, "current_inventor", None)
                or getattr(row, "inventor", None)
                or getattr(row, "dwpi_inventor", None)
                or ""
            )
            relation_time = getattr(row, "filing_date", None) or getattr(
                row, "publication_date", None
            )
            institution = self._first_non_empty(
                getattr(row, "assignee", None),
                getattr(row, "current_assignee", None),
                getattr(row, "dwpi_assignee", None),
            )
            title = self._first_non_empty(
                getattr(row, "title_localized", None), getattr(row, "id", None)
            )
            return {
                "people": inventors,
                "relation_time": relation_time,
                "institution": institution,
                "institution_text": institution or "",
                "title": title or "",
            }

        participants = self._extract_people_tokens(
            self._join_non_empty(
                getattr(row, "project_host", None),
                getattr(row, "participants", None),
            )
        )
        institution = self._first_non_empty(
            getattr(row, "funded_institution", None),
            getattr(row, "participating_institution", None),
        )
        relation_time = getattr(row, "approval_time", None) or getattr(
            row, "approval_year", None
        )
        title = self._first_non_empty(
            getattr(row, "title", None), getattr(row, "project_number", None)
        )
        return {
            "people": participants,
            "relation_time": relation_time,
            "institution": institution,
            "institution_text": self._join_non_empty(
                getattr(row, "funded_institution", None),
                getattr(row, "participating_institution", None),
            ),
            "title": title or "",
        }

    def _map_people_to_scholars(
        self,
        people: Iterable[str],
        exact_name_map: dict[str, list[DwdScholar]],
    ) -> list[dict[str, object]]:
        mapped: list[dict[str, object]] = []
        for person in people:
            normalized = self._normalize_person_name(person)
            if not normalized:
                continue
            candidates = exact_name_map.get(normalized, [])
            if len(candidates) != 1:
                continue
            scholar = candidates[0]
            mapped.append(
                {
                    "scholar_id": scholar.scholar_id,
                    "name": scholar.name_zh or scholar.name_en or scholar.scholar_id,
                    "organization": (
                        scholar.scholar_org_name_zh or scholar.scholar_org_name_en or ""
                    ),
                    "h_index": scholar.h_index or 0,
                    "paper_nums": scholar.paper_nums or 0,
                    "citation_nums": scholar.citation_nums or 0,
                }
            )
        return mapped

    def _match_pair_filters(
        self,
        *,
        left: dict[str, object],
        right: dict[str, object],
        expert_a_keyword: str,
        expert_b_keyword: str,
    ) -> bool:
        if expert_a_keyword and not (
            self._match_person_keyword(left, expert_a_keyword)
            or self._match_person_keyword(right, expert_a_keyword)
        ):
            return False
        if expert_b_keyword and not (
            self._match_person_keyword(left, expert_b_keyword)
            or self._match_person_keyword(right, expert_b_keyword)
        ):
            return False
        if expert_a_keyword and expert_b_keyword:
            return (
                self._match_person_keyword(left, expert_a_keyword)
                and self._match_person_keyword(right, expert_b_keyword)
            ) or (
                self._match_person_keyword(left, expert_b_keyword)
                and self._match_person_keyword(right, expert_a_keyword)
            )
        return True

    def _order_pair(
        self,
        *,
        left: dict[str, object],
        right: dict[str, object],
        expert_a_keyword: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if expert_a_keyword and self._match_person_keyword(right, expert_a_keyword):
            return right, left
        return left, right

    def _init_pair_bucket(
        self,
        *,
        left: dict[str, object],
        right: dict[str, object],
        relation_time: object,
        institution: str | None,
        row_kind: str,
    ) -> dict[str, object]:
        return {
            "relation_key": f"direct:{row_kind}:{left['scholar_id']}:{right['scholar_id']}",
            "expert_a_id": left["scholar_id"],
            "expert_a_name": left["name"],
            "expert_a_org": left["organization"],
            "expert_a_h_index": left["h_index"],
            "expert_a_paper_nums": left["paper_nums"],
            "expert_a_citation_nums": left["citation_nums"],
            "expert_b_id": right["scholar_id"],
            "expert_b_name": right["name"],
            "expert_b_org": right["organization"],
            "expert_b_h_index": right["h_index"],
            "expert_b_paper_nums": right["paper_nums"],
            "expert_b_citation_nums": right["citation_nums"],
            "evidence_kind": row_kind,
            "evidence_count": 0,
            "evidence_titles": [],
            "relation_time": relation_time,
            "institution": institution or "",
        }

    def _match_person_keyword(self, person: dict[str, object], keyword: str) -> bool:
        normalized = keyword.strip().lower()
        return normalized in {
            str(person.get("scholar_id") or "").strip().lower(),
            str(person.get("name") or "").strip().lower(),
        }

    def _within_time_range(
        self,
        relation_time: object,
        start_time: str | None,
        end_time: str | None,
    ) -> bool:
        if relation_time is None:
            return not start_time and not end_time
        relation_date = str(relation_time)[:10]
        if start_time and relation_date < start_time:
            return False
        if end_time and relation_date > end_time:
            return False
        return True

    def _extract_people_tokens(self, raw: str) -> list[str]:
        if not raw:
            return []
        text_value = str(raw).strip()
        if not text_value:
            return []
        parsed = self._parse_json_people(text_value)
        if parsed:
            return parsed
        parts = re.split(r"[;,/|、，；\n\r\t]+", text_value)
        return [part.strip() for part in parts if part.strip()]

    def _parse_json_people(self, raw: str) -> list[str]:
        try:
            payload = json.loads(raw)
        except Exception:
            return []
        names: list[str] = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    for key in ("name", "name_zh", "name_en", "inventor", "person"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            names.append(value.strip())
                            break
        return names

    def _normalize_person_name(self, value: str | None) -> str:
        if value is None:
            return ""
        return str(value).strip().strip('"').strip("'")

    def _join_non_empty(self, *parts: object) -> str:
        values = [str(part).strip() for part in parts if str(part or "").strip()]
        return " / ".join(values)

    def _first_non_empty(self, *parts: object) -> str | None:
        for part in parts:
            value = str(part or "").strip()
            if value:
                return value
        return None
