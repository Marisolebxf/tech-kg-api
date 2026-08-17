"""学者关系抽取算子——包装 script.load_scholar_relations。

写 AFFILIATED_WITH（Person→Organization）和 COAUTHOR_WITH（Person→Person）边。
可选：include_authored_by_fallback 补 AUTHORED_BY 兜底边。
"""


def operator(data, ctx):
    """执行学者关系入图。

    Args:
        data: 上游数据，本算子忽略（源数据直接从 MySQL 读）。
        ctx: 运行参数，支持 ``database``（默认 gkx_element）、``dry_run``（默认 True）、
            ``include_authored_by_fallback``（默认 False，是否补 AUTHORED_BY 兜底边）。

    Returns:
        单元素列表，含 ``status``（ok/error）、``params`` 与 ``stats``。
    """
    from script.load_scholar_relations import run

    ctx = ctx or {}
    database = str(ctx.get("database", "gkx_element"))
    dry_run = bool(ctx.get("dry_run", True))
    include_authored_by_fallback = bool(ctx.get("include_authored_by_fallback", False))
    params = {
        "database": database,
        "dry_run": dry_run,
        "include_authored_by_fallback": include_authored_by_fallback,
    }
    try:
        stats = run(
            database=database,
            dry_run=dry_run,
            include_authored_by_fallback=include_authored_by_fallback,
        )
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "operator": "user.scholar.load_relations",
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "params": params,
            }
        ]
    return [
        {
            "operator": "user.scholar.load_relations",
            "status": "ok",
            "params": params,
            "stats": stats,
        }
    ]
