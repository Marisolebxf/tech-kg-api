"""门户开发人员身份校验；业务归属仍由本地成员表控制。"""

import threading
import time
from functools import lru_cache

from fastapi import HTTPException

from config.auth import AuthSettings
from infra.user_center import UserCenterClient, UserCenterError


class PortalDeveloperDirectory:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self.client = UserCenterClient(settings)
        self._lock = threading.Lock()
        self._expires_at = 0.0
        self._user_ids: frozenset[str] = frozenset()

    def contains(self, user_id: str) -> bool:
        # API 和 worker 都查询同一后端接口；不信任任务 payload 里的角色。
        with self._lock:
            if time.monotonic() >= self._expires_at:
                started = time.monotonic()
                users: set[str] = set()
                for code in self.settings.portal_developer_role_codes:
                    users.update(self.client.role_user_ids(code))
                self._user_ids = frozenset(users)
                self._expires_at = started + min(60, self.settings.portal_role_cache_ttl_seconds)
            return user_id in self._user_ids


@lru_cache(maxsize=16)
def _directory(settings: AuthSettings) -> PortalDeveloperDirectory:
    return PortalDeveloperDirectory(settings)


def portal_allows_development(user_id: str) -> bool:
    settings = AuthSettings.from_env()
    # 默认保持现有本地业务授权；仅在明确配置门户角色编码的环境开启双重校验。
    if not settings.enabled or not settings.portal_developer_role_codes:
        return True
    try:
        return _directory(settings).contains(user_id)
    except UserCenterError as exc:
        # 查询失败不沿用过期身份，不把未确认的结果当作管理员/开发人员。
        raise HTTPException(503, "门户开发人员身份暂时无法核验，请稍后重试") from exc
