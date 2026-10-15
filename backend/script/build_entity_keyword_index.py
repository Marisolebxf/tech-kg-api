"""全量构建实体关键词 ES 索引（spike 验证工具）。

图上属性 CONTAINS 无法建索引，实体列表文字搜索只能逐标签全扫；本脚本把
每个图空间的全部实体（VID + 全量属性值 + 序列化列表项）镜像进 ES 的
``kg_entity_kw_{space}`` 索引，供 ``service/entity_search.py`` 的 ES 通道查询。

- 幂等：``_id = vid``，重复执行为覆盖写；``--drop`` 先删索引重建（清走已删实体）；
- 分页拉取（``paged_nodes_by_label``，标签索引路径）+ 批量 bulk，串行逐标签，
  对共享 graphd 友好；
- 逐标签打印进度与耗时，结尾输出同步吞吐与索引文档数核对。

用法（api 容器内，或按 [[backend-container-test-runbook]] 一次性容器）::

    .venv/bin/python -m script.build_entity_keyword_index --space dev2 \
        --es-url http://es1016-es:9200 [--drop] [--labels Person,Org] [--batch-size 1000]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from infra.elasticsearch import ElasticsearchError, EntityKeywordES
from infra.graph_db import get_space_client
from service.entity_search import (
    _serialize_browse_item,
)  # 同仓脚本复用，保证回放项与图直查逐字节一致


def _search_text(vid: str, props: dict) -> str:
    """检索语料 = VID + 全量属性值（不截断、不挑 key）。

    与图谓词 ``id(v) CONTAINS kw OR any(values(properties(v)) CONTAINS kw)``
    保持同一口径：属性 key 不参与匹配（图上本来也不匹配 key）。
    """
    parts = [str(vid)]
    for value in props.values():
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            try:
                parts.append(
                    json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
                )
            except (TypeError, ValueError):
                continue
        else:
            parts.append(str(value))
    return "\n".join(parts)


def build_docs(nodes: list, label: str) -> list[dict]:
    docs = []
    for node in nodes:
        props = dict(node.properties or {})
        vid = str(node.id)
        docs.append(
            {
                "vid": vid,
                "entity_type": label,
                "search_text": _search_text(vid, props),
                "item": _serialize_browse_item(node, label),
            }
        )
    return docs


def sync_label(store: EntityKeywordES, graph, space: str, label: str, batch_size: int) -> int:
    offset = 0
    total = 0
    started = time.monotonic()
    while True:
        nodes = graph.paged_nodes_by_label(label, limit=batch_size, offset=offset)
        if not nodes:
            break
        docs = build_docs(nodes, label)
        store.upsert(space, docs)
        total += len(docs)
        offset += len(nodes)
        elapsed = time.monotonic() - started
        print(f"  [{label}] +{len(docs)} (累计 {total}, {elapsed:.1f}s)", flush=True)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--space", default=os.environ.get("TRS_GRAPH_SPACE", "dev2"), help="图空间名"
    )
    parser.add_argument(
        "--es-url",
        default=os.environ.get("ENTITY_SEARCH_ES_URL", ""),
        help="ES 地址，如 http://es1016-es:9200（默认读 ENTITY_SEARCH_ES_URL）",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="分页拉取批次大小")
    parser.add_argument("--labels", default="", help="只同步指定标签（逗号分隔），调试用")
    parser.add_argument("--drop", action="store_true", help="先删除索引重建（清走已删实体）")
    args = parser.parse_args()

    if not args.es_url:
        parser.error("需要 --es-url 或环境变量 ENTITY_SEARCH_ES_URL")

    store = EntityKeywordES(args.es_url)
    graph = get_space_client(args.space)

    labels = sorted(graph.labels())
    if args.labels:
        wanted = [x.strip() for x in args.labels.split(",") if x.strip()]
        unknown = [x for x in wanted if x not in labels]
        if unknown:
            print(
                f"未知标签: {unknown}（空间 {args.space} 共 {len(labels)} 个标签）", file=sys.stderr
            )
            return 2
        labels = wanted

    print(f"空间 {args.space}: {len(labels)} 个标签 → ES {args.es_url}")
    if args.drop:
        store.drop_index(args.space)
        print("已删除旧索引")
    store.ensure_index(args.space)

    started = time.monotonic()
    per_label: dict[str, int] = {}
    try:
        for label in labels:
            label_started = time.monotonic()
            count = sync_label(store, graph, args.space, label, args.batch_size)
            per_label[label] = count
            print(
                f"[{label}] 完成: {count} 个实体, {time.monotonic() - label_started:.1f}s",
                flush=True,
            )
    except ElasticsearchError as exc:
        print(f"ES 写入失败: {exc}", file=sys.stderr)
        return 1

    store.refresh(args.space)
    indexed = store.doc_count(args.space)
    elapsed = time.monotonic() - started
    total = sum(per_label.values())
    print(
        f"\n同步完成: {len(per_label)} 个标签 / 图侧 {total} 个实体 / ES 索引 {indexed} 篇文档"
        f" / 耗时 {elapsed:.1f}s（吞吐 {total / elapsed:.0f} 实体/s）"
    )
    if indexed != total:
        print("⚠️ 图侧与 ES 文档数不一致（可能有重复 VID 被覆盖或写入丢失）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
