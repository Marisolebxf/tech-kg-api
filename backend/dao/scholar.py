from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from dao.base import BaseDAO
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
                            :expert_a = ''
                            OR c.scholar_id = :expert_a
                            OR COALESCE(s.name_zh, '') LIKE :expert_a_like
                            OR COALESCE(s.name_en, '') LIKE :expert_a_like
                            OR (
                                :expert_b = ''
                                AND (
                                    c.co_scholar_id = :expert_a
                                    OR COALESCE(cs.name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(cs.name_en, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_zh, '') LIKE :expert_a_like
                                    OR COALESCE(c.co_scholar_name_en, '') LIKE :expert_a_like
                                )
                            )
                        )
                        AND (
                            :expert_b = ''
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
