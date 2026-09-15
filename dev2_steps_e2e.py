"""dev2 端到端验证：STEPS 多步脚本全链路（SSE 上传 → 绑源 → 触发 → 分步统计/审核/水位）。

跑法（host）：python3 dev2_steps_e2e.py
前置：tech-kg-api-dev2 + tech-kg-temporal-worker-dev2 运行中（8002），
temporal-mysql-dev2 里有 techkg_e2e.widgets（w1–w4）。脚本幂等，可重复跑。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid

API = "http://localhost:8002/api/v1"

SCRIPT = '''"""E2E 三步脚本：清洗 → 机构解析（未命中进审核）→ 出实体。"""
STEPS = [
    {"id": "clean", "fn": "step_clean"},
    {"id": "resolve", "fn": "step_resolve"},
    {"id": "emit", "fn": "step_emit"},
]


def step_clean(payload):
    rows = payload.get("rows") or []
    cleaned, failures = [], []
    for row in rows:
        name = str(row.get("name") or "")
        if "POISON" in name:
            failures.append({"recordId": str(row["id"]), "error": "ValueError: POISON 行拒绝解析"})
        else:
            cleaned.append({"id": str(row["id"]), "name": name})
    return {"cleaned": cleaned, "failures": failures, "stats": {"cleaned": len(cleaned)}}


def step_resolve(payload):
    resolved, pending = [], []
    for row in payload["input"]["cleaned"]:
        org = row["name"].split("-", 1)[1] if "-" in row["name"] else ""
        if not org:
            pending.append({
                "kind": "entity",
                "objectName": row["id"],
                "reason": "机构名为空，需人工补录",
                "sourceTable": "techkg_e2e.widgets",
                "sourceRecordId": row["id"],
            })
        else:
            resolved.append({"id": row["id"], "name": row["name"]})
    return {"resolved": resolved, "pendingReview": pending, "stats": {"resolved": len(resolved)}}


def step_emit(payload):
    return {
        "entities": [
            {"id": "widget_" + r["id"], "props": {"id": r["id"], "name": r["name"]}}
            for r in payload["input"]["resolved"]
        ]
    }
'''


def req(method: str, path: str, body=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def step(msg):
    print(f"\n=== {msg}")


def ok(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        raise SystemExit(f"E2E 失败: {msg}")


def wait_execution(execution_id: str, timeout: int = 180):
    for _ in range(timeout // 3):
        code, resp = req("GET", f"/workflow-system/executions/{execution_id}")
        if code == 200 and resp.get("data", {}).get("status") in (
            "COMPLETED", "FAILED", "TERMINATED", "CANCELED", "TIMED_OUT"
        ):
            return resp["data"]
        time.sleep(3)
    raise SystemExit(f"执行超时未终态: {execution_id}")


def main():
    run = uuid.uuid4().hex[:6]

    # 重置测试数据：w1/w4 带机构名、w2 机构名空、w3 毒行
    import subprocess as _sp
    _sp.run(
        ["docker", "exec", "tech-kg-temporal-mysql-dev2", "mysql", "-uroot", "-ptemporal",
         "--default-character-set=utf8mb4", "-e",
         "UPDATE techkg_e2e.widgets SET name='甲-浙江大学', update_time=NOW() WHERE id='w1'; "
         "UPDATE techkg_e2e.widgets SET name='乙-', update_time=NOW() WHERE id='w2'; "
         "UPDATE techkg_e2e.widgets SET name='POISON毒行', update_time=NOW() WHERE id='w3'; "
         "UPDATE techkg_e2e.widgets SET name='丙-浙江大学', update_time=NOW() WHERE id='w4';"],
        check=True, capture_output=True,
    )

    # 1. 数据源（幂等复用）
    step("1. 准备数据源（temporal-mysql-dev2 / techkg_e2e）")
    code, resp = req("GET", "/mysql-datasources")
    data = resp.get("data") or []
    items = data.get("items", []) if isinstance(data, dict) else data
    ds = next(
        (i for i in items if i.get("host") == "temporal-mysql-dev2" and i.get("database") == "techkg_e2e"),
        None,
    )
    if ds is None:
        code, resp = req(
            "POST", "/mysql-datasources",
            {
                "name": f"e2e-steps-{run}", "host": "temporal-mysql-dev2", "port": 3306,
                "username": "root", "password": "temporal", "database": "techkg_e2e",
                "description": "多步 e2e",
            },
        )
        ok(code in (200, 201), f"创建数据源 {code}")
        ds = resp["data"]
    datasource_id = ds["id"]

    # 2. schema（幂等：删旧建新；tag DDL 随 dev2 默认空间）
    step("2. 创建实体 Schema E2EStepWidget")
    code, resp = req("GET", "/schema-management/schemas?keyword=E2EStepWidget&pageSize=100")
    old = next(
        (i for i in (resp.get("data") or {}).get("items") or [] if i.get("name") == "E2EStepWidget"),
        None,
    )
    if old:
        req("DELETE", f"/schema-management/schemas/{old['id']}")
    code, resp = req(
        "POST", "/schema-management/schemas/entities",
        {
            "schemaKey": f"e2e-step-widget-{run}",
            "name": "E2EStepWidget",
            "label": "E2E多步挂件",
            "description": "多步 e2e",
            "identityKey": "id",
            "properties": [
                {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
                {"name": "name", "dataType": "string", "required": False, "category": "core", "rule": ""},
            ],
            "isCore": False, "version": "v1.0",
        },
    )
    ok(code in (200, 201), f"创建 schema {code}: {str(resp)[:150]}")
    schema_id = resp["data"]["id"]

    # 3. 走浏览器同款 SSE 上传通道（含 LLM 安全校验）
    step("3. SSE 通道上传 STEPS 三步脚本（POST /script/verify）")
    import pathlib
    import subprocess

    script_file = pathlib.Path(f"/tmp/e2e_steps_{run}.py")
    script_file.write_text(SCRIPT, encoding="utf-8")
    r = subprocess.run(
        ["curl", "-sS", "-N", "-m", "120", "-X", "POST",
         f"{API}/schema-management/schemas/{schema_id}/script/verify",
         "-H", "X-User-Id: e2e-admin", "-F", f"script=@{script_file}"],
        capture_output=True, text=True,
    )
    events = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("data: ")]
    final = json.loads(events[-1][6:]) if events else {}
    ok(final.get("type") == "success", f"SSE 上传成功（终事件 {str(final)[:150]}）")

    code, resp = req("GET", f"/schema-management/schemas/{schema_id}")
    script = resp["data"]["script"]
    ok(script.get("workflowFunctionName") == "step_clean",
       f"workflowFunctionName=step_clean（实际 {script.get('workflowFunctionName')}）")

    # 4. 绑定来源
    step("4. 绑定来源表 widgets（pk=id, time=update_time）")
    code, resp = req(
        "PUT", f"/schema-management/schemas/{schema_id}/sources",
        {"sources": [{
            "datasourceId": datasource_id, "databaseName": "techkg_e2e",
            "tableName": "widgets", "pkColumn": "id", "timeColumn": "update_time",
        }]},
    )
    ok(code in (200, 201), f"绑定来源 {code}: {str(resp)[:150]}")

    # 5. 建任务触发
    step("5. 创建抽取任务并触发（batchSize=2 → 2 批）")
    code, resp = req(
        "POST", "/workflow-system/jobs",
        {
            "name": f"e2e多步-{run}", "taskType": "extract", "schemaId": schema_id,
            "schedule": {"kind": "once"}, "graphSpace": "dev2", "batchSize": 2,
        },
    )
    ok(code in (200, 201), f"创建任务 {code}: {str(resp)[:200]}")
    job_id = resp["data"]["id"]
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    ok(code in (200, 201), f"触发 {code}: {str(resp)[:150]}")
    exec1 = resp["data"]["id"]

    execution = wait_execution(exec1)
    out = execution.get("output") or {}
    ok(execution["status"] == "COMPLETED",
       f"执行 COMPLETED（{execution['status']} {str(execution.get('message'))[:120]}）")

    # 6. 分步统计
    step("6. 执行结果分步统计 steps")
    expect_steps = {
        "clean": {"records": 0, "written": 0, "failed": 1},
        "resolve": {"records": 0, "written": 0, "failed": 0},
        "emit": {"records": 2, "written": 2, "failed": 0},
    }
    got = out.get("steps") or {}
    for sid, stat in expect_steps.items():
        actual = got.get(sid) or {}
        ok(actual.get("status") == "COMPLETED", f"steps[{sid}].status=COMPLETED（实际 {actual.get('status')}）")
        ok(all(actual.get(k) == v for k, v in stat.items()),
           f"steps[{sid}]={stat}（实际 {actual}）")
    src = (out.get("sources") or [{}])[0]
    ok(src.get("rows") == 4 and src.get("batches") == 2,
       f"读取 4 行 / 2 批（实际 {src.get('rows')}/{src.get('batches')}）")
    ok(src.get("written") == 2, f"写图 2 实体（实际 {src.get('written')}）")
    src_steps = src.get("steps") or {}
    ok(all((src_steps.get(sid) or {}).get(k) == v for sid, stat in expect_steps.items() for k, v in stat.items()),
       f"来源摘要 steps 计数一致（实际 {src_steps}）")
    ok((out.get("failures") or {}).get("count") == 1, f"毒行失败 1 条（实际 {out.get('failures')}）")

    # 7. 任务详情 pipeline_steps 渲染分步
    step("7. 任务详情 steps（pipeline_steps 渲染）")
    code, resp = req("GET", f"/task-center/tasks/{execution.get('taskId')}")
    task = resp.get("data") or {}
    by_id = {s.get("id"): s for s in (task.get("steps") or [])}
    ok(set(by_id) >= {"clean", "resolve", "emit"}, f"任务 steps 含三步（实际 {sorted(by_id)}）")
    for sid, stat in expect_steps.items():
        s = by_id.get(sid) or {}
        ok(s.get("status") == "成功", f"steps[{sid}].status=成功（实际 {s.get('status')}）")
        ok(s.get("count") == str(stat["records"]) and s.get("abnormal") == str(stat["failed"]),
           f"steps[{sid}] count/abnormal={stat['records']}/{stat['failed']}（实际 {s.get('count')}/{s.get('abnormal')}）")

    # 8. 审核队列：pendingReview（w2 机构名空）+ T_EXTRACT_FAIL（w3 毒行）
    # 队列是共享状态（历史 e2e 留有旧 case），按本次执行 taskId 过滤
    step("8. 审核队列：pendingReview 直发 case + 毒行 T_EXTRACT_FAIL")
    code, resp = req("GET", "/manual-reviews/production/queue?statusGroup=pending&pageSize=100")
    items = (resp.get("data") or {}).get("items") or []
    mine = [i for i in items if i.get("sourceTaskId") == execution.get("taskId")]
    direct = [i for i in mine if i.get("sourceRecordId") == "w2" and i.get("templateId") == "T_DIRECT"]
    ok(len(direct) == 1, f"w2 pendingReview 1 条 T_DIRECT（实际 {len(direct)}）")
    ok("机构名为空" in (direct[0].get("errorType") or ""), "errorType=机构名为空")
    ok((direct[0].get("nodeId") or "").endswith("#resolve"),
       f"nodeId 为 source:{{绑定id}}#resolve 复合观测 id（实际 {direct[0].get('nodeId')}）")
    extract_fail = [
        i for i in mine
        if i.get("sourceRecordId") == "w3" and i.get("templateId") == "T_EXTRACT_FAIL"
    ]
    ok(len(extract_fail) == 1, f"w3 T_EXTRACT_FAIL 1 条（实际 {len(extract_fail)}）")

    # 9. 水位整链推进：再触发读 0 行
    step("9. 水位推进验证：再次触发读取 0 行")
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    execution3 = wait_execution(resp["data"]["id"])
    src3 = (execution3.get("output") or {}).get("sources") or [{}]
    ok(src3 and src3[0].get("rows") == 0, f"第二跑读取 0 行（实际 {src3[0].get('rows') if src3 else '?'}）")

    # 10. 图库验证：w1/w4 入库，w2（pending）/w3（failed）不入库
    step("10. 图库 dev2 空间 E2EStepWidget 节点")
    r2 = urllib.request.Request(
        "http://localhost:8090/api/v1/query/read",
        data=json.dumps({"query": "MATCH (v:E2EStepWidget) RETURN id(v) AS vid LIMIT 20"}).encode(),
        method="POST",
    )
    r2.add_header("X-API-Key", "ysukeg")
    r2.add_header("X-Graph-Space", "dev2")
    r2.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r2, timeout=30) as resp_g:
        graph = json.loads(resp_g.read().decode())
    records = graph.get("data", {}).get("records") or graph.get("records") or []
    vids = {rec.get("vid") for rec in records}
    ok("widget_w1" in vids and "widget_w4" in vids, f"w1/w4 节点入库（{sorted(vids)}）")
    ok("widget_w2" not in vids and "widget_w3" not in vids, f"w2/w3 不入库（{sorted(vids)}）")

    print("\n全部 STEPS E2E 通过 ✔")


if __name__ == "__main__":
    main()
