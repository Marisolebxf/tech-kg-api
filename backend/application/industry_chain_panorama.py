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
    ) -> dict[str, object]:
        return await self._service.query(
            industry=industry,
            anchor_id=anchor_id,
            depth=depth,
            top_k=top_k,
        )
