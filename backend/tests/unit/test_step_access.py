"""activity 侧 access 合并单测（sidecar 为准 + 降级路径，无需真 Temporal 子进程）。"""

from __future__ import annotations

import json
from pathlib import Path

from service.temporal_workflows import _cleanup_sidecar, _log_failed_access, _merge_access


def _write_sidecar(path: Path, events: list[dict]) -> str:
    path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    return str(path)


def test_merge_prefers_sidecar_when_stdout_missing(tmp_path: Path) -> None:
    """超时/崩溃路径：stdout 没有 _access，仅凭 sidecar 恢复报告。"""
    sidecar = _write_sidecar(
        tmp_path / "access.jsonl",
        [
            {"t": "mysql", "db": "gkx", "table": "dwd_paper", "op": "SELECT"},
            {"t": "graph", "kind": "tag", "name": "Scholar", "op": "write"},
            {"t": "llm", "model": "glm-4.7-flash", "ok": True},
        ],
    )
    merged = _merge_access(None, sidecar)
    assert merged is not None
    assert merged["mysql"]["gkx"]["dwd_paper"]["ops"] == ["SELECT"]
    assert merged["graph"]["tag"]["Scholar"] == {"ops": ["write"], "count": 1}
    assert merged["llm"]["glm-4.7-flash"] == {"calls": 1, "failures": 0}


def test_merge_unions_sidecar_and_stdout(tmp_path: Path) -> None:
    sidecar = _write_sidecar(
        tmp_path / "access.jsonl",
        [{"t": "mysql", "db": "db1", "table": "t_a", "op": "SELECT"}],
    )
    stdout_access = {
        "mysql": {"db1": {"t_a": {"ops": ["SELECT"], "statements": 5}}},
        "graph": {},
        "milvus": {},
        "llm": {},
        "embedding": {},
    }
    merged = _merge_access(stdout_access, sidecar)
    assert merged is not None
    assert merged["mysql"]["db1"]["t_a"]["statements"] == 5


def test_merge_falls_back_to_stdout_when_sidecar_missing(tmp_path: Path) -> None:
    stdout_access = {"mysql": {"db1": {"t_b": {"ops": ["SELECT"], "statements": 1}}}}
    merged = _merge_access(stdout_access, str(tmp_path / "nope.jsonl"))
    assert merged is stdout_access


def test_merge_both_empty() -> None:
    assert _merge_access(None, None) is None


def test_merge_never_raises_on_corrupt_sidecar(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text("not json\nalso not json\n", encoding="utf-8")
    stdout_access = {"mysql": {"db1": {"t_b": {"ops": ["SELECT"], "statements": 1}}}}
    # 全损坏行 → sidecar 聚合为空报告，降级返回 stdout 报告
    assert _merge_access(stdout_access, str(corrupt)) == stdout_access


def test_failed_access_logged_from_sidecar(tmp_path: Path, caplog) -> None:
    sidecar = _write_sidecar(
        tmp_path / "access.jsonl",
        [{"t": "milvus", "collection": "techkg_chunks", "op": "read"}],
    )
    import logging

    with caplog.at_level(logging.WARNING):
        _log_failed_access("step extract 执行超时", sidecar)
    assert "access 溯源留账" in caplog.text
    assert "techkg_chunks" in caplog.text


def test_cleanup_sidecar_removes_file(tmp_path: Path) -> None:
    sidecar = tmp_path / "access.jsonl"
    sidecar.write_text("", encoding="utf-8")
    _cleanup_sidecar(str(sidecar))
    assert not sidecar.exists()
    _cleanup_sidecar(str(tmp_path / "gone.jsonl"))  # 不存在也不抛错
    _cleanup_sidecar(None)
