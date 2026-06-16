from service.industry_chain_panorama import IndustryChainPanoramaService


class IndustryChainPanoramaApplication:
    def __init__(self) -> None:
        self._service = IndustryChainPanoramaService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
