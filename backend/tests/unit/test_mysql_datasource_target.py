"""No live DNS or TCP: destination policy, DNS rebinding and address aliases."""

import json
import socket

import pytest

from service import mysql_datasource_target as target


def _answer(address: str, port: int = 3306):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


@pytest.fixture(autouse=True)
def no_real_dns(monkeypatch):
    monkeypatch.delenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", raising=False)

    def unexpected_dns(*args, **kwargs):
        raise AssertionError("Unexpected DNS lookup")

    monkeypatch.setattr(target.socket, "getaddrinfo", unexpected_dns)


@pytest.mark.parametrize(
    "policy",
    [
        None,
        "",
        "not-json",
        "null",
        "{}",
        "[]",
        "[1]",
        '["mysql.internal:3306"]',
        '["10.20.30.40/32:3306"]',
        '["10.20.30.40:*"]',
        '["10.20.30.40:0"]',
        '["10.20.30.40:65536"]',
        '["[10.20.30.40]:3306"]',
        '["2001:db8::1:3306"]',
        '["10.20.30.40:12345678901234567890"]',
    ],
)
def test_missing_empty_or_invalid_policy_denies_without_dns(monkeypatch, policy):
    if policy is not None:
        monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", policy)
    with pytest.raises(target.MysqlDatasourceTargetError, match="^数据源连接目标未获准$"):
        target.resolve_mysql_datasource_target("mysql.internal", 3306)


@pytest.mark.parametrize(
    "endpoint",
    [
        "127.0.0.1:3306",
        "169.254.169.254:3306",
        "0.0.0.0:3306",
        "224.0.0.1:3306",
        "[::1]:3306",
        "[fe80::1]:3306",
        "[::]:3306",
        "[ff02::1]:3306",
        "[::ffff:10.20.30.40]:3306",
        "[fe80::1%eth0]:3306",
    ],
)
def test_forbidden_address_cannot_be_allowed_by_configuration(monkeypatch, endpoint):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", json.dumps([endpoint]))
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("mysql.internal", 3306)


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "::1", "::ffff:10.20.30.40"])
def test_unsafe_literal_is_denied_before_resolution(monkeypatch, host):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target(host, 3306)


def test_allowed_private_endpoint_returns_numeric_ip_and_requires_exact_port(monkeypatch):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    calls = []

    def dns(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return [_answer("10.20.30.40", port)]

    monkeypatch.setattr(target.socket, "getaddrinfo", dns)
    assert target.resolve_mysql_datasource_target("mysql.internal", 3306) == "10.20.30.40"
    assert calls[0] == (
        "mysql.internal",
        3306,
        {"type": socket.SOCK_STREAM, "proto": socket.IPPROTO_TCP},
    )
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("mysql.internal", 3307)


@pytest.mark.parametrize(
    "other", ["10.20.30.41", "127.0.0.1", "169.254.169.254", "::ffff:10.20.30.40"]
)
@pytest.mark.parametrize("unsafe_first", [True, False])
def test_every_dns_answer_must_be_permitted(monkeypatch, other, unsafe_first):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    answers = [_answer("10.20.30.40"), _answer(other)]
    if unsafe_first:
        answers.reverse()
    monkeypatch.setattr(target.socket, "getaddrinfo", lambda *a, **kw: answers)
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("mysql.internal", 3306)


def test_ipv6_is_canonicalized_and_all_approved_answers_are_supported(monkeypatch):
    monkeypatch.setenv(
        "MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["[2001:db8::1]:3306", "10.20.30.40:3306"]'
    )
    monkeypatch.setattr(
        target.socket,
        "getaddrinfo",
        lambda *a, **kw: [
            _answer("2001:0db8:0000:0000:0000:0000:0000:0001"),
            _answer("10.20.30.40"),
        ],
    )
    assert target.resolve_mysql_datasource_target("mysql.internal", 3306) == "2001:db8::1"


def test_dns_and_policy_are_rechecked_instead_of_cached(monkeypatch):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    responses = iter([[_answer("10.20.30.40")], [_answer("127.0.0.1")]])
    monkeypatch.setattr(target.socket, "getaddrinfo", lambda *a, **kw: next(responses))
    assert target.resolve_mysql_datasource_target("rebind.internal", 3306) == "10.20.30.40"
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("rebind.internal", 3306)
    monkeypatch.delenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS")
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("rebind.internal", 3306)


@pytest.mark.parametrize("answers", [[], [_answer("10.20.30.40", 3307)]])
def test_empty_or_wrong_port_resolution_denies(monkeypatch, answers):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    monkeypatch.setattr(target.socket, "getaddrinfo", lambda *a, **kw: answers)
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target("mysql.internal", 3306)


def test_resolver_error_is_not_exposed(monkeypatch):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')

    def broken(*args, **kwargs):
        raise socket.gaierror("internal resolver and network details")

    monkeypatch.setattr(target.socket, "getaddrinfo", broken)
    with pytest.raises(target.MysqlDatasourceTargetError) as caught:
        target.resolve_mysql_datasource_target("mysql.internal", 3306)
    assert str(caught.value) == "数据源连接目标未获准"


@pytest.mark.parametrize(
    "host,port",
    [
        ("http://mysql.internal", 3306),
        ("a@b", 3306),
        ("mysql ", 3306),
        ("mysql", True),
        ("mysql", 0),
    ],
)
def test_invalid_connection_arguments_deny_without_dns(monkeypatch, host, port):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    with pytest.raises(target.MysqlDatasourceTargetError):
        target.resolve_mysql_datasource_target(host, port)
