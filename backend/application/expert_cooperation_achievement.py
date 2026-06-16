from service.expert_cooperation_achievement import ExpertCooperationAchievementService


class ExpertCooperationAchievementApplication:
    def __init__(self) -> None:
        self._service = ExpertCooperationAchievementService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
