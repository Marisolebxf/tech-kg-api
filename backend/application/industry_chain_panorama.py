from collections.abc import Mapping

from service.industry_chain_panorama import IndustryChainPanoramaService


class IndustryChainPanoramaApplication:
    def __init__(self) -> None:
        self._service = IndustryChainPanoramaService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    async def query(
        self,
        *,
        industry: str | None = None,
        anchor_id: str | None = None,
        depth: int = 2,
        top_k: int = 5,
        relation_types: list[str] | None = None,
        refresh: bool = False,
        auth_headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        return await self._service.query(
            industry=industry,
            anchor_id=anchor_id,
            depth=depth,
            top_k=top_k,
            relation_types=relation_types,
            refresh=refresh,
            auth_headers=auth_headers,
        )
