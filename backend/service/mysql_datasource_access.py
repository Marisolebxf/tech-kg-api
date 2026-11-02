"""Keep use of shared MySQL credentials within their reviewed database scope."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db_model.mysql_datasource import MysqlDatasource
from service.config_ownership import ensure_config_access
from service.platform_access import PlatformActor


def ensure_mysql_database_access(
    session: Session,
    actor: PlatformActor,
    datasource_id: str,
    requested_database: str | None,
) -> str:
    """Authorize the configuration and the effective database, not just its ID.

    An omitted override uses the configured default. Empty legacy defaults do
    not authorize developers to enumerate or select arbitrary databases.
    """
    ensure_config_access(session, actor, "mysql", datasource_id)
    row = session.get(MysqlDatasource, datasource_id)
    if row is None:
        raise HTTPException(403, "数据源数据库不存在或不可访问")
    default = row.default_database or ""
    database = requested_database if requested_database not in (None, "") else default
    if not actor.is_admin and (
        not default.strip() or not isinstance(database, str) or database != default
    ):
        raise HTTPException(403, "无权访问数据源授权数据库以外的数据库")
    return database
