"""平台首页总览应用层。"""

from biz.schemas.platform_overview import PlatformOverviewData
from service.platform_overview import PlatformOverviewService


class PlatformOverviewApplication:
    def __init__(self, service: PlatformOverviewService | None = None) -> None:
        self.service = service or PlatformOverviewService()

    def get_overview(self) -> PlatformOverviewData:
        return self.service.get_overview()
