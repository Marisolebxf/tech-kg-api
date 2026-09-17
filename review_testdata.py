"""lizhou 栈人工审核测试数据生成 + 按钮级验证（review_testdata.py）。

跑法（host）：python3 review_testdata.py [--only setup,r1,...,buttons,open] [--fresh]
前置：lizhou 栈运行中（api 8006 / web 8097），tech-kg-mysql 可 docker exec。

阶段（默认全跑，按序）：
  setup   源表 review_widgets + 实体/关系 Schema + 脚本 + 来源绑定 + 清理历史自家 OPEN case
  r1      基线：3 行不同名 → 3 节点、0 case
  r2a     自动合并对照(rw201) + 灰区前置(rw202/203) + 碰撞前置(rw203) + 挂起(rw204→T_LINK)
  r2b     灰区案(rw205→T_LINK 扣留) + 碰撞案(rw206 写图后 v1 兜底 T_LINK)
  r3      双候选案(rw301 同名两候选 T_LINK)
  r4      关系边端点命中未决案 → parked 暂存（图里无边，快照 _pendingRelations）
  r5      毒行(rw501) → T_EXTRACT_FAIL → 修数 → 重跑成功 → 日志非空 + 原案 RESOLVED
  r6      毒行(rw601) → 重跑仍失败 → attempt+1 新案
  buttons API 层执行按钮：merge(真并入)/create(真写图+补边)/reject(零写入)
  open    重新生成一批 OPEN case 供 8097 页面手动点按钮，输出操作指引

id 全局按插入顺序递增（rw1xx < rw2xx < ... < rwg-*），保证水位 keyset 递增不跳读。
关键批次各带一行唯一名垫行（审测-垫X）：让批内显示名 ≥2，同名召回/碰撞检测按
多元素 IN 查询；setup 建 rw_name_idx 原生索引兜住 pendingReview 单名召回
（Nebula 把单元素 IN 折叠成 ==，无属性索引时 IndexNotFound 建不出挂起案）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "http://localhost:8006/api/v1"
MYSQL_DOCKER = ["docker", "exec", "tech-kg-mysql", "mysql",
                "--default-character-set=utf8mb4", "-uroot", "-pgkx_element"]
GRAPH_DOCKER = ["docker", "exec", "tech-kg-temporal-worker-lizhou",
                "/app/.venv/bin/python", "-c"]
DB = "techkg_e2e_liz"
SPACE = "dev2"
ENTITY_NAME = "ReviewWidget"
RELATION_NAME = "REVIEW_LINKED"
BATCH_SIZE = 10
WEB = "http://localhost:8097"

RESULTS: list[tuple[str, str, str]] = []  # (阶段, PASS/FAIL, 说明)


def req(method, path, body=None):
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
            return e.code, {"error": text}


def sql(statements: str):
    subprocess.run(MYSQL_DOCKER + ["-e", statements], check=True, capture_output=True)


def step(msg):
    print(f"\n=== {msg}")


def ok(cond, msg):
    line = ("PASS" if cond else "FAIL") + " | " + msg
    print("  " + line)
    RESULTS.append((msg.split("（")[0][:40], "PASS" if cond else "FAIL", msg))
    if not cond:
        raise SystemExit(f"造数失败: {msg}")


def info(msg):
    print("  - " + msg)


def wait_execution(execution_id, timeout=240):
    for _ in range(timeout // 3):
        code, resp = req("GET", f"/workflow-system/executions/{execution_id}")
        if code == 200 and resp.get("data", {}).get("status") in (
            "COMPLETED", "FAILED", "TERMINATED", "CANCELED", "TIMED_OUT"
        ):
            return resp["data"]
        time.sleep(3)
    raise SystemExit(f"执行超时未终态: {execution_id}")


# ---------------------------------------------------------------- 审核队列/图

def queue_pending():
    code, resp = req(
        "GET", "/manual-reviews/production/queue?statusGroup=pending&pageSize=200"
    )
    assert code == 200, f"队列查询 {code}: {str(resp)[:120]}"
    return (resp.get("data") or {}).get("items") or []


def ours(item):
    return (
        item.get("sourceTable") == "review_widgets"
        or str(item.get("objectName") or "").startswith("审测")
    )


def find_case(name=None, template=None, record_id=None, object_id=None):
    for item in queue_pending():
        if name and item.get("objectName") != name:
            continue
        if template and item.get("templateId") != template:
            continue
        if record_id and item.get("sourceRecordId") != record_id:
            continue
        if object_id and item.get("objectId") != object_id:
            continue
        return item
    return None


def case_detail(case_id):
    code, resp = req("GET", f"/manual-reviews/production/{case_id}")
    assert code == 200, f"case 详情 {code}: {str(resp)[:120]}"
    return resp["data"]


def submit(case_id, action_id, result=None, note=""):
    detail = case_detail(case_id)
    body = {"version": detail.get("version"), "actionId": action_id, "note": note}
    if result:
        body["result"] = result
    return req("POST", f"/manual-reviews/production/{case_id}/submit", body)


def graph_nodes_by_name(name):
    """按显示名找节点：GET 全量后 Python 过滤（POST /nodes/search 对中文过滤 500，绕开）。"""
    code, resp = req("GET", f"/graph-search/nodes?label={ENTITY_NAME}&space={SPACE}&limit=500")
    if code != 200:
        return []
    items = (resp.get("data") or {}).get("items") or []
    return [n for n in items if (n.get("properties") or {}).get("name") == name]


def graph_node(vid):
    code, resp = req("GET", f"/graph-search/nodes/{vid}?space={SPACE}")
    if code != 200:
        return None
    return resp.get("data")


def graph_edges(vid):
    code, resp = req("GET", f"/graph-search/node/{vid}/edges?space={SPACE}")
    if code != 200:
        return []
    data = resp.get("data") or {}
    return data if isinstance(data, list) else data.get("items") or []


def task_logs(task_id):
    code, resp = req("GET", f"/task-center/tasks/{task_id}")
    if code != 200:
        return []
    return (resp.get("data") or {}).get("logs") or []


# ---------------------------------------------------------------- 转换脚本

ENTITY_SCRIPT = '''"""审测实体转换脚本：按 memo 分流——POISON→failures，PENDING→挂起，EDGE 跳过，其余实体。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures, pending = [], [], []
    for row in rows:
        rid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        memo = str(row.get("memo") or "")
        if "POISON" in memo:
            failures.append({"recordId": rid, "error": "ValueError: POISON 拒绝解析（审测）"})
            continue
        if "PENDING" in memo:
            pending.append({
                "kind": "entity",
                "objectId": f"rwpend-{rid}",
                "objectName": name,
                "nodeLabel": "ReviewWidget",
                "reason": "脚本显式挂起待人工确认（审测）",
                "sourceTable": "review_widgets",
                "sourceRecordId": rid,
                "confidence": 0.55,
            })
            continue
        if "EDGE" in memo:
            continue
        props = {"id": rid, "name": name}
        for col in ("category", "city", "memo"):
            val = row.get(col)
            if val is not None and str(val) != "":
                props[col] = str(val)
        entities.append({"id": rid, "props": props})
    out: dict[str, Any] = {"entities": entities, "failures": failures}
    if pending:
        out["pendingReview"] = pending
    return out
'''

RELATION_SCRIPT = '''"""审测关系转换脚本：EDGE 行输出边（from_id/to_id 列），其余跳过。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    edges = []
    for row in rows:
        memo = str(row.get("memo") or "")
        if "EDGE" not in memo:
            continue
        edges.append({
            "fromId": str(row.get("from_id") or ""),
            "toId": str(row.get("to_id") or ""),
            "props": {"note": str(row.get("name") or "")},
        })
    return {"edges": edges}
'''


# ---------------------------------------------------------------- setup

def setup():
    step("setup.0 准备源表 review_widgets")
    sql(
        f"CREATE DATABASE IF NOT EXISTS {DB}; "
        f"CREATE TABLE IF NOT EXISTS {DB}.review_widgets ("
        "id VARCHAR(64) PRIMARY KEY, name VARCHAR(255), category VARCHAR(64), "
        "city VARCHAR(64), memo VARCHAR(255), from_id VARCHAR(64), to_id VARCHAR(64), "
        "update_time DATETIME); "
        f"DELETE FROM {DB}.review_widgets;"
    )

    step("setup.1 清理历史自家 OPEN case（只动 review_widgets/审测 前缀，不碰他人数据）")
    stale = [i for i in queue_pending() if ours(i)]
    for item in stale:
        code, resp = req("DELETE", f"/manual-reviews/production/{item['id']}")
        ok(code == 200, f"清理旧 case {item['id']} ({item.get('objectName')})")
    info(f"清理 {len(stale)} 条")

    step("setup.2 注册数据源（host.docker.internal:30306）")
    code, resp = req("GET", "/mysql-datasources")
    data = resp.get("data") or []
    items = data.get("items", []) if isinstance(data, dict) else data
    ds = next((i for i in items if i.get("name") == "review-testdata-lizhou"), None)
    if ds is None:
        code, resp = req(
            "POST", "/mysql-datasources",
            {
                "name": "review-testdata-lizhou", "host": "host.docker.internal",
                "port": 30306, "username": "root", "password": "gkx_element",
                "database": DB, "description": "人工审核测试数据",
            },
        )
        ok(code in (200, 201), f"创建数据源 {code}")
        ds = resp["data"]
    datasource_id = ds["id"]
    info(f"datasource={datasource_id}")

    step(f"setup.3 实体 Schema {ENTITY_NAME}（含图 DDL）")
    # 先删引用方（关系），再删实体——实体被关系引用时删除会被拒
    code, resp = req("GET", f"/schema-management/schemas?keyword={RELATION_NAME}&pageSize=100")
    for old_rel_del in (
        i for i in (resp.get("data") or {}).get("items") or [] if i.get("name") == RELATION_NAME
    ):
        code_del, resp_del = req(
            "DELETE", f"/schema-management/schemas/{old_rel_del['id']}"
        )
        ok(code_del == 200, f"删除旧关系 schema {old_rel_del['id']}: {str(resp_del)[:80]}")
    code, resp = req("GET", f"/schema-management/schemas?keyword={ENTITY_NAME}&pageSize=100")
    for old in (
        i for i in (resp.get("data") or {}).get("items") or [] if i.get("name") == ENTITY_NAME
    ):
        # 每次重建：新 schema = 新来源绑定 = 空水位，避免旧水位跳读重插的行
        code_del, resp_del = req("DELETE", f"/schema-management/schemas/{old['id']}")
        ok(code_del == 200, f"删除旧实体 schema {old['id']}: {str(resp_del)[:80]}")
    code, resp = req(
        "POST", "/schema-management/schemas/entities",
        {
            "schemaKey": f"review-widget-{uuid.uuid4().hex[:6]}",
            "name": ENTITY_NAME, "label": "审测挂件", "description": "人工审核测试数据",
            "identityKey": "id",
            "properties": [
                {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
                {"name": "name", "dataType": "string", "required": False, "category": "core", "rule": ""},
                {"name": "category", "dataType": "string", "required": False, "category": "core", "rule": ""},
                {"name": "city", "dataType": "string", "required": False, "category": "core", "rule": ""},
                {"name": "memo", "dataType": "string", "required": False, "category": "core", "rule": ""},
            ],
            "isCore": False, "version": "v1.0", "graphSpace": SPACE,
        },
    )
    ok(code in (200, 201), f"创建实体 schema {code}: {str(resp)[:150]}")
    entity_schema_id = resp["data"]["id"]
    ensure_graph_index()

    step("setup.4 上传实体转换脚本")
    _upload_script(entity_schema_id, ENTITY_SCRIPT)

    step("setup.5 绑定实体来源表")
    code, resp = req(
        "PUT", f"/schema-management/schemas/{entity_schema_id}/sources",
        {"sources": [{
            "datasourceId": datasource_id, "databaseName": DB, "tableName": "review_widgets",
            "pkColumn": "id", "timeColumn": "update_time",
        }]},
    )
    ok(code in (200, 201), f"绑定来源 {code}: {str(resp)[:120]}")

    step(f"setup.6 关系 Schema {RELATION_NAME}")
    code, resp = req("GET", f"/schema-management/schemas?keyword={RELATION_NAME}&pageSize=100")
    old_rel = next(
        (i for i in (resp.get("data") or {}).get("items") or [] if i.get("name") == RELATION_NAME),
        None,
    )
    if old_rel:
        # 同实体：重建以重置水位
        req("DELETE", f"/schema-management/schemas/{old_rel['id']}")
    code, resp = req(
        "POST", "/schema-management/schemas/relations",
        {
            "schemaKey": f"review-linked-{uuid.uuid4().hex[:6]}",
            "name": RELATION_NAME, "label": "审测关联", "description": "人工审核测试数据",
            "identityKey": "id",
            "sourceSchemaId": entity_schema_id, "targetSchemaId": entity_schema_id,
            "relationCategory": "fact",
            "properties": [
                {"name": "note", "dataType": "string", "required": False, "category": "core", "rule": ""},
            ],
            "isCore": False, "version": "v1.0", "graphSpace": SPACE,
        },
    )
    ok(code in (200, 201), f"创建关系 schema {code}: {str(resp)[:150]}")
    relation_schema_id = resp["data"]["id"]

    step("setup.7 上传关系转换脚本 + 绑定来源")
    _upload_script(relation_schema_id, RELATION_SCRIPT)
    code, resp = req(
        "PUT", f"/schema-management/schemas/{relation_schema_id}/sources",
        {"sources": [{
            "datasourceId": datasource_id, "databaseName": DB, "tableName": "review_widgets",
            "pkColumn": "id", "timeColumn": "update_time",
        }]},
    )
    ok(code in (200, 201), f"绑定关系来源 {code}: {str(resp)[:120]}")
    return entity_schema_id, relation_schema_id


def ensure_graph_index():
    """dev2 给 ReviewWidget 建 name 原生索引。

    Nebula 把单元素 IN ["名"] 折叠成 == 等值，等值必须有属性索引——没有它时
    pendingReview 挂起路径的同名召回（单名单独召回）报 IndexNotFound，T_LINK
    挂起案建不出来（多元素 IN 走全表扫描不受影响，所以消歧主路径一直正常）。
    DDL 异步生效，REBUILD 需重试。幂等：IF NOT EXISTS + 重复 REBUILD 无害。
    """
    code = (
        "import time\n"
        "from infra.graph_db.config import TRSGraphSettings\n"
        "from infra.graph_db.client import TRSGraphClient\n"
        "c = TRSGraphClient(TRSGraphSettings.from_env()); c.connect()\n"
        f"c.execute_write('CREATE TAG INDEX IF NOT EXISTS rw_name_idx ON `{ENTITY_NAME}`(name(128))')\n"
        "for _ in range(10):\n"
        "    try:\n"
        "        c.execute_write('REBUILD TAG INDEX rw_name_idx')\n"
        "        print('rebuilt')\n"
        "        break\n"
        "    except Exception:\n"
        "        time.sleep(3)\n"
        "else:\n"
        "    raise SystemExit('REBUILD TAG INDEX 一直失败')\n"
    )
    r = subprocess.run(GRAPH_DOCKER + [code], capture_output=True, text=True)
    ok("rebuilt" in r.stdout,
       f"ReviewWidget name 原生索引就绪（{r.stderr.strip()[:100]}）")


def rebuild_index():
    """REBUILD name 索引并等新任务 FINISHED（按 SHOW JOBS 的 Id 判定，防旧状态假通过）。

    有索引后 IN 查询可能走索引 seek；各轮之间重建一次，保证下一轮工作流内的
    同名召回/碰撞检测能看到上一轮写入。等待逻辑按「提交后出现的新 REBUILD 任务
    达到 FINISHED」判定。
    """
    code = (
        "import time\n"
        "from infra.graph_db.config import TRSGraphSettings\n"
        "from infra.graph_db.client import TRSGraphClient\n"
        "c = TRSGraphClient(TRSGraphSettings.from_env()); c.connect()\n"
        "def job_ids():\n"
        "    out = []\n"
        "    for j in c.execute_read('SHOW JOBS').records or []:\n"
        "        try:\n"
        "            out.append((int(j.get('Job Id')), str(j.get('Command') or ''), str(j.get('Status'))))\n"
        "        except (TypeError, ValueError):\n"
        "            pass\n"
        "    return out\n"
        "prev = max((i for i, _, _ in job_ids()), default=0)\n"
        "c.execute_write('REBUILD TAG INDEX rw_name_idx')\n"
        "for _ in range(30):\n"
        "    time.sleep(1)\n"
        "    jobs = job_ids()\n"
        "    if any(i > prev and 'REBUILD' in cmd and st == 'FINISHED' for i, cmd, st in jobs):\n"
        "        print('finished'); break\n"
        "else:\n"
        "    raise SystemExit('REBUILD 未 FINISHED')\n"
    )
    r = subprocess.run(GRAPH_DOCKER + [code], capture_output=True, text=True)
    ok("finished" in r.stdout, f"name 索引 REBUILD 完成（{r.stderr.strip()[:80]}）")


def _upload_script(schema_id, content):
    script_file = pathlib.Path(f"/tmp/review_testdata_{schema_id[:8]}.py")
    script_file.write_text(content, encoding="utf-8")
    r = subprocess.run(
        ["curl", "-sS", "-m", "120", "-X", "PUT",
         f"{API}/schema-management/schemas/{schema_id}/script",
         "-F", f"script=@{script_file}"],
        capture_output=True, text=True,
    )
    resp = json.loads(r.stdout or "{}")
    ok(resp.get("code", 0) == 200, f"上传脚本 inner={resp.get('code')}: {str(resp)[:150]}")


# ---------------------------------------------------------------- 触发

def trigger(schema_id, label):
    code, resp = req(
        "POST", "/workflow-system/jobs",
        {
            "name": f"审测-{label}-{uuid.uuid4().hex[:6]}", "taskType": "extract",
            "schemaId": schema_id, "schedule": {"kind": "once"},
            "graphSpace": SPACE, "batchSize": BATCH_SIZE,
        },
    )
    ok(code in (200, 201), f"创建任务 {label} {code}: {str(resp)[:150]}")
    job_id = resp["data"]["id"]
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    ok(code in (200, 201), f"触发 {label} {code}: {str(resp)[:120]}")
    return job_id, resp["data"]["id"]


def insert_rows(rows):
    values = ",".join(
        f"('{r[0]}','{r[1]}',{_nn(r[2])},{_nn(r[3])},{_nn(r[4])},{_nn(r[5])},{_nn(r[6])},NOW())"
        for r in rows
    )
    sql(
        f"INSERT INTO {DB}.review_widgets "
        "(id,name,category,city,memo,from_id,to_id,update_time) VALUES "
        + values
        + " ON DUPLICATE KEY UPDATE update_time=NOW();"
    )


def _nn(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


# ---------------------------------------------------------------- 各轮

def r1(entity_schema_id):
    step("r1 基线：3 行不同名 → 3 节点、0 新 case")
    insert_rows([
        ("rw101", "审测-甲", "catA", "北京", None, None, None),
        ("rw102", "审测-乙", "catB", "上海", None, None, None),
        ("rw103", "审测-丙", "catC", "广州", None, None, None),
    ])
    _, exec_id = trigger(entity_schema_id, "r1基线")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r1 执行 COMPLETED（{execution['status']}）")
    rebuild_index()
    ok(len(graph_nodes_by_name("审测-甲")) == 1, "图里 审测-甲 1 个节点")
    ok(len(graph_nodes_by_name("审测-乙")) == 1, "图里 审测-乙 1 个节点")
    ok(find_case(name="审测-甲") is None and find_case(name="审测-乙") is None,
       "r1 无审核 case（不误报）")


def r2a(entity_schema_id):
    step("r2a 自动合并对照 + 灰区/碰撞前置 + 挂起案")
    insert_rows([
        ("rw201", "审测-甲", "catA", "北京", None, None, None),        # 全一致→自动合并不建案
        ("rw202", "审测-灰区", "catX", "深圳", None, None, None),       # 灰区前置节点
        ("rw203", "审测-碰撞", "catY", "杭州", None, None, None),       # 碰撞前置节点
        ("rw204", "审测-挂起", None, None, "PENDING", None, None),      # pendingReview→T_LINK
    ])
    _, exec_id = trigger(entity_schema_id, "r2a")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r2a 执行 COMPLETED（{execution['status']}）")
    rebuild_index()
    ok(len(graph_nodes_by_name("审测-甲")) == 1 and graph_node("rw201") is None,
       "rw201 自动并入 rw101（不新增 vid、不建案）")
    ok(len(graph_nodes_by_name("审测-灰区")) == 1, "灰区前置节点 rw202 已写图")
    case = find_case(name="审测-挂起", template="T_LINK")
    ok(case is not None, "挂起行产生 T_LINK case")
    detail = case_detail(case["id"])
    cand = detail.get("candidate") or {}
    ok(not (cand.get("existingCandidates") or []), "挂起案无同名候选（可 create）")
    ok(case.get("jobId"), f"挂起案 jobId 可溯源（{case.get('jobId')}）")
    code, _ = req("GET", f"/workflow-system/jobs/{case.get('jobId')}")
    ok(code == 200, "jobId 能打开任务详情（来源记录一一对应）")
    return case


def r2b(entity_schema_id):
    step("r2b 灰区案（0.80 扣留）+ 碰撞案（写后兜底）")
    insert_rows([
        ("rw205", "审测-灰区", None, None, "灰区补充备注", None, None),  # 无可比属性→0.80 灰区
        ("rw206", "审测-碰撞", "catZ", "南京", None, None, None),       # 全冲突→新实体→写后碰撞
        # 垫名行：让批内显示名 ≥2，同名召回/碰撞检测走多元素 IN 全表扫描——
        # Nebula 单元素 IN 被折叠成 == 走属性索引，而新写行的索引增量不稳定
        ("rw2fa", "审测-垫A", None, None, None, None, None),
    ])
    _, exec_id = trigger(entity_schema_id, "r2b")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r2b 执行 COMPLETED（{execution['status']}）")
    rebuild_index()
    gray = find_case(name="审测-灰区", template="T_LINK")
    ok(gray is not None, "灰区行产生 T_LINK case")
    ok(graph_node("rw205") is None, "灰区记录被扣留未写图（裁决后才落图）")
    detail = case_detail(gray["id"])
    cand = detail.get("candidate") or {}
    cands = cand.get("existingCandidates") or []
    ok(len(cands) == 1 and cands[0].get("vid") == "rw202",
       f"灰区案候选=rw202（实际 {cands}）")
    ok("0.8" in str(detail.get("diagnosis") or ""), f"诊断含得分 0.80（{detail.get('diagnosis')}）")
    # object_id 精确定位：同名 T_LINK 可能有多案（灰区扣留案 object_id=被扣 vid，
    # 碰撞兜底案 object_id=本批首个新 vid），按名字找会撞错
    coll = find_case(name="审测-碰撞", template="T_LINK", object_id="rw206")
    ok(coll is not None, "冲突行写图后 v1 兜底产生碰撞 T_LINK case")
    ok(graph_node("rw206") is not None, "rw206 判新实体已写图（碰撞案=存量写后语义）")
    return gray, coll


def r3(entity_schema_id):
    step("r3 双候选案")
    insert_rows([
        ("rw301", "审测-碰撞", None, None, None, None, None),  # 无可比属性 vs 两个同名节点
        ("rw3f1", "审测-垫B", None, None, None, None, None),   # 垫名行（同 r2b 理由）
    ])
    _, exec_id = trigger(entity_schema_id, "r3双候选")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r3 执行 COMPLETED（{execution['status']}）")
    rebuild_index()
    case = find_case(name="审测-碰撞", template="T_LINK", object_id="rw301")
    ok(case is not None, "双候选行产生 T_LINK case")
    detail = case_detail(case["id"])
    cands = (detail.get("candidate") or {}).get("existingCandidates") or []
    ok({c.get("vid") for c in cands} == {"rw203", "rw206"},
       f"候选集含两个同名 vid（实际 {cands}）")
    ok(graph_node("rw301") is None, "rw301 扣留未写图")
    return case


def r4(entity_schema_id, relation_schema_id):
    step("r4 关系边端点命中未决挂起案 → parked 暂存")
    insert_rows([
        ("rw401", "审测-暂存边", None, None, "EDGE", "rwpend-rw204", "rw101"),
    ])
    _, exec_id = trigger(relation_schema_id, "r4关系")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r4 执行 COMPLETED（{execution['status']}）")
    ok(graph_node("rwpend-rw204") is None, "挂起 vid 尚未落图（case 未裁决）")
    rw101_edges = graph_edges("rw101")
    ok(not any("rwpend-rw204" in json.dumps(e, ensure_ascii=False) for e in rw101_edges),
       "暂存边未写图（等裁决补写）")
    case = find_case(name="审测-挂起", template="T_LINK")
    detail = case_detail(case["id"])
    cand = detail.get("candidate") or {}
    parked = cand.get("_pendingRelations") or []
    ok(len(parked) == 1 and parked[0].get("fromId") == "rwpend-rw204",
       f"边进快照 _pendingRelations（实际 {parked}）")
    return case


def r5(entity_schema_id):
    step("r5 毒行 → T_EXTRACT_FAIL → 修数重跑成功 → 日志非空")
    insert_rows([("rw501", "审测-毒甲", None, None, "POISON", None, None)])
    _, exec_id = trigger(entity_schema_id, "r5毒行")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r5 执行 COMPLETED（{execution['status']}）")
    case = find_case(template="T_EXTRACT_FAIL", record_id="rw501")
    ok(case is not None, "毒行产生 T_EXTRACT_FAIL case")
    ok(case.get("jobId"), f"失败案 jobId 可溯源（{case.get('jobId')}）")
    info("修数：memo POISON → FIXED")
    sql(f"UPDATE {DB}.review_widgets SET memo='FIXED' WHERE id='rw501';")
    code, resp = req("POST", "/manual-reviews/production/rerun-extract-failures",
                     {"caseIds": [case["id"]]})
    ok(code in (200, 201), f"重跑下发 {code}: {str(resp)[:150]}")
    rerun_exec = resp["data"]["executions"][0]["executionId"]
    execution2 = wait_execution(rerun_exec)
    ok(execution2["status"] == "COMPLETED", f"重跑执行 COMPLETED（{execution2['status']}）")
    ok(execution2.get("triggerSource") == "RERUN", "重跑 triggerSource=RERUN")
    logs = task_logs(execution2.get("taskId"))
    ok(any("重跑范围：1 条失败记录（1 个来源）" in ln for ln in logs),
       "任务日志含「重跑范围：1 条失败记录（1 个来源）」")
    ok(any(ln.startswith("来源 ") for ln in logs), "任务日志含逐来源统计行")
    time.sleep(2)
    ok(case_detail(case["id"]).get("status") == "RESOLVED", "原案自动 RESOLVED")
    ok(graph_node("rw501") is not None, "修数重跑后 rw501 落图")


def r6(entity_schema_id):
    step("r6 毒行重跑仍失败 → attempt+1 新案")
    insert_rows([("rw601", "审测-毒乙", None, None, "POISON", None, None)])
    _, exec_id = trigger(entity_schema_id, "r6毒行2")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"r6 执行 COMPLETED（{execution['status']}）")
    case = find_case(template="T_EXTRACT_FAIL", record_id="rw601")
    ok(case is not None, "毒行产生 T_EXTRACT_FAIL case")
    code, resp = req("POST", "/manual-reviews/production/rerun-extract-failures",
                     {"caseIds": [case["id"]]})
    ok(code in (200, 201), f"重跑下发 {code}")
    rerun_exec = resp["data"]["executions"][0]["executionId"]
    execution2 = wait_execution(rerun_exec)
    logs = task_logs(execution2.get("taskId"))
    ok(any("重跑范围" in ln for ln in logs), "仍失败重跑的日志也非空")
    time.sleep(2)
    ok(case_detail(case["id"]).get("status") == "RESOLVED", "原案 RESOLVED")
    new_case = find_case(template="T_EXTRACT_FAIL", record_id="rw601")
    ok(new_case is not None and new_case["id"] != case["id"],
       "仍失败生成 attempt+1 新案（OPEN）")
    return new_case


def buttons(gray_case, pending_case, dual_case, coll_case):
    step("buttons.1 T_LINK merge：真实并入目标实体")
    code, resp = submit(gray_case["id"], "entity-confirm",
                        {"entityVerdict": "merge", "targetEntityId": "rw202"},
                        note="审测-并入rw202")
    ok(code == 200, f"merge 提交 {code}: {str(resp)[:150]}")
    node = graph_node("rw202")
    props = (node or {}).get("properties") or {}
    ok(props.get("memo") == "灰区补充备注",
       f"rw202 获得扣留记录属性 memo=灰区补充备注（实际 {props.get('memo')}）")
    ok(graph_node("rw205") is None, "merge 不产生新 vid")
    ok(case_detail(gray_case["id"]).get("status") == "RESOLVED", "灰区案 RESOLVED")

    step("buttons.2 T_LINK create：真实写图 + 暂存边补写")
    code, resp = submit(pending_case["id"], "entity-confirm",
                        {"entityVerdict": "create"}, note="审测-新建挂起实体")
    ok(code == 200, f"create 提交 {code}: {str(resp)[:150]}")
    node = graph_node("rwpend-rw204")
    ok(node is not None, "挂起实体按预留 vid 落图")
    edges = graph_edges("rwpend-rw204")
    linked = [e for e in edges if RELATION_NAME in json.dumps(e, ensure_ascii=False)]
    ok(len(linked) >= 1, f"暂存边补写：REVIEW_LINKED 边已落图（实际 {edges}）")
    ok(case_detail(pending_case["id"]).get("status") == "RESOLVED", "挂起案 RESOLVED")

    step("buttons.3 T_LINK reject：零写入")
    code, resp = submit(dual_case["id"], "reject-candidate", note="审测-驳回")
    ok(code == 200, f"reject 提交 {code}: {str(resp)[:150]}")
    ok(graph_node("rw301") is None, "驳回后图中无 rw301（零写入）")
    ok(case_detail(dual_case["id"]).get("status") == "REJECTED", "双候选案 REJECTED")

    step("buttons.4 碰撞案(存量写后) merge：只记决策、不再改图")
    code, resp = submit(coll_case["id"], "entity-confirm",
                        {"entityVerdict": "merge", "targetEntityId": "rw203"},
                        note="审测-存量并入rw203")
    ok(code == 200, f"存量 merge 提交 {code}: {str(resp)[:150]}")
    ok(graph_node("rw206") is not None, "存量案无 _incoming：rw206 节点保持独立（决策已落库）")
    ok(case_detail(coll_case["id"]).get("status") == "RESOLVED", "碰撞案 RESOLVED")


def open_cases(entity_schema_id):
    step("open 生成手动测试 OPEN case")
    run = uuid.uuid4().hex[:6]
    insert_rows([
        (f"rwg-{run}", "审测-灰区", None, None, None, None, None),
        (f"rwp-{run}", "审测-挂起2", None, None, "PENDING", None, None),
        (f"rwx-{run}", "审测-毒丙", None, None, "POISON", None, None),
        (f"rwf-{run}", "审测-垫C", None, None, None, None, None),  # 垫名行（同 r2b 理由）
    ])
    _, exec_id = trigger(entity_schema_id, "open")
    execution = wait_execution(exec_id)
    ok(execution["status"] == "COMPLETED", f"open 执行 COMPLETED（{execution['status']}）")
    gray = find_case(name="审测-灰区", template="T_LINK")
    pend = find_case(name="审测-挂起2", template="T_LINK")
    fail = find_case(template="T_EXTRACT_FAIL", record_id=f"rwx-{run}")
    ok(gray is not None, "手测灰区案 OPEN")
    ok(pend is not None, "手测挂起案 OPEN")
    ok(fail is not None, "手测失败案 OPEN")

    print(f"""
================ 手动测试指引（web {WEB} 运维中心·审核队列）================
案 1 灰区裁决 {gray['id']}  对象「审测-灰区」
    按钮「通过/确认」(merge)：选候选 rw202 → 预期 rw202 节点属性被补写，不出现新 vid
    按钮「新建」(create)  ：预期图中出现新 vid（扣留记录落图）
    按钮「驳回」          ：预期图零变化，案 REJECTED
案 2 挂起裁决 {pend['id']}  对象「审测-挂起2」
    「新建」→ 图中出现 rwpend-rwp-{run} 节点；「驳回」→ 零写入
案 3 失败重跑 {fail['id']}  记录 rwx-{run}「审测-毒丙」
    先修数：docker exec tech-kg-mysql mysql -uroot -pgkx_element -e \\
      "UPDATE {DB}.review_widgets SET memo='FIXED' WHERE id='rwx-{run}';"
    再点「重跑」→ 任务详情日志出现「重跑范围：1 条失败记录（1 个来源）」+ 逐来源统计，案 RESOLVED
    （不修数直接重跑 → 验证 attempt+1 新案，日志同样非空）
来源记录列：每案点 jobId 链接 → /graph-build/jobs/{{jobId}} 任务详情可打开（执行历史非空）
=========================================================================""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="setup,r1,r2a,r2b,r3,r4,r5,r6,buttons,open",
                        help="逗号分隔阶段")
    args = parser.parse_args()
    phases = [p.strip() for p in args.only.split(",")]

    entity_id = relation_id = None
    if "setup" in phases:
        entity_id, relation_id = setup()
    else:
        code, resp = req("GET", f"/schema-management/schemas?keyword={ENTITY_NAME}&pageSize=100")
        entity_id = next(
            (i["id"] for i in (resp.get("data") or {}).get("items") or []
             if i.get("name") == ENTITY_NAME), None)
        code, resp = req("GET", f"/schema-management/schemas?keyword={RELATION_NAME}&pageSize=100")
        relation_id = next(
            (i["id"] for i in (resp.get("data") or {}).get("items") or []
             if i.get("name") == RELATION_NAME), None)
        assert entity_id and relation_id, "Schema 未就绪，先跑 setup"

    gray = pend = dual = coll = None
    if "r1" in phases:
        r1(entity_id)
    if "r2a" in phases:
        pend = r2a(entity_id)
    if "r2b" in phases:
        gray, coll = r2b(entity_id)
    if "r3" in phases:
        dual = r3(entity_id)
    if "r4" in phases:
        r4(entity_id, relation_id)
    if "r5" in phases:
        r5(entity_id)
    if "r6" in phases:
        r6(entity_id)
    if "buttons" in phases:
        assert gray and pend and dual and coll, "buttons 需要 r2a/r2b/r3 先产出 case"
        buttons(gray, pend, dual, coll)
    if "open" in phases:
        open_cases(entity_id)

    print("\n===== 结果汇总 =====")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"PASS {passed} / {len(RESULTS)}")
    for _, s, m in RESULTS:
        print(f"  {s} | {m}")


if __name__ == "__main__":
    sys.exit(main())
