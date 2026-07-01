"""gkx_local 企业数据查询（只读）。

候选企业池取 gkx_local 中所有含 ``org_id``+``name_cn`` 列的 ``dwd_org_*`` 表的并集
（注册信息、上市公司、高管、股东、风险、财务、标签等共 31 张表，去重约 2.7 万家），
按 org_id 去重，最大覆盖学者可能关联的企业。结果进程级缓存，首次构建后复用。
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db_model.domestic_organization import DwdOrgRegInfo, DwdOrgStockBase

# 进程级候选缓存：org_id -> name_cn。首次 list_name_id() 构建后复用，避免每请求扫 31 张表。
_CANDIDATE_CACHE: dict[str, str] | None = None


def reset_candidate_cache() -> None:
    """测试用：清空候选缓存。"""
    global _CANDIDATE_CACHE
    _CANDIDATE_CACHE = None


class GkxOrganizationDAO:
    """gkx 企业查询封装（用于挖掘消歧靶库与企业建点）。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | DwdOrgStockBase | None:
        """取企业完整 ORM 对象：先查注册信息表，再查上市公司表。

        仅覆盖两张主表（含 province/listing_status 等完整字段）；仅出现在 detail 表
        的企业用 get_name_by_id 取名字建最小节点。
        """
        row = self._s.execute(
            select(DwdOrgRegInfo).where(DwdOrgRegInfo.org_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        return self._s.execute(
            select(DwdOrgStockBase).where(DwdOrgStockBase.org_id == org_id)
        ).scalar_one_or_none()

    def get_name_by_id(self, org_id: str) -> str | None:
        """从候选缓存取企业名（覆盖全 31 张表的并集）。"""
        cache = self._ensure_cache()
        return cache.get(org_id)

    def list_name_id(self) -> list[tuple[str, str]]:
        """返回 [(org_id, name_cn), ...]，全表并集去重，进程级缓存。"""
        cache = self._ensure_cache()
        return list(cache.items())

    def _ensure_cache(self) -> dict[str, str]:
        global _CANDIDATE_CACHE
        if _CANDIDATE_CACHE is not None:
            return _CANDIDATE_CACHE
        by_id: dict[str, str] = {}
        tabs = [r[0] for r in self._s.execute(text("SHOW TABLES")).all()]
        for t in tabs:
            try:
                cols = [c[0] for c in self._s.execute(text(f"SHOW COLUMNS FROM {t}")).all()]
            except Exception:  # noqa: BLE001
                continue
            if "org_id" not in cols or "name_cn" not in cols:
                continue
            rows = self._s.execute(
                text(f"SELECT DISTINCT org_id, name_cn FROM {t} WHERE org_id IS NOT NULL")
            ).all()
            for oid, name in rows:
                if oid and oid not in by_id and name:
                    by_id[oid] = name
        _CANDIDATE_CACHE = by_id
        return _CANDIDATE_CACHE
