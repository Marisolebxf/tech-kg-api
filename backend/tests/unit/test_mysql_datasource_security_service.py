"""Service-side policy applies to probes, enumeration, CRUD and background use."""

import socket
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from service import mysql_datasource as module
from service import mysql_datasource_target as target


def _row(**changes):
    values = dict(
        id="MYSQL-1",
        name="source",
        description="",
        host="mysql.internal",
        port=3306,
        default_database="business",
        username="reader",
        password="hidden-password-tail",
        owner="admin",
        is_default=False,
        status="正常",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return SimpleNamespace(**{**values, **changes})


@pytest.fixture
def service():
    instance = module.MysqlDatasourceService(None)
    instance._dao = Mock()
    instance._dao.get.return_value = _row()
    instance._dao.update.side_effect = lambda cid, **kw: _row(**kw)
    instance._dao.create.side_effect = lambda **kw: _row(**kw)
    return instance


@pytest.fixture
def allowed(monkeypatch):
    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["10.20.30.40:3306"]')
    dns = Mock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.20.30.40", 3306))
        ]
    )
    monkeypatch.setattr(target.socket, "getaddrinfo", dns)
    return dns


@pytest.fixture(autouse=True)
def no_live_connections(monkeypatch):
    monkeypatch.delenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", raising=False)
    monkeypatch.setattr(
        target.socket, "getaddrinfo", Mock(side_effect=AssertionError("Live DNS forbidden"))
    )
    monkeypatch.setattr(
        module, "MySQLClient", Mock(side_effect=AssertionError("Live TCP forbidden"))
    )


@pytest.mark.parametrize("password", ["a", "12345678", "a-very-long-secret-tail", "密码"])
def test_password_mask_never_discloses_length_or_suffix(password):
    assert module._mask_password(password) == "••••••••"
    assert module._mask_password("") == ""


def test_policy_denied_probe_does_not_connect_or_change_status(service):
    assert service.test_connection("MYSQL-1") == {
        "ok": False,
        "latencyMs": None,
        "error": "连接失败",
    }
    module.MySQLClient.assert_not_called()
    service._dao.update.assert_not_called()


@pytest.mark.parametrize("operation", ["list_databases", "list_tables", "list_columns"])
def test_policy_denied_enumeration_never_constructs_client(service, operation):
    args = ("MYSQL-1", "scholar") if operation == "list_columns" else ("MYSQL-1",)
    with pytest.raises(target.MysqlDatasourceTargetError):
        getattr(service, operation)(*args)
    module.MySQLClient.assert_not_called()
    service._dao.update.assert_not_called()


def test_new_or_changed_targets_validate_before_persistence(service):
    with pytest.raises(target.MysqlDatasourceTargetError):
        service.create_config({"name": "unsafe", "host": "mysql.internal", "username": "reader"})
    service._dao.create.assert_not_called()
    for change in ({"host": "other.internal"}, {"port": 3307}):
        with pytest.raises(target.MysqlDatasourceTargetError):
            service.update_config("MYSQL-1", change)
    service._dao.update.assert_not_called()


def test_unrelated_edit_does_not_require_grandfathering_saved_destination(service):
    service.update_config("MYSQL-1", {"name": "renamed"})
    assert service._dao.update.call_args.kwargs["name"] == "renamed"
    # The same stored destination is still denied when it is actually used.
    assert service.test_connection("MYSQL-1")["error"] == "连接失败"
    module.MySQLClient.assert_not_called()


def test_approved_create_and_target_update_retain_dns_name_for_future_revalidation(
    service, allowed
):
    created = service.create_config(
        {"name": "allowed", "host": "mysql.internal", "username": "reader"}
    )
    assert created["host"] == "mysql.internal"
    service.update_config("MYSQL-1", {"host": "new.internal"})
    assert service._dao.update.call_args.kwargs["host"] == "new.internal"
    assert allowed.call_count == 2


@pytest.mark.parametrize(
    "operation", ["test_connection", "list_databases", "list_tables", "list_columns"]
)
def test_network_errors_are_generic_dispose_client_and_pin_dns(
    service, allowed, monkeypatch, caplog, operation
):
    secret_error = "driver 2003 at internal-source-ip with database-user and secret-password"
    client = Mock()
    client.health_check.side_effect = RuntimeError(secret_error)
    client.engine.connect.side_effect = RuntimeError(secret_error)
    factory = Mock(return_value=client)
    monkeypatch.setattr(module, "MySQLClient", factory)
    args = ("MYSQL-1", "scholar") if operation == "list_columns" else ("MYSQL-1",)
    result = getattr(service, operation)(*args)
    assert factory.call_args.kwargs["host"] == "10.20.30.40"
    assert allowed.call_count == 1
    client.dispose.assert_called_once_with()
    assert secret_error not in repr(result) + caplog.text
    assert "internal-source-ip" not in repr(result) + caplog.text
    if operation == "test_connection":
        assert result["error"] == "连接失败"
        service._dao.update.assert_called_once_with("MYSQL-1", status="异常")
    else:
        assert result == []


def test_probe_success_false_result_and_constructor_failure(allowed, service, monkeypatch, caplog):
    client = Mock()
    client.health_check.return_value = True
    monkeypatch.setattr(module, "MySQLClient", Mock(return_value=client))
    assert service.test_connection("MYSQL-1")["ok"] is True
    client.dispose.assert_called_once_with()
    client.reset_mock()
    client.health_check.return_value = False
    assert service.test_connection("MYSQL-1")["error"] == "连接失败"
    client.dispose.assert_called_once_with()
    monkeypatch.setattr(
        module, "MySQLClient", Mock(side_effect=RuntimeError("secret constructor details"))
    )
    assert service.test_connection("MYSQL-1")["error"] == "连接失败"
    assert "secret constructor details" not in caplog.text


def test_probe_rechecks_dns_and_stops_rebinding_before_second_connection(
    service, allowed, monkeypatch
):
    allowed.side_effect = [
        allowed.return_value,
        [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 3306))],
    ]
    client = Mock()
    client.health_check.return_value = True
    factory = Mock(return_value=client)
    monkeypatch.setattr(module, "MySQLClient", factory)
    assert service.test_connection("MYSQL-1")["ok"] is True
    service._dao.update.reset_mock()
    assert service.test_connection("MYSQL-1")["error"] == "连接失败"
    assert factory.call_count == 1
    service._dao.update.assert_not_called()


def test_client_cleanup_error_does_not_expose_exception(service, allowed, monkeypatch, caplog):
    client = Mock()
    client.health_check.return_value = True
    client.dispose.side_effect = RuntimeError("secret cleanup network details")
    monkeypatch.setattr(module, "MySQLClient", Mock(return_value=client))
    result = service.test_connection("MYSQL-1")
    client.dispose.assert_called_once_with()
    assert "secret cleanup network details" not in repr(result) + caplog.text


@pytest.mark.parametrize("permit", [True, False])
def test_background_settings_revalidate_pin_ip_and_close_session(
    service, allowed, monkeypatch, permit
):
    if not permit:
        monkeypatch.delenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS")
    session = Mock()
    monkeypatch.setattr("infra.mysql.create_session", Mock(return_value=session))
    monkeypatch.setattr(module, "MysqlDatasourceDAO", Mock(return_value=service._dao))
    if permit:
        settings = module.get_mysql_settings_by_id("MYSQL-1")
        assert settings["host"] == "10.20.30.40"
        assert settings["port"] == 3306
    else:
        with pytest.raises(target.MysqlDatasourceTargetError):
            module.get_mysql_settings_by_id("MYSQL-1")
    session.close.assert_called_once_with()


def test_ipv6_pinning_builds_a_numeric_sqlalchemy_connection_host(service, monkeypatch):
    from sqlalchemy.engine import make_url

    from infra.mysql import MySQLClient

    monkeypatch.setenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", '["[2001:db8::1]:3306"]')
    monkeypatch.setattr(
        target.socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2001:db8::1", 3306, 0, 0),
            )
        ],
    )
    client = Mock()
    client.health_check.return_value = True
    factory = Mock(return_value=client)
    monkeypatch.setattr(module, "MySQLClient", factory)
    service.test_connection("MYSQL-1")
    assert factory.call_args.kwargs["host"] == "2001:db8::1"
    assert make_url(MySQLClient(**factory.call_args.kwargs).url).host == "2001:db8::1"


def test_target_policy_does_not_change_environment_configured_platform_client(monkeypatch):
    from infra.mysql import MySQLClient

    monkeypatch.delenv("MYSQL_DATASOURCE_ALLOWED_ENDPOINTS", raising=False)
    client = MySQLClient(host="127.0.0.1", port=3306)
    assert "127.0.0.1:3306" in client.url
