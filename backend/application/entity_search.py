"""实体检索应用编排层。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from service.entity_search import EntitySearchService


class EntitySearchApplication:
    def __init__(self, session: Session) -> None:
        self._service = EntitySearchService(session)

    def browse(self, **kwargs) -> dict[str, Any]:
        return self._service.browse(**kwargs)

    def preview_page(self, snapshot: dict[str, Any], **kwargs) -> dict[str, Any]:
        return self._service.preview_page(snapshot, **kwargs)

    def export_csv(self, **kwargs) -> str:
        return self._service.export_csv(**kwargs)

    def reindex(self, **kwargs) -> dict[str, Any]:
        return self._service.reindex(**kwargs)

    def search(self, **kwargs) -> dict[str, Any]:
        return self._service.search(**kwargs)

    def keyword_count(self, **kwargs) -> dict[str, Any]:
        return self._service.keyword_count(**kwargs)

    def keyword_search(self, **kwargs) -> dict[str, Any]:
        return self._service.keyword_search(**kwargs)

    def types(self, **kwargs) -> list[dict[str, Any]]:
        return self._service.types(**kwargs)

    def status(self, **kwargs) -> dict[str, Any]:
        return self._service.status(**kwargs)
