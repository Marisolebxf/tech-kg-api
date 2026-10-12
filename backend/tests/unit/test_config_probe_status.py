"""测试连接的探活结果落库：失败→状态异常、成功→正常；停用态不覆盖（启停只由人工切换）。

此前三个配置服务的 test_connection 只返回结果不更新 status，前端徽标翻转只在内存里，
刷新后回跳库里旧值——表现为「连接测试失败但状态仍是正常」。
"""

from types import SimpleNamespace

import service.embedding_config as embedding_module
import service.llm_config as llm_module
import service.mysql_datasource as mysql_module
from service.embedding_config import EmbeddingConfigService
from service.llm_config import LlmConfigService
from service.mysql_datasource import MysqlDatasourceService


class StubDAO:
    """只实现 test_connection 路径用到的 get/update，记录 update 调用供断言。"""

    def __init__(self, row):
        self.row = row
        self.updates: list[dict] = []

    def get(self, config_id: str):
        return self.row if self.row.id == config_id else None

    def update(self, config_id: str, **values):
        self.updates.append({"id": config_id, **values})
        return self.row


def _row(status: str, **extra) -> SimpleNamespace:
    base = {
        "id": "CFG-1",
        "status": status,
        "host": "127.0.0.1",
        "port": 3306,
        "default_database": "test",
        "username": "root",
        "password": "x",
        "base_url": "https://llm.example/api",
        "model": "m",
        "api_key": "sk-x",
    }
    return SimpleNamespace(**{**base, "status": status, **extra})


class _FakeMySQLClient:
    """替换 MySQLClient：按类属性决定 health_check 结果，不真连库。"""

    ok = True
    fail_with: Exception | None = None

    def __init__(self, **_kwargs):
        pass

    def health_check(self) -> bool:
        if _FakeMySQLClient.fail_with:
            raise _FakeMySQLClient.fail_with
        return _FakeMySQLClient.ok

    def dispose(self) -> None:
        pass


def _mysql_service(monkeypatch, row) -> tuple[MysqlDatasourceService, StubDAO]:
    monkeypatch.setattr(mysql_module, "MySQLClient", _FakeMySQLClient)
    service = MysqlDatasourceService(session=None)
    stub = StubDAO(row)
    service._dao = stub  # noqa: SLF001 测试注入
    return service, stub


def test_mysql_probe_fail_marks_abnormal(monkeypatch):
    _FakeMySQLClient.fail_with = RuntimeError("connect refused")
    service, stub = _mysql_service(monkeypatch, _row("正常"))
    result = service.test_connection("CFG-1")
    assert result["ok"] is False
    assert stub.updates == [{"id": "CFG-1", "status": "异常"}]
    _FakeMySQLClient.fail_with = None


def test_mysql_probe_success_marks_normal(monkeypatch):
    _FakeMySQLClient.ok = False
    service, stub = _mysql_service(monkeypatch, _row("异常"))
    _FakeMySQLClient.ok = True
    service.test_connection("CFG-1")
    assert stub.updates == [{"id": "CFG-1", "status": "正常"}]


def test_mysql_disabled_status_not_overwritten(monkeypatch):
    _FakeMySQLClient.fail_with = RuntimeError("down")
    service, stub = _mysql_service(monkeypatch, _row("停用"))
    result = service.test_connection("CFG-1")
    assert result["ok"] is False
    assert stub.updates == []  # 停用态探活只报结果，不改状态
    _FakeMySQLClient.fail_with = None


def test_llm_probe_result_persisted(monkeypatch):
    for ping_ok, expected in ((True, "正常"), (False, "异常")):
        monkeypatch.setattr(
            llm_module,
            "_ping_llm",
            lambda *a, ok=ping_ok: {"ok": ok, "latencyMs": 1, "error": None},
        )
        service = LlmConfigService(session=None)
        stub = StubDAO(_row("正常"))
        service._dao = stub  # noqa: SLF001
        service.test_connection("CFG-1")
        assert stub.updates == [{"id": "CFG-1", "status": expected}]


def test_llm_missing_api_key_marks_abnormal(monkeypatch):
    called = []
    monkeypatch.setattr(llm_module, "_ping_llm", lambda *a: called.append(1) or {"ok": True})
    service = LlmConfigService(session=None)
    stub = StubDAO(_row("正常", api_key=""))
    service._dao = stub  # noqa: SLF001
    result = service.test_connection("CFG-1")
    assert result["ok"] is False
    assert called == []  # 没 Key 不发探活请求
    assert stub.updates == [{"id": "CFG-1", "status": "异常"}]


def test_embedding_probe_result_persisted(monkeypatch):
    monkeypatch.setattr(
        embedding_module,
        "_ping_embedding",
        lambda *a: {"ok": False, "latencyMs": 2, "error": "boom"},
    )
    service = EmbeddingConfigService(session=None)
    stub = StubDAO(_row("正常"))
    service._dao = stub  # noqa: SLF001
    service.test_connection("CFG-1")
    assert stub.updates == [{"id": "CFG-1", "status": "异常"}]
