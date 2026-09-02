"""dev2 端到端验证：批次抽取 → 毒行失败 → 审核 case → 重跑（重新执行）→ 自动关闭。

跑法（host）：python3 dev2_extract_e2e.py
前置：tech-kg-api-dev2 运行中（8002），temporal-mysql-dev2 里有 techkg_e2e.widgets
（含 2 行 POISON）。脚本幂等，可重复跑。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid

API = "http://localhost:8002/api/v1"
MYSQL = "host=temporal-mysql-dev2"


def req(method: str, path: str, body=None, headers: dict | None = None, raw: bytes | None = None):
    url = path if path.startswith("http") else API + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
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


SCRIPT = '''"""E2E 毒行转换脚本：POISON 行报 failures，其余出实体。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        name = str(row.get("name") or "")
        if "POISON" in name:
            failures.append({"recordId": str(row["id"]), "error": "ValueError: POISON 行拒绝解析"})
        else:
            entities.append({"id": "widget_" + str(row["id"]), "props": {"id": str(row["id"]), "name": name}})
    return {"entities": entities, "failures": failures}
'''


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

    # 重置测试数据（幂等重跑）：w3/w4 恢复毒行标记
    import subprocess as _sp
    _sp.run(
        ["docker", "exec", "tech-kg-temporal-mysql-dev2", "mysql", "-uroot", "-ptemporal", "-e",
         "UPDATE techkg_e2e.widgets SET name='POISON坏行', update_time=NOW() WHERE id='w3'; "
         "UPDATE techkg_e2e.widgets SET name='POISON又坏', update_time=NOW() WHERE id='w4';"],
        check=True, capture_output=True,
    )

    # 1. 数据源
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
            "POST",
            "/mysql-datasources",
            {
                "name": f"e2e-extract-{run}",
                "host": "temporal-mysql-dev2",
                "port": 3306,
                "username": "root",
                "password": "temporal",
                "database": "techkg_e2e",
                "description": "抽取 e2e",
            },
        )
        ok(code in (200, 201), f"创建数据源 {code}")
        ds = resp["data"]
    datasource_id = ds["id"]
    print(f"  datasource={datasource_id}")

    # 2. schema（幂等：删旧建新）
    step("2. 创建实体 Schema E2EWidget（自动执行图 DDL 建 tag）")
    code, resp = req("GET", "/schema-management/schemas?limit=200")
    old = next(
        (i for i in resp["data"]["items"] if i.get("name") == "E2EWidget"), None
    )
    if old:
        req("DELETE", f"/schema-management/schemas/{old['id']}")
    code, resp = req(
        "POST",
        "/schema-management/schemas/entities",
        {
            "schemaKey": f"e2e-widget-{run}",
            "name": "E2EWidget",
            "label": "E2E挂件",
            "description": "抽取 e2e",
            "identityKey": "id",
            "properties": [
                {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
                {"name": "name", "dataType": "string", "required": False, "category": "core", "rule": ""},
            ],
            "isCore": False,
            "version": "v1.0",
        },
    )
    ok(code in (200, 201), f"创建 schema {code}: {str(resp)[:150]}")
    schema_id = resp["data"]["id"]

    # 3. 上传脚本（transform 入口）
    step("3. 上传 transform 抽取脚本")
    import pathlib
    import subprocess

    script_file = pathlib.Path(f"/tmp/e2e_widget_{run}.py")
    script_file.write_text(SCRIPT, encoding="utf-8")
    r = subprocess.run(
        [
            "curl", "-sS", "-m", "60", "-X", "PUT",
            f"{API}/schema-management/schemas/{schema_id}/script",
            "-F", f"script=@{script_file}",
        ],
        capture_output=True,
        text=True,
    )
    resp = json.loads(r.stdout or "{}")
    inner = resp.get("code", 0)
    ok(inner == 200, f"上传脚本 inner={inner}: {str(resp)[:150]}")

    # 4. 绑定来源
    step("4. 绑定来源表 widgets（pk=id, time=update_time）")
    code, resp = req(
        "PUT",
        f"/schema-management/schemas/{schema_id}/sources",
        {
            "sources": [
                {
                    "datasourceId": datasource_id,
                    "databaseName": "techkg_e2e",
                    "tableName": "widgets",
                    "pkColumn": "id",
                    "timeColumn": "update_time",
                }
            ]
        },
    )
    ok(code in (200, 201), f"绑定来源 {code}: {str(resp)[:150]}")

    # 5. 建抽取任务（once）并触发
    step("5. 创建数据抽取任务（taskType=extract）并触发")
    code, resp = req(
        "POST",
        "/workflow-system/jobs",
        {
            "name": f"e2e抽取-{run}",
            "taskType": "extract",
            "schemaId": schema_id,
            "schedule": {"kind": "once"},
            "graphSpace": "dev2",
            "batchSize": 2,  # 4 行 → 2 批，验证分批
        },
    )
    ok(code in (200, 201), f"创建任务 {code}: {str(resp)[:200]}")
    job_id = resp["data"]["id"]
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    ok(code in (200, 201), f"触发 {code}: {str(resp)[:150]}")
    exec1 = resp["data"]["id"]
    print(f"  job={job_id} execution={exec1} triggerSource={resp['data'].get('triggerSource')}")
    ok(resp["data"].get("triggerSource") == "MANUAL", "执行 triggerSource=MANUAL")

    execution = wait_execution(exec1)
    out = execution.get("output") or {}
    ok(execution["status"] == "COMPLETED", f"执行 COMPLETED（{execution['status']} {str(execution.get('message'))[:120]}）")
    failures = out.get("failures") or {}
    ok(failures.get("count") == 2, f"失败记录数=2（实际 {failures.get('count')}）")
    sources = (out.get("sources") or [{}])[0]
    ok(sources.get("rows") == 4 and sources.get("batches") == 2, f"读取 4 行 / 2 批（实际 {sources.get('rows')}/{sources.get('batches')}）")
    ok(sources.get("written") == 2, f"写图 2 实体（实际 {sources.get('written')}）")

    # 6. 审核队列 category=C
    step("6. 人工审核队列（category=C）出现 2 条抽取失败")
    code, resp = req("GET", "/manual-reviews/production/queue?category=C&statusGroup=pending&pageSize=50")
    items = resp["data"]["items"]
    ok(code == 200 and len(items) == 2, f"2 条 T_EXTRACT_FAIL case（实际 {len(items)}）")
    ok(all(i["templateId"] == "T_EXTRACT_FAIL" for i in items), "templateId=T_EXTRACT_FAIL")
    ok({i["sourceRecordId"] for i in items} == {"w3", "w4"}, "记录 id = w3/w4")
    case_ids = [i["id"] for i in items]

    # 7. 修数据 + 重跑
    step("7. 修复毒行数据后，按 case 批量重跑")
    import subprocess
    subprocess.run(
        ["docker", "exec", "tech-kg-temporal-mysql-dev2", "mysql", "-uroot", "-ptemporal", "-e",
         "UPDATE techkg_e2e.widgets SET name='修复好的行', update_time=update_time WHERE id IN ('w3','w4');"],
        check=True, capture_output=True,
    )
    code, resp = req("POST", "/manual-reviews/production/rerun-extract-failures", {"caseIds": case_ids})
    ok(code in (200, 201), f"重跑下发 {code}: {str(resp)[:200]}")
    exec2 = resp["data"]["executions"][0]["executionId"]
    ok(resp["data"]["cases"] == 2, "合并为 1 个新执行、2 条记录")

    execution2 = wait_execution(exec2)
    ok(execution2["status"] == "COMPLETED", f"重跑执行 COMPLETED（{execution2['status']}）")
    ok(execution2.get("triggerSource") == "RERUN", f"重跑 triggerSource=RERUN（实际 {execution2.get('triggerSource')}）")
    ok((execution2.get("output") or {}).get("failures", {}).get("count") == 0, "重跑后 0 失败")
    rerun_out = (execution2.get("output") or {}).get("rerun") or {}
    print(f"  rerun={rerun_out}")

    # 8. case 自动关闭
    step("8. 原 case 自动关闭（RERUN_SUCCEEDED）")
    time.sleep(2)
    code, resp = req("GET", f"/manual-reviews/production/{case_ids[0]}")
    ok(resp["data"]["status"] == "RESOLVED", f"case 状态 RESOLVED（实际 {resp['data']['status']}）")
    code, resp = req("GET", "/manual-reviews/production/queue?category=C&statusGroup=pending&pageSize=50")
    ok(not resp["data"]["items"], "C 队列无待处理")

    # 9. 任务执行历史：两条执行、类别正确
    step("9. 任务详情执行历史：MANUAL + RERUN 同列展示")
    code, resp = req("GET", f"/workflow-system/jobs/{job_id}")
    execs = resp["data"]["executions"]
    by_id = {e["id"]: e.get("triggerSource") for e in execs}
    ok(by_id.get(exec1) == "MANUAL", f"首执行=MANUAL（{by_id.get(exec1)}）")
    ok(by_id.get(exec2) == "RERUN", f"重跑执行=RERUN（{by_id.get(exec2)}）")
    ok(len(execs) >= 2, f"执行历史 {len(execs)} 条")

    # 10. 水位：再次触发应读 0 行（全部已推进）
    step("10. 水位推进验证：再次触发读取 0 行")
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    exec3 = resp["data"]["id"]
    execution3 = wait_execution(exec3)
    src3 = (execution3.get("output") or {}).get("sources") or [{}]
    ok(src3 and src3[0].get("rows") == 0, f"第二跑读取 0 行（实际 {src3[0].get('rows') if src3 else '?'}）")

    # 11. 图库验证
    step("11. 图库 dev2 空间 E2EWidget 节点")
    import urllib.request as _u
    r = _u.Request(
        "http://localhost:8090/api/v1/query/read",
        data=json.dumps({"query": "MATCH (v:E2EWidget) RETURN id(v) AS vid, v.name AS nm LIMIT 10"}).encode(),
        method="POST",
    )
    r.add_header("X-API-Key", "ysukeg")
    r.add_header("X-Graph-Space", "dev2")
    r.add_header("Content-Type", "application/json")
    with _u.urlopen(r, timeout=30) as resp_g:
        graph = json.loads(resp_g.read().decode())
    records = graph.get("data", {}).get("records") or graph.get("records") or []
    vids = {rec.get("vid") for rec in records}
    ok({"widget_w1", "widget_w2", "widget_w3", "widget_w4"} <= vids, f"4 个节点入库（{sorted(vids)}）")

    print("\n全部 E2E 通过 ✔")


if __name__ == "__main__":
    main()
