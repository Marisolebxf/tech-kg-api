"""Mount legacy routers into the main FastAPI app without modifying legacy source."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI


def setup_legacy_import_path() -> None:
    legacy_root = Path(__file__).resolve().parents[1] / "legacy"
    legacy_root_str = str(legacy_root)
    if legacy_root_str not in sys.path:
        sys.path.insert(0, legacy_root_str)


def register_legacy_routers(app: FastAPI) -> None:
    setup_legacy_import_path()
    from app.routers.scholar_paper_cooperation import router as scholar_paper_cooperation_router

    app.include_router(scholar_paper_cooperation_router, prefix="/api/v1")
