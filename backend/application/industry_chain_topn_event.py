from service.industry_chain_topn_event import IndustryChainTopNEventService


class IndustryChainTopNEventApplication:
    def __init__(self) -> None:
        self._service = IndustryChainTopNEventService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
