"""外部调用方认证和凭证生命周期，不复用图库服务密钥。"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from db_model.external_api_client import ExternalAPIClient
from infra.mysql import session_scope

PROJECT_RELATIONS_READ = "project-relations:read"
CLIENT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class ExternalClientError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ExternalClientIdentity:
    client_id: str


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def authenticate_client(client_id: str, api_key: str) -> ExternalClientIdentity:
    if not CLIENT_ID_PATTERN.fullmatch(client_id) or not 1 <= len(api_key) <= 256:
        raise ExternalClientError("调用凭证无效或已失效")
    try:
        with session_scope() as session:
            client = session.get(ExternalAPIClient, client_id)
            expected = client.api_key_hash if client else "0" * 64
            matches = hmac.compare_digest(hash_key(api_key), expected)
            if (
                not matches
                or client is None
                or not client.enabled
                or client.expires_at <= utc_now()
            ):
                raise ExternalClientError("调用凭证无效或已失效")
            if PROJECT_RELATIONS_READ not in (client.scopes or []):
                raise ExternalClientError("调用方无项目关系查询权限", 403)
            return ExternalClientIdentity(client_id=client.client_id)
    except SQLAlchemyError as exc:
        # 不将连接信息、SQL 参数或数据库异常回传调用方。
        raise ExternalClientError("调用方认证服务暂时不可用", 503) from exc


def issue_key(client_id: str, *, business_name: str | None, expires_days: int) -> str:
    """business_name=None 表示轮换；提交成功后才返回唯一一次明文。"""
    if not CLIENT_ID_PATTERN.fullmatch(client_id):
        raise ValueError("client_id 须为 1～64 位小写字母、数字、下划线或连字符，首位为字母或数字")
    if not 1 <= expires_days <= 3650:
        raise ValueError("有效天数须为 1～3650")
    if business_name is not None and not 1 <= len(business_name.strip()) <= 200:
        raise ValueError("业务方名称须为 1～200 字符")
    now = utc_now()
    key = "kg_" + secrets.token_urlsafe(32)
    with session_scope() as session:
        client = session.get(ExternalAPIClient, client_id, with_for_update=True)
        if business_name is not None:
            if client is not None:
                raise ValueError("client_id 已存在，请使用 rotate 更换密钥")
            client = ExternalAPIClient(
                client_id=client_id,
                business_name=business_name.strip(),
                enabled=True,
                scopes=[PROJECT_RELATIONS_READ],
                created_at=now,
            )
            session.add(client)
        elif client is None:
            raise ValueError("client_id 不存在")
        client.api_key_hash = hash_key(key)
        client.key_prefix = key[:12]
        client.expires_at = now + timedelta(days=expires_days)
        client.updated_at = now
    return key


def disable_client(client_id: str) -> None:
    with session_scope() as session:
        client = session.get(ExternalAPIClient, client_id, with_for_update=True)
        if client is None:
            raise ValueError("client_id 不存在")
        client.enabled = False
        client.updated_at = utc_now()
