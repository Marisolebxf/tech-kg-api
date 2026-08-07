"""学者消歧算子——包装 script.dedupe_scholar_persons。

从图库拉 Person 顶点，融合 Milvus 混合检索分和字段相似度打分，
识别 "疑似同一人" 的 Person 对：
- 综合分 >= high_threshold：高置信，可选写 SAME_AS 边
- mid_threshold <= 综合分 < high_threshold：疑似，写报表供人工复核
"""


def operator(data, ctx):
    from script.dedupe_scholar_persons import run

    ctx = ctx or {}
    dry_run = bool(ctx.get("dry_run", True))
    write = bool(ctx.get("write", False))
    top_k = int(ctx.get("top_k", 5))
    high_threshold = float(ctx.get("high_threshold", 0.75))
    mid_threshold = float(ctx.get("mid_threshold", 0.55))
    report_path = ctx.get("report_path")
    if report_path is not None:
        report_path = str(report_path)
    preview = int(ctx.get("preview", 8))
    params = {
        "dry_run": dry_run,
        "write": write,
        "top_k": top_k,
        "high_threshold": high_threshold,
        "mid_threshold": mid_threshold,
        "report_path": report_path,
        "preview": preview,
    }
    try:
        stats = run(
            dry_run=dry_run,
            write=write,
            top_k=top_k,
            high_threshold=high_threshold,
            mid_threshold=mid_threshold,
            report_path=report_path,
            preview=preview,
        )
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "operator": "user.scholar.dedupe_persons",
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "params": params,
            }
        ]
    return [
        {
            "operator": "user.scholar.dedupe_persons",
            "status": "ok",
            "params": params,
            "stats": stats,
        }
    ]
