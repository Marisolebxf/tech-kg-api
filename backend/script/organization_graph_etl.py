"""Deprecated compatibility entry for the organization entity loader.

Historically this module created vertices and relations together.  That behavior
could conflict with ``organization_relation_etl`` and generate different VIDs or
duplicate edges.  It now delegates to ``organization_entity_etl`` and therefore
never writes an edge.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from script.organization_entity_etl import main as entity_main

logger = logging.getLogger("script.organization_graph_etl")


def main(argv: Sequence[str] | None = None) -> int:
    logger.warning(
        "organization_graph_etl is deprecated and entity-only; "
        "use organization_entity_etl for vertices and organization_relation_etl for edges"
    )
    return entity_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
