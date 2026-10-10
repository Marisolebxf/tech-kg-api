"""Build the entity list's literal index without embeddings or Milvus.

Run from backend: PYTHONPATH=. python -m script.build_entity_literal_index --space dev2
"""

from __future__ import annotations

import argparse
import json

from infra.graph_db import get_space_client
from service.entity_literal_index import EntityLiteralIndex, LiteralIndexError
from service.entity_literal_sync import locked_index_session
from service.entity_search import _iter_graph_entities, clear_entity_caches


def build(space: str) -> dict:
    import asyncio

    graph = get_space_client(space)
    with locked_index_session(space) as session:
        labels = sorted(graph.labels())
        skipped: list[str] = []

        def entities():
            yield from _iter_graph_entities(graph, labels, skipped=skipped)
            if skipped:
                raise LiteralIndexError(
                    "索引构建不完整，未发布；失败标签: " + ", ".join(sorted(skipped))
                )

        result = EntityLiteralIndex(session).build(space, entities(), labels)
    asyncio.run(clear_entity_caches())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.space), ensure_ascii=False))


if __name__ == "__main__":
    main()
