"""学者机构对齐算子——包装 script.align_scholar_affiliations。

针对 AFFILIATED_WITH 边上的桩机构（org_{md5hash[:16]}），
通过 Milvus 混合检索找出真实机构 VID，写 SAME_AS 边。
"""


def operator(data, ctx):
    """执行学者机构对齐。

    Args:
        data: 上游数据，本算子忽略（候选来自图与 Milvus）。
        ctx: 运行参数，支持 ``dry_run``（默认 True）、``top_k``（默认 5）、
            ``min_score``（默认 0.65）、``preview``（默认 5）。

    Returns:
        单元素列表，含 ``status``（ok/error）、``params`` 与 ``stats``。
    """
    _ = data
    from script.align_scholar_affiliations import run

    ctx = ctx or {}
    dry_run = bool(ctx.get("dry_run", True))
    top_k = int(ctx.get("top_k", 5))
    min_score = float(ctx.get("min_score", 0.65))
    preview = int(ctx.get("preview", 5))
    params = {
        "dry_run": dry_run,
        "top_k": top_k,
        "min_score": min_score,
        "preview": preview,
    }
    try:
        stats = run(
            dry_run=dry_run,
            top_k=top_k,
            min_score=min_score,
            preview=preview,
        )
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "operator": "user.scholar.align_affiliations",
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "params": params,
            }
        ]
    return [
        {
            "operator": "user.scholar.align_affiliations",
            "status": "ok",
            "params": params,
            "stats": stats,
        }
    ]
