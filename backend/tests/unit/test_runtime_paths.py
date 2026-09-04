from __future__ import annotations

import stat

from utils.runtime_paths import private_state_dir


def test_private_state_dir_uses_configured_owner_only_directory(tmp_path, monkeypatch):
    base = tmp_path / "runtime-state"
    monkeypatch.setenv("TECH_KG_STATE_DIR", str(base))

    result = private_state_dir("reports", "batch-1")

    assert result == base / "reports" / "batch-1"
    assert result.is_dir()
    assert stat.S_IMODE(result.stat().st_mode) == 0o700


def test_private_state_dir_defaults_below_user_home(tmp_path, monkeypatch):
    monkeypatch.delenv("TECH_KG_STATE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = private_state_dir("locks")

    assert result == tmp_path / ".local" / "state" / "tech-kg" / "locks"
    assert stat.S_IMODE(result.stat().st_mode) == 0o700
