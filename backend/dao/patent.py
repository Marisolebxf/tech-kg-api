"""专利数据查询（MySQL）。"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.patent import DwdPatent


class PatentDAO:
    """dwd_patent 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_by_assignee(
        self, name_cn: str, cpc_prefixes: Sequence[str] | None = None
    ) -> list[DwdPatent]:
        stmt = select(DwdPatent).where(DwdPatent.first_current_assignee_name == name_cn)
        rows = list(self._s.execute(stmt).scalars())
        if cpc_prefixes:
            prefixes = [p.upper() for p in cpc_prefixes]
            rows = [
                p for p in rows
                if any(
                    any(c.upper().startswith(pre) for c in self._cpc_codes(p))
                    for pre in prefixes
                )
            ]
        return rows

    def count_by_cpc_section(self, name_cn: str) -> list[dict[str, object]]:
        rows = self.list_by_assignee(name_cn)
        counts: dict[str, int] = {}
        for p in rows:
            sections = {c[:1].upper() for c in self._cpc_codes(p) if c[:1]}
            for section in sections:
                counts[section] = counts.get(section, 0) + 1
        return [{"cpcSection": k, "count": v} for k, v in sorted(counts.items())]

    @staticmethod
    def _cpc_codes(patent: DwdPatent) -> list[str]:
        raw = patent.classification_cpc
        if not raw:
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return []
        codes: list[str] = []
        if isinstance(raw, dict):
            for v in raw.values():
                if isinstance(v, list):
                    codes.extend(str(x) for x in v)
                elif isinstance(v, str):
                    codes.append(v)
        elif isinstance(raw, list):
            codes.extend(str(x) for x in raw)
        return [c.strip() for c in codes if str(c).strip()]
