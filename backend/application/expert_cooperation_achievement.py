from service.expert_cooperation_achievement import ExpertCooperationAchievementService


class ExpertCooperationAchievementApplication:
    def __init__(self) -> None:
        self._service = ExpertCooperationAchievementService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def query(
        self,
        *,
        source_expert_id: str,
        target_expert_id: str,
        achievement_types: list[str] | None = None,
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        limit_per_type: int = 20,
    ) -> dict[str, object]:
        return self._service.query(
            source_expert_id=source_expert_id,
            target_expert_id=target_expert_id,
            achievement_types=achievement_types,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            limit_per_type=limit_per_type,
        )
