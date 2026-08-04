"""学者 Milvus 索引构建算子——包装 script.build_scholar_milvus_index。

从图库拉 Person 顶点，双编码（m3e-small 稠密 + BM25 稀疏）后写入 Milvus。
"""


def operator(data, ctx):
    from script.build_scholar_milvus_index import run

    ctx = ctx or {}
    dry_run = bool(ctx.get("dry_run", True))
    drop_existing = bool(ctx.get("drop_existing", False))
    preview = int(ctx.get("preview", 5))
    params = {"dry_run": dry_run, "drop_existing": drop_existing, "preview": preview}
    try:
        stats = run(dry_run=dry_run, drop_existing=drop_existing, preview=preview)
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "operator": "user.scholar.build_milvus_index",
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "params": params,
            }
        ]
    return [
        {
            "operator": "user.scholar.build_milvus_index",
            "status": "ok",
            "params": params,
            "stats": stats,
        }
    ]
