"""清理人工审核旧 case——控制面执行/任务记录已被清理、来源记录与重跑日志点开全空的悬空旧数据。

背景（2026-09-18 统计）：业务库 manual_review_case 里 created_at < 2026-09-17 的旧 case
（约 385+ 条）快照中的 executionId/jobId 指向的控制库 workflow_executions/workflow_jobs/tasks
行已被清理重置，来源记录链接与失败重跑日志弹窗点开均为空页/空文案。9/17 起修复
（64f815c 来源记录打通 / 64fb758 日志回填）生效后新建的 case 基本正常，故按时间边界清理旧案。

跑法（host，脚本在 api 容器内执行以复用其 pymysql 与 MYSQL_* env）：
    # 干跑（默认）：只打印将删除的统计，不动数据
    docker exec -i tech-kg-api-lizhou .venv/bin/python - < cleanup_review_old_cases.py

    # 真删：必须显式给 --backup（'-' = 备份写到 stdout，报告走 stderr，host 侧重定向留存）
    docker exec -i tech-kg-api-lizhou .venv/bin/python - \
        < cleanup_review_old_cases.py --apply --backup - > review_old_cases_backup.jsonl

    # 自定义边界（默认 2026-09-17，即删除该日 00:00 之前创建的 case）
    ... --before 2026-09-15 ...

删除范围：manual_review_case 及其全部子表（decision/draft/evidence/audit_log/outbox/
correction/execution/execution_event）中 case_id 命中目标的行，单事务先子后父。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import pymysql

# 先子后父；子表一律按 case_id 关联，case 表本身主键列是 id
CHILD_TABLES = [
    "manual_review_execution_event",
    "manual_review_execution",
    "manual_review_correction",
    "manual_review_outbox",
    "manual_review_evidence",
    "manual_review_audit_log",
    "manual_review_decision",
    "manual_review_draft",
]
CASE_TABLE = "manual_review_case"
# 备份/删除时各表用于命中目标 case 的列
KEY_COL = {table: "case_id" for table in CHILD_TABLES}
KEY_COL[CASE_TABLE] = "id"
CHUNK = 500  # IN 列表分块上限


def connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "host.docker.internal"),
        port=int(os.environ.get("MYSQL_PORT", "30306")),
        user=os.environ.get("MYSQL_USERNAME", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DATABASE", "gkx_element"),
        charset="utf8mb4",
        autocommit=False,
    )


def chunks(seq: list, size: int = CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def fetch_case_ids(cur, before: str) -> list[str]:
    cur.execute(
        f"SELECT id FROM {CASE_TABLE} WHERE created_at < %s ORDER BY created_at",
        (before,),
    )
    return [r[0] for r in cur.fetchall()]


def report(cur, case_ids: list[str], out) -> dict:
    """打印将删除的统计明细，返回 {表名: 行数} 供 apply 后核对。"""
    ph = ",".join(["%s"] * len(case_ids))
    cur.execute(
        f"SELECT template_id, status, COUNT(*) FROM {CASE_TABLE} WHERE id IN ({ph}) "
        "GROUP BY template_id, status",
        case_ids,
    )
    out("-- 将删除 case 按模板×状态 --")
    plan = {}
    for tmpl, status, n in cur.fetchall():
        out(f"  {tmpl}/{status}: {n}")
        plan[f"{tmpl}/{status}"] = n
    cur.execute(
        f"SELECT DATE(created_at), COUNT(*) FROM {CASE_TABLE} WHERE id IN ({ph}) "
        "GROUP BY DATE(created_at) ORDER BY 1",
        case_ids,
    )
    out("-- 按创建日 --")
    for day, n in cur.fetchall():
        out(f"  {day}: {n}")
    counts = {}
    for table in CHILD_TABLES:
        total = 0
        for chunk in chunks(case_ids):
            cph = ",".join(["%s"] * len(chunk))
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {KEY_COL[table]} IN ({cph})", chunk
            )
            total += cur.fetchone()[0]
        counts[table] = total
    counts[CASE_TABLE] = len(case_ids)
    out("-- 连带删除的子表行数 --")
    for table, n in counts.items():
        out(f"  {table}: {n}")
    return counts


def backup(cur, case_ids: list[str], sink) -> None:
    """把将删除的行按 JSONL 备份（cases + 全部子表）。"""
    tables = CHILD_TABLES + [CASE_TABLE]
    for table in tables:
        for chunk in chunks(case_ids):
            cph = ",".join(["%s"] * len(chunk))
            cur.execute(f"SELECT * FROM {table} WHERE {KEY_COL[table]} IN ({cph})", chunk)
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                rec = dict(zip(cols, row))
                sink.write(
                    json.dumps({"table": table, "row": rec}, ensure_ascii=False, default=str) + "\n"
                )


def apply_delete(conn, cur, case_ids: list[str]) -> dict:
    deleted = {}
    for table in CHILD_TABLES + [CASE_TABLE]:
        total = 0
        for chunk in chunks(case_ids):
            cph = ",".join(["%s"] * len(chunk))
            total += cur.execute(f"DELETE FROM {table} WHERE {KEY_COL[table]} IN ({cph})", chunk)
        deleted[table] = total
    conn.commit()
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(description="清理人工审核旧 case（默认 dry-run）")
    ap.add_argument("--before", default="2026-09-17", help="删除 created_at 早于该日 00:00 的 case（YYYY-MM-DD）")
    ap.add_argument("--apply", action="store_true", help="真删（默认只统计）")
    ap.add_argument("--backup", help="apply 时必填；备份 JSONL 输出路径，'-' 表示 stdout")
    args = ap.parse_args()

    before = f"{args.before} 00:00:00"
    # 备份走 stdout 时，报告与进度改走 stderr，避免混流
    backup_stdout = args.apply and args.backup == "-"
    out = (lambda m: print(m, file=sys.stderr)) if backup_stdout else print

    if args.apply and not args.backup:
        print("错误：--apply 必须显式指定 --backup（备份 JSONL 路径或 '-'）", file=sys.stderr)
        return 2

    conn = connect()
    cur = conn.cursor()
    try:
        case_ids = fetch_case_ids(cur, before)
        if not case_ids:
            out(f"没有 created_at < {before} 的 case，无需清理。")
            return 0
        out(f"目标：created_at < {before} 的 case 共 {len(case_ids)} 条（首 {case_ids[0]} 尾 {case_ids[-1]}）")
        report(cur, case_ids, out)

        if not args.apply:
            out("dry-run 结束，未删除任何数据。加 --apply --backup <path|-> 执行删除。")
            return 0

        sink = sys.stdout if backup_stdout else open(args.backup, "w", encoding="utf-8")
        try:
            backup(cur, case_ids, sink)
            if not backup_stdout:
                sink.close()
            out(f"备份完成 -> {args.backup}")
        except Exception:
            if not backup_stdout and not sink.closed:
                sink.close()
            raise

        deleted = apply_delete(conn, cur, case_ids)
        out("-- 已删除（单事务） --")
        for table, n in deleted.items():
            out(f"  {table}: {n}")
        remaining = fetch_case_ids(cur, before)
        out(f"复核：边界外剩余旧 case {len(remaining)} 条（应为 0）")
        return 0 if not remaining else 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
