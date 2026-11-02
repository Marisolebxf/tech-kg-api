"""Fail-closed destination policy for user-configured MySQL data sources."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket

_POLICY_ENV = "MYSQL_DATASOURCE_ALLOWED_ENDPOINTS"
_DENIED = "数据源连接目标未获准"


class MysqlDatasourceTargetError(ValueError):
    """A configured or resolved destination is not explicitly permitted."""

    def __init__(self) -> None:
        super().__init__(_DENIED)


def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    # Scoped IPv6 and mapped IPv4 must not bypass either address-family policy.
    if "%" in value:
        raise MysqlDatasourceTargetError()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise MysqlDatasourceTargetError() from None
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None)
    ):
        raise MysqlDatasourceTargetError()
    return address


def _allowed_endpoints() -> set[tuple[str, int]]:
    try:
        entries = json.loads(os.getenv(_POLICY_ENV, "[]"))
    except (TypeError, ValueError):
        raise MysqlDatasourceTargetError() from None
    if not isinstance(entries, list):
        raise MysqlDatasourceTargetError()
    allowed: set[tuple[str, int]] = set()
    for entry in entries:
        if not isinstance(entry, str):
            raise MysqlDatasourceTargetError()
        match = re.fullmatch(r"(?:\[([^\[\]]+)\]|([^:\[\]]+)):([0-9]+)", entry)
        if match is None:
            raise MysqlDatasourceTargetError()
        address = _address(match[1] or match[2])
        if (match[1] is not None) != isinstance(address, ipaddress.IPv6Address):
            raise MysqlDatasourceTargetError()
        if len(match[3]) > 5:
            raise MysqlDatasourceTargetError()
        port = int(match[3])
        if not 1 <= port <= 65535:
            raise MysqlDatasourceTargetError()
        allowed.add((str(address), port))
    return allowed


def resolve_mysql_datasource_target(host: str, port: int) -> str:
    """Resolve once, require *every* answer to be allowed, and return a pinned IP.

    Only the admin-provided numeric endpoint list grants access, including for
    private networks. This policy deliberately does not affect infra.mysql's
    environment-configured platform/control-plane connections.
    """
    allowed = _allowed_endpoints()
    if (
        not allowed
        or not isinstance(host, str)
        or not host
        or host != host.strip()
        or any(character.isspace() for character in host)
        or any(character in host for character in ("%", "/", "\\", "@"))
        or not isinstance(port, int)
        or isinstance(port, bool)
        or not 1 <= port <= 65535
    ):
        raise MysqlDatasourceTargetError()
    # Accept bracketed numeric IPv6 from connection settings, never a URL/port.
    if host.startswith("[") and host.endswith("]"):
        host = str(_address(host[1:-1]))
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        pass  # Host names are checked against every resolved address below.
    else:
        _address(str(literal))
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError, ValueError):
        raise MysqlDatasourceTargetError() from None
    if not answers:
        raise MysqlDatasourceTargetError()
    resolved: list[str] = []
    for family, _kind, _protocol, _canonical, sockaddr in answers:
        if family not in (socket.AF_INET, socket.AF_INET6) or sockaddr[1] != port:
            raise MysqlDatasourceTargetError()
        address = _address(sockaddr[0])
        if (str(address), port) not in allowed:
            raise MysqlDatasourceTargetError()
        resolved.append(str(address))
    return resolved[0]
