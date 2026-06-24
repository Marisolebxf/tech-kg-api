"""Configuration for the trs-graph repository, loaded from TRS_GRAPH_* env vars."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class TRSGraphSettings(BaseModel):
    """Connection settings for trs-graph-service."""

    base_url: str = "http://localhost:8090"
    space: str = "entity_binding_demo"
    api_key: str | None = None
    timeout: int = 30

    @classmethod
    def from_env(cls, prefix: str = "TRS_GRAPH") -> TRSGraphSettings:
        """Load settings from ``<prefix>_*`` environment variables."""

        def env(name: str) -> str | None:
            return os.environ.get(f"{prefix}_{name}")

        return cls(
            base_url=env("BASE_URL") or "http://localhost:8090",
            space=env("SPACE") or "entity_binding_demo",
            api_key=env("API_KEY") or None,
            timeout=int(env("TIMEOUT") or 30),
        )
