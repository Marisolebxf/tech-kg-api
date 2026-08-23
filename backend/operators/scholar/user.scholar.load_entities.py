"""学者实体抽取算子——包装 script.load_scholar_entities。

薄封装：ctx 传递 dry_run/database 等参数，返回统计结果。
data 参数忽略（本算子从 MySQL 读取源数据）。
"""


def operator(data, ctx):
    """执行学者实体入图。

    Args:
        data: 上游数据，本算子忽略（源数据直接从 MySQL 读）。
        ctx: 运行参数，支持 ``database``（默认 gkx_element）与 ``dry_run``（默认 True）。

    Returns:
        单元素列表，含 ``status``（ok/error）、``params`` 与 ``stats``。
    """
    from script.load_scholar_entities import run

    ctx = ctx or {}
    database = str(ctx.get("database", "gkx_element"))
    dry_run = bool(ctx.get("dry_run", True))
    try:
        stats = run(database=database, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "operator": "user.scholar.load_entities",
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "params": {"database": database, "dry_run": dry_run},
            }
        ]
    return [
        {
            "operator": "user.scholar.load_entities",
            "status": "ok",
            "params": {"database": database, "dry_run": dry_run},
            "stats": stats,
        }
    ]
