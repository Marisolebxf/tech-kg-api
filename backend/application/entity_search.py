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

    def reindex(self, **kwargs) -> dict[str, Any]:
        return self._service.reindex(**kwargs)

    def search(self, **kwargs) -> dict[str, Any]:
        return self._service.search(**kwargs)

    def types(self, **kwargs) -> list[dict[str, Any]]:
        return self._service.types(**kwargs)

    def status(self, **kwargs) -> dict[str, Any]:
        return self._service.status(**kwargs)
