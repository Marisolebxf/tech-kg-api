"""Private filesystem locations for runtime state written by local tools."""

from __future__ import annotations

import os
from pathlib import Path


def private_state_dir(*parts: str) -> Path:
    """Return a per-user state directory that is not shared through ``/tmp``.

    ``TECH_KG_STATE_DIR`` may override the base location for containers and
    managed deployments.  Directories are kept owner-only because reports and
    lock metadata can contain identifiers from imported datasets.
    """
    configured = os.environ.get("TECH_KG_STATE_DIR")
    base = Path(configured).expanduser() if configured else Path.home() / ".local/state/tech-kg"
    path = base.joinpath(*parts)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path
