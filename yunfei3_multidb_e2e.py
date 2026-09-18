"""多数据源抽取 e2e：从两个非默认 MySQL 库（不同实例）抽实体入 yunfei_test。

- 库 A：yunfei3-test-mysql(宿主 33306).kg_source_a.patents（专利）
- 库 B：tech-kg-mysql(宿主 30306).kg_source_b.orgs（机构，业务实例上的独立新库）
跑法（host）：python3 yunfei3_multidb_e2e.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

API = "http://localhost:8004/api/v1"
GRAPH = "http://localhost:8090/api/v1/query/read"
SPACE = "yunfei_test"
RUN = uuid.uuid4().hex[:6]

PATENT_SCRIPT = '''"""专利实体抽取（kg_source_a.patents）。"""
from typing import Any, Mapping

from kg_sdk import step


@step
def emit_patent(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        pid = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not pid or not title:
            failures.append({"recordId": pid, "error": "ValueError: 缺少 id 或标题"})
            continue
        entities.append({
            "id": "patent_" + pid,
            "props": {
                "id": pid,
                "title": title,
                "applicant": str(row.get("applicant") or ""),
                "apply_year": int(row.get("apply_year") or 0),
            },
        })
    return {"entities": entities, "failures": failures}
'''

ORG_SCRIPT = '''"""机构实体抽取（kg_source_b.orgs）。"""
from typing import Any, Mapping

from kg_sdk import step


@step
def emit_org(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        oid = str(row.get("id") or "").strip()
        name = str(row.get("name") or "").strip()
        if not oid or not name:
            failures.append({"recordId": oid, "error": "ValueError: 缺少 id 或机构名"})
            continue
        entities.append({
            "id": "org_" + oid,
            "props": {"id": oid, "name": name, "city": str(row.get("city") or "")},
        })
    return {"entities": entities, "failures": failures}
'''

SQL_A = """
CREATE DATABASE IF NOT EXISTS kg_source_a DEFAULT CHARACTER SET utf8mb4;
USE kg_source_a;
DROP TABLE IF EXISTS patents;
CREATE TABLE patents (
  id VARCHAR(32) NOT NULL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  applicant VARCHAR(128) NOT NULL,
  apply_year INT NOT NULL,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
INSERT INTO patents (id, title, applicant, apply_year) VALUES
  ('pa1', '一种知识图谱构建方法', '甲科技', 2024),
  ('pa2', '基于图神经网络的实体对齐装置', '乙智能', 2025),
  ('pa3', '多源异构数据融合系统', '丙数据', 2023);
"""

SQL_B = """
CREATE DATABASE IF NOT EXISTS kg_source_b DEFAULT CHARACTER SET utf8mb4;
USE kg_source_b;
DROP TABLE IF EXISTS orgs;
CREATE TABLE orgs (
  id VARCHAR(32) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  city VARCHAR(64) NOT NULL,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
INSERT INTO orgs (id, name, city) VALUES
  ('o1', '甲科技有限公司', '北京'),
  ('o2', '乙智能装备有限公司', '上海'),
  ('o3', '丙数据服务有限公司', '深圳'),
  ('o4', '丁研究院', '合肥');
"""


def sh(cmd: list[str]) -> None:
    import subprocess
    subprocess.run(cmd, check=True, capture_output=True)


def req(method: str, path: str, body=None, raw_file=None) -> tuple[int, Any]:
    import http.client
    from urllib.parse import urlparse
    url = path if path.startswith("http") else API + path
    if raw_file:
        import subprocess
        r = subprocess.run(
            ["curl", "-sS", "-m", "60", "-X", "PUT", url, "-F", f"script=@{raw_file}"],
            capture_output=True, text=True,
        )
        try:
            return 200, json.loads(r.stdout)
        except Exception:
            return 500, r.stdout[:200]
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, text


def graph(query: str) -> list[dict]:
    r = urllib.request.Request(GRAPH, data=json.dumps({"query": query}).encode(), method="POST")
    r.add_header("X-API-Key", "ysukeg")
    r.add_header("X-Graph-Space", SPACE)
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode()).get("data", {}).get("records") or []


def ok(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        raise SystemExit(f"失败: {msg}")


def wait_exec(execution_id: str) -> dict:
    for _ in range(60):
        code, resp = req("GET", f"/workflow-system/executions/{execution_id}")
        if code == 200 and resp.get("data", {}).get("status") in (
            "COMPLETED", "FAILED", "TERMINATED", "CANCELED", "TIMED_OUT"
        ):
            return resp["data"]
        time.sleep(3)
    raise SystemExit("执行超时")


def main():
    print(f"=== 1. 两个实例建库造数（run={RUN}）")
    sh(["docker", "exec", "yunfei3-test-mysql", "mysql", "--default-character-set=utf8mb4",
        "-uroot", "-ptemporal", "-e", SQL_A])
    sh(["docker", "exec", "tech-kg-mysql", "mysql", "--default-character-set=utf8mb4",
        "-uroot", "-pgkx_element", "-e", SQL_B])
    print("  kg_source_a.patents(33306) / kg_source_b.orgs(30306) 就绪")

    print("=== 2. 注册两个非默认数据源")
    ds_specs = [
        ("multidb-a-33306", "host.docker.internal", 33306, "root", "temporal", "kg_source_a"),
        ("multidb-b-30306", "host.docker.internal", 30306, "root", "gkx_element", "kg_source_b"),
    ]
    ds_ids: dict[str, str] = {}
    code, resp = req("GET", "/mysql-datasources")
    data = resp.get("data") or []
    items = data.get("items", data) if isinstance(data, dict) else data
    existing = {i["name"]: i["id"] for i in items}
    for name, host, port, user, pwd, db in ds_specs:
        if name in existing:
            ds_ids[name] = existing[name]
            print(f"  复用数据源 {name} = {existing[name]}")
            continue
        code, resp = req("POST", "/mysql-datasources", {
            "name": name, "host": host, "port": port,
            "username": user, "password": pwd, "database": db,
            "description": f"多数据源 e2e {RUN}",
        })
        ok(code in (200, 201), f"创建数据源 {name}: {str(resp)[:120]}")
        ds_ids[name] = resp["data"]["id"]
    print(" ", ds_ids)

    print("=== 3. 建实体 Schema（Patent/Org，graphSpace=yunfei_test）")

    def ensure_schema(name: str, label: str, props: list[dict], script: str, tag: str) -> str:
        code, resp = req("GET", f"/schema-management/schemas?keyword={name}&pageSize=50")
        for item in resp.get("data", {}).get("items") or []:
            if item.get("name") == name and item.get("graphSpace") == SPACE:
                print(f"  复用 schema {name}")
                req("PUT", f"/schema-management/schemas/{item['id']}/script", raw_file=_write_script(script, tag))
                return item["id"]
        code, resp = req("POST", "/schema-management/schemas/entities", {
            "schemaKey": f"multidb-{name.lower()}-{RUN}",
            "name": name, "label": label,
            "description": f"多数据源 e2e {label}",
            "identityKey": "id", "properties": props,
            "isCore": False, "version": "v1.0", "graphSpace": SPACE,
        })
        ok(code in (200, 201), f"创建 schema {name}: {str(resp)[:150]}")
        req("PUT", f"/schema-management/schemas/{resp['data']['id']}/script", raw_file=_write_script(script, tag))
        return resp["data"]["id"]

    patent_id = ensure_schema("Patent", "专利", [
        {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
        {"name": "title", "dataType": "string", "required": True, "category": "core", "rule": ""},
        {"name": "applicant", "dataType": "string", "required": False, "category": "core", "rule": ""},
        {"name": "apply_year", "dataType": "int64", "required": False, "category": "core", "rule": ""},
    ], PATENT_SCRIPT, "patent")
    org_id = ensure_schema("Org", "机构", [
        {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
        {"name": "name", "dataType": "string", "required": True, "category": "core", "rule": ""},
        {"name": "city", "dataType": "string", "required": False, "category": "core", "rule": ""},
    ], ORG_SCRIPT, "org")
    print(f"  Patent={patent_id} Org={org_id}")

    print("=== 4. 绑定来源（各指向自己的非默认库）")
    for schema_id, ds_name, table in (
        (patent_id, "multidb-a-33306", "patents"),
        (org_id, "multidb-b-30306", "orgs"),
    ):
        code, resp = req("PUT", f"/schema-management/schemas/{schema_id}/sources", {
            "sources": [{
                "datasourceId": ds_ids[ds_name],
                "databaseName": "kg_source_a" if "a-33306" in ds_name else "kg_source_b",
                "tableName": table,
                "pkColumn": "id",
                "timeColumn": "update_time",
            }]
        })
        ok(code in (200, 201), f"绑定 {table} → {ds_name}")

    print("=== 5. 建任务并触发")
    for schema_id, label in ((patent_id, "专利"), (org_id, "机构")):
        code, resp = req("POST", "/workflow-system/jobs", {
            "name": f"多数据源{label}抽取-{RUN}",
            "taskType": "extract", "schemaId": schema_id,
            "schedule": {"kind": "once"}, "graphSpace": SPACE, "batchSize": 2,
        })
        ok(code in (200, 201), f"创建任务 {label}: {str(resp)[:120]}")
        job_id = resp["data"]["id"]
        code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
        ok(code in (200, 201), f"触发 {label}")
        execution = wait_exec(resp["data"]["id"])
        ok(execution["status"] == "COMPLETED",
           f"{label} COMPLETED（{execution['status']} {str(execution.get('message'))[:100]}）")
        src = (execution.get("output") or {}).get("sources") or [{}]
        print(f"  rows={src[0].get('rows')} written={src[0].get('written')} source_table={src[0].get('table')}")

    print("=== 6. 图库验证")
    # FETCH 立即可见（主断言）；MATCH 扫描依赖 Nebula 心跳传播，本环境需数分钟，
    # 仅作最佳努力附加检查（不阻塞）
    def fetch_vid(tag: str, vid: str) -> dict | None:
        import urllib.error
        r = urllib.request.Request(
            GRAPH,
            data=json.dumps({"query": f'FETCH PROP ON {tag} "{vid}" YIELD vertex AS v'}).encode(),
            method="POST",
        )
        r.add_header("X-API-Key", "ysukeg")
        r.add_header("X-Graph-Space", SPACE)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                records = json.loads(resp.read().decode()).get("records") or []
                if not records:
                    return None
                vertex = records[0].get("v") or {}
                return vertex.get("properties") or None
        except Exception:
            return None

    patent_props = {vid: fetch_vid("Patent", vid) for vid in ("patent_pa1", "patent_pa2", "patent_pa3")}
    ok(all(patent_props.values()), f"Patent 3 节点入库（{sorted(patent_props)}）")
    ok(patent_props["patent_pa1"].get("applicant") == "甲科技", "Patent 属性正确")
    ok(patent_props["patent_pa1"].get("source_table") == "kg_source_a.patents",
       f"溯源 source_table={patent_props['patent_pa1'].get('source_table')}（实例 33306/kg_source_a）")

    org_props = {vid: fetch_vid("Org", vid) for vid in ("org_o1", "org_o2", "org_o3", "org_o4")}
    ok(all(org_props.values()), f"Org 4 节点入库（{sorted(org_props)}）")
    ok(org_props["org_o4"].get("city") == "合肥", "Org 属性正确")
    ok(org_props["org_o1"].get("source_table") == "kg_source_b.orgs",
       f"溯源 source_table={org_props['org_o1'].get('source_table')}（实例 30306/kg_source_b）")

    for _ in range(30):
        try:
            if graph("MATCH (v:Patent) RETURN id(v) AS vid LIMIT 20"):
                print("  MATCH 扫描已可见（Nebula 传播完成）")
                break
        except Exception:
            pass
        time.sleep(10)

    print("\n多数据源 e2e 全部通过 ✔")


def _write_script(content: str, tag: str) -> str:
    import pathlib
    f = pathlib.Path(f"/tmp/multidb_{tag}.py")
    f.write_text(content, encoding="utf-8")
    return str(f)


if __name__ == "__main__":
    main()
