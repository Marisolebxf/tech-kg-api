"""nGQL 控制台 service：语句分类 + 受控执行。

策略（务实关键字法，非 SQL 解析器）：
- 拒绝多语句（分号分隔的多条）、管道、USE（图空间由 scoped client 强制）；
- 首 token 白名单分类为 读 / 写；
- DDL 与管理类语句对所有人（含管理员）一律拒绝；
- 写语句仅平台管理员可执行。
"""

from __future__ import annotations

import re

from service.platform_access import PlatformActor

# 首 token 白名单
READ_TOKENS = frozenset(
    {
        "MATCH",
        "LOOKUP",
        "GO",
        "SHOW",
        "DESCRIBE",
        "DESC",
        "EXPLAIN",
        "FIND",
        "FETCH",
        "GET",
        "UNWIND",
        "RETURN",
        "ORDER",
        "WITH",
        "COUNT",
        "YIELD",
    }
)
WRITE_TOKENS = frozenset({"INSERT", "DELETE", "UPDATE", "UPSERT"})
# DDL / 集群管理：任何人都不能通过控制台执行
DDL_TOKENS = frozenset(
    {
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "REBUILD",
        "SUBMIT",
        "ADMIN",
        "DOWNLOAD",
        "INGEST",
        "KILL",
        "SIGNOUT",
        "ZONE",
        "BALANCE",
        "HOST",
        "MACHINE",
        "LIST",
        "USE",
    }
)

_MAX_STATEMENT_CHARS = 4000

_comment_pattern = re.compile(r"(--|//)[^\n]*")


class GraphConsoleError(Exception):
    """语句被拒绝或执行失败（message 直接作为 API detail）。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def classify_statement(statement: str) -> str:
    """返回 'read' | 'write'；非法/被拒语句抛 GraphConsoleError。"""
    statement = (statement or "").strip()
    if not statement:
        raise GraphConsoleError("nGQL 语句不能为空")
    if len(statement) > _MAX_STATEMENT_CHARS:
        raise GraphConsoleError("nGQL 语句过长（上限 4000 字符）")

    stripped = _comment_pattern.sub("", statement).strip()
    if not stripped:
        raise GraphConsoleError("nGQL 语句不能只包含注释")

    # 去掉尾部空白与结尾分号后再判断多语句
    body = stripped.rstrip(";").strip()
    if not body:
        raise GraphConsoleError("nGQL 语句不能为空")
    if ";" in body:
        raise GraphConsoleError("一次仅允许执行一条语句")
    if "|" in body:
        raise GraphConsoleError("不允许使用管道")

    token_match = re.match(r"[A-Za-z_]+", body)
    first_token = (token_match.group(0) if token_match else "").upper()
    if first_token in DDL_TOKENS:
        raise GraphConsoleError(
            f"禁止执行 DDL/管理类语句（{first_token}）；图空间与 Schema 请通过配置页 / Schema 管理维护",
            status_code=403,
        )
    if first_token in WRITE_TOKENS:
        return "write"
    if first_token in READ_TOKENS:
        return "read"
    raise GraphConsoleError(
        f"不支持的语句开头 “{first_token}”；允许的只读语句："
        "MATCH / LOOKUP / GO / SHOW / DESCRIBE / FIND / FETCH / GET / UNWIND 等，"
        "管理员另可执行 INSERT / UPDATE / DELETE / UPSERT"
    )


def run_statement(actor: PlatformActor, space: str, statement: str) -> dict:
    """按分类执行语句并返回 {records, columns, summary}。

    空间必须存在于图服务；普通用户还需已绑定该空间。
    """
    from service.graph_space import SPACE_NAME_PATTERN, GraphSpaceError, GraphSpaceService

    if not SPACE_NAME_PATTERN.fullmatch(space or ""):
        raise GraphConsoleError("图空间名称不合法")
    kind = classify_statement(statement)
    if kind == "write" and not actor.is_admin:
        raise GraphConsoleError("仅平台管理员可以执行写语句", status_code=403)

    import logging

    from infra.graph_db import get_space_client
    from infra.graph_db.exceptions import GraphRepoError

    logger = logging.getLogger(__name__)

    # 空间存在性与归属校验（绑定关系在 MySQL）
    try:
        from infra.mysql import create_session

        session = create_session()
        try:
            space_service = GraphSpaceService(session)
            spaces = space_service.client.list_spaces()
        finally:
            session.close()
    except GraphSpaceError as exc:
        raise GraphConsoleError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("nGQL 控制台列空间失败: %s", exc)
        raise GraphConsoleError(f"图服务不可用: {exc}") from exc
    if space not in spaces:
        raise GraphConsoleError(f"图空间 {space} 不存在")
    if not actor.is_admin and not space_service.is_bound(actor.user_id, space):
        raise GraphConsoleError("无权访问未绑定的图空间", status_code=403)

    try:
        client = get_space_client(space)
        if kind == "write":
            result = client.execute_write(statement)
        else:
            result = client.execute_read(statement)
    except GraphRepoError as exc:
        raise GraphConsoleError(f"语句执行失败: {exc}") from exc

    records = [dict(record) for record in (result.records or [])]
    columns: list[str] = []
    if records:
        columns = list(records[0].keys())
    summary = getattr(result, "summary", None) or {}
    if not isinstance(summary, dict):
        summary = {"summary": str(summary)}
    return {"records": records, "columns": columns, "summary": summary, "kind": kind}
