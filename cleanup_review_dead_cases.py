"""清理人工审核「死链」case——按点过去有没有数据判定，不按时间一刀切。

判定口径（与前端 OperationsCenterView.vue 完全一致）：
- 来源记录列（全部 case）：jobId 优先跳 /graph-build/jobs/{jobId}（getJob）；
  无 jobId 回落 executionId/workflowId 跳 /processing-instance/{id}
  （EXEC- 前缀走 getExecution，其余走 getTask）。目标记录在控制库不存在 => 点开空页。
- 日志按钮（仅 C 类 T_EXTRACT_FAIL）：弹窗取快照 rerunExecutionId||executionId
  → workflow_executions（含 payload.taskId/message）→ tasks.payload.logs；
  执行记录不存在 => 空文案；有 task logs 或执行 message 之一 => 有数据。

清理规则：C 类要求 来源记录可打开 且 日志有数据；A 类（T_DIRECT/T_LINK）只要求
来源记录可打开。任一不满足即删除（连同 8 张子表行）。

跑法（host，脚本在 api 容器内执行以复用其 pymysql 与 MYSQL_* env）：
    # 干跑（默认）：打印死/活判定统计，不动数据
    docker exec -i tech-kg-api-lizhou .venv/bin/python - < cleanup_review_dead_cases.py

    # 真删：必须显式给 --backup（'-' = 备份写 stdout，报告走 stderr）
    docker exec -i tech-kg-api-lizhou .venv/bin/python - \
        < cleanup_review_dead_cases.py --apply --backup - > backup.jsonl

    # 恢复一次历史备份（JSONL，cases + 子表全量回灌，幂等冲突即中止回滚）
    docker exec -i tech-kg-api-lizhou .venv/bin/python - \
        < cleanup_review_dead_cases.py --restore /path/to/backup.jsonl
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


def connect_control() -> pymysql.connections.Connection:
    """控制面库（workflow_executions/tasks/workflow_jobs，死链判定的参照数据）。"""
    return pymysql.connect(
        host=os.environ.get("WORKFLOW_MYSQL_HOST", os.environ.get("MYSQL_HOST", "host.docker.internal")),
        port=int(os.environ.get("WORKFLOW_MYSQL_PORT", os.environ.get("MYSQL_PORT", "30306"))),
        user=os.environ.get("WORKFLOW_MYSQL_USERNAME", os.environ.get("MYSQL_USERNAME", "root")),
        password=os.environ.get("WORKFLOW_MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", "")),
        database=os.environ.get("WORKFLOW_MYSQL_DATABASE", "techkg_control_lizhou"),
        charset="utf8mb4",
        autocommit=False,
    )


def chunks(seq: list, size: int = CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_control_refs(cur) -> tuple[set, dict, set, dict, dict]:
    """控制面参照：job 集合、EXEC→job_id 映射、执行集合、EXEC→taskId/message、任务日志。"""
    cur.execute("SELECT id FROM workflow_jobs")
    jobs = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT id, job_id, payload FROM workflow_executions")
    exec_job, exec_task, exec_msg, execs = {}, {}, {}, set()
    for eid, jid, payload in cur.fetchall():
        execs.add(eid)
        exec_job[eid] = jid
        try:
            p = json.loads(payload or "{}")
        except Exception:
            p = {}
        exec_task[eid] = p.get("taskId")
        exec_msg[eid] = p.get("message") or ""
    cur.execute("SELECT id, payload FROM tasks")
    task_logs = {}
    for tid, payload in cur.fetchall():
        try:
            task_logs[tid] = json.loads(payload or "{}").get("logs") or []
        except Exception:
            task_logs[tid] = []
    return jobs, exec_job, execs, {"task": exec_task, "msg": exec_msg}, task_logs


def source_alive(snap: dict, wf_id, jobs, exec_job, execs, task_ids: set) -> tuple[bool, str]:
    """来源记录列点开是否有数据（与前端三级回落一致）。"""
    exec_id = snap.get("executionId")
    eff_job = snap.get("jobId") or exec_job.get(exec_id or "")
    if eff_job:
        return (eff_job in jobs, f"job链接:{eff_job}" + ("" if eff_job in jobs else "(job不存在)"))
    target = exec_id or wf_id
    if not target:
        return False, "无jobId/executionId/workflowId(显示—)"
    if target.startswith("EXEC-"):
        return (target in execs, f"执行链接:{target[:20]}" + ("" if target in execs else "(执行不存在)"))
    # 非 EXEC 前缀走 getTask
    return (target in task_ids, f"任务链接:{target[:20]}" + ("" if target in task_ids else "(任务不存在)"))


def log_alive(snap: dict, execs, exec_meta, task_logs) -> tuple[bool, str]:
    """C 类日志弹窗是否有数据：执行存在且（task logs 或执行 message 非空）。"""
    le = snap.get("rerunExecutionId") or snap.get("executionId")
    if not le:
        return False, "快照无executionId"
    if le not in execs:
        return False, f"执行不存在:{le[:20]}"
    tid = exec_meta["task"].get(le)
    logs = task_logs.get(tid or "", []) if tid else []
    if logs:
        return True, f"task日志{len(logs)}行"
    if exec_meta["msg"].get(le):
        return True, "执行message单行"
    return False, "执行在但无日志无message"


def analyze(cur, control_cur, out) -> tuple[list[str], dict]:
    """返回（待删 case id 列表, 统计）。"""
    jobs, exec_job, execs, exec_meta, task_logs = load_control_refs(control_cur)
    control_cur.execute("SELECT id FROM tasks")
    task_ids = {r[0] for r in control_cur.fetchall()}
    cur.execute(
        f"SELECT id, template_id, status, workflow_id, input_snapshot, DATE(created_at) FROM {CASE_TABLE}"
    )
    dead, alive = [], []
    reason = {}
    for cid, tmpl, status, wf_id, snap_raw, day in cur.fetchall():
        try:
            snap = json.loads(snap_raw or "{}")
        except Exception:
            snap = {}
        src_ok, src_desc = source_alive(snap, wf_id, jobs, exec_job, execs, task_ids)
        fails = [] if src_ok else [f"来源记录空({src_desc})"]
        if tmpl == "T_EXTRACT_FAIL":
            log_ok, log_desc = log_alive(snap, execs, exec_meta, task_logs)
            if not log_ok:
                fails.append(f"日志空({log_desc})")
        ok = not fails
        (alive if ok else dead).append((cid, tmpl, status, day))
        if not ok:
            # 汇总口径只看失败项组合（来源记录空/日志空），具体悬空 id 不进分布
            key = tmpl + " | " + " + ".join(f.split("(")[0] for f in fails)
            reason[key] = reason.get(key, 0) + 1
    out(f"-- 判定结果：存活 {len(alive)} 条 / 死链 {len(dead)} 条 --")
    out("-- 死链原因分布 --")
    for k, n in sorted(reason.items(), key=lambda x: -x[1]):
        out(f"  [{n:>4}] {k}")
    out("-- 死链按模板×状态×日 --")
    dist = {}
    for cid, tmpl, status, day in dead:
        dist[(tmpl, status, str(day))] = dist.get((tmpl, status, str(day)), 0) + 1
    for (tmpl, status, day), n in sorted(dist.items()):
        out(f"  {tmpl}/{status}/{day}: {n}")
    out("-- 存活明细（保留） --")
    keep = {}
    for cid, tmpl, status, day in alive:
        keep[(tmpl, status, str(day))] = keep.get((tmpl, status, str(day)), 0) + 1
    for (tmpl, status, day), n in sorted(keep.items()):
        out(f"  {tmpl}/{status}/{day}: {n}")
    return [c[0] for c in dead], {"alive": len(alive), "dead": len(dead)}


def report_children(cur, case_ids: list[str], out) -> dict:
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
    for table in CHILD_TABLES + [CASE_TABLE]:
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


def restore(conn, cur, path: str, out) -> None:
    """按备份 JSONL 全量回灌（cases + 子表），单事务，遇主键冲突即中止回滚。"""
    rows_by_table: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rows_by_table.setdefault(rec["table"], []).append(rec["row"])
    order = [CASE_TABLE] + CHILD_TABLES  # 先父后子，无外键其实无序，稳妥起见
    for table in order:
        for row in rows_by_table.get(table, []):
            cols = list(row.keys())
            cur.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})",
                [row[c] for c in cols],
            )
    conn.commit()
    for table in order:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        out(f"  恢复后 {table}: {cur.fetchone()[0]} 行（本次回灌 {len(rows_by_table.get(table, []))} 行）")


def main() -> int:
    ap = argparse.ArgumentParser(description="清理点开为空的人工审核死链 case（默认 dry-run）")
    ap.add_argument("--apply", action="store_true", help="真删（默认只统计）")
    ap.add_argument("--backup", help="apply 时必填；备份 JSONL 输出路径，'-' 表示 stdout")
    ap.add_argument("--restore", help="恢复模式：从备份 JSONL 回灌数据")
    args = ap.parse_args()

    backup_stdout = args.apply and args.backup == "-"
    out = (lambda m: print(m, file=sys.stderr)) if backup_stdout else print

    if args.restore:
        conn = connect()
        cur = conn.cursor()
        try:
            out(f"开始恢复：{args.restore}")
            restore(conn, cur, args.restore, out)
            return 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    if args.apply and not args.backup:
        print("错误：--apply 必须显式指定 --backup（备份 JSONL 路径或 '-'）", file=sys.stderr)
        return 2

    conn = connect()
    cur = conn.cursor()
    control_conn = connect_control()
    control_cur = control_conn.cursor()
    try:
        dead_ids, _ = analyze(cur, control_cur, out)
        if not dead_ids:
            out("没有死链 case，无需清理。")
            return 0
        report_children(cur, dead_ids, out)

        if not args.apply:
            out("dry-run 结束，未删除任何数据。加 --apply --backup <path|-> 执行删除。")
            return 0

        sink = sys.stdout if backup_stdout else open(args.backup, "w", encoding="utf-8")
        try:
            backup(cur, dead_ids, sink)
            if not backup_stdout:
                sink.close()
            out(f"备份完成 -> {args.backup}")
        except Exception:
            if not backup_stdout and not sink.closed:
                sink.close()
            raise

        deleted = apply_delete(conn, cur, dead_ids)
        out("-- 已删除（单事务） --")
        for table, n in deleted.items():
            out(f"  {table}: {n}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
        control_conn.close()


if __name__ == "__main__":
    sys.exit(main())
