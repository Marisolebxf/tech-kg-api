from infra import lifecycle


def test_close_infrastructure_releases_all_singletons(monkeypatch) -> None:
    calls: list[str] = []
    names = [
        "close_graph_clients",
        "reset_milvus_client",
        "reset_schema_s3_storage",
        "reset_llm_client",
        "reset_gkx_element_client",
        "reset_gkx_client",
    ]
    for name in names:
        monkeypatch.setattr(lifecycle, name, lambda name=name: calls.append(name))
    monkeypatch.setattr(lifecycle.mysql_client, "dispose", lambda: calls.append("mysql.dispose"))

    lifecycle.close_infrastructure()

    assert calls == [*names, "mysql.dispose"]
