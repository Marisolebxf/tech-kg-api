"""yunfei3 平台端 e2e（除人工审核外）：schema 建实体 → 绑脚本 → 抽取入图 → 图库验证。

目标图空间 yunfei_test（全新空空间）；数据源 yunfei3-test-mysql（宿主 33306）。
跑法（host）：python3 yunfei3_platform_e2e.py
前置：tech-kg-api-yunfei3 运行中（8004）+ temporal-worker-yunfei3 运行中。脚本幂等，可重复跑。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

API = "http://localhost:8004/api/v1"
GRAPH_SPACE = "yunfei_test"
MYSQL_CONTAINER = "yunfei3-test-mysql"
DS_HOST = "host.docker.internal"  # api 容器视角：宿主映射 33306
DS_PORT = 33306
DS_DB = "techkg_e2e"

PAPER_SCRIPT = '''"""论文抽取：papers 行 → Paper 实体。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        rid = str(row.get("id") or "")
        if not rid:
            failures.append({"recordId": "", "error": "ValueError: 缺少 id"})
            continue
        entities.append({
            "id": "paper_" + rid,
            "props": {
                "id": rid,
                "title": str(row.get("title") or ""),
                "author_name": str(row.get("author_name") or ""),
                "publish_year": int(row.get("publish_year") or 0),
            },
        })
    return {"entities": entities, "failures": failures}
'''

EXPERT_SCRIPT = '''"""专家抽取：experts 行 → Expert 实体。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        rid = str(row.get("id") or "")
        if not rid:
            failures.append({"recordId": "", "error": "ValueError: 缺少 id"})
            continue
        entities.append({
            "id": "expert_" + rid,
            "props": {
                "id": rid,
                "name": str(row.get("name") or ""),
                "org": str(row.get("org") or ""),
                "job_title": str(row.get("job_title") or ""),
            },
        })
    return {"entities": entities, "failures": failures}
'''


AUTHORED_SCRIPT = '''"""关系抽取：papers JOIN experts（作者名=专家名）→ AUTHORED 边。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    edges, failures = [], []
    for row in rows:
        pid = str(row.get("paper_id") or "")
        eid = str(row.get("expert_id") or "")
        if not pid or not eid:
            failures.append({"recordId": pid, "error": "ValueError: 关系两端 id 缺失"})
            continue
        edges.append({
            "fromId": "expert_" + eid,
            "toId": "paper_" + pid,
            "props": {"author_role": "第一作者"},
        })
    return {"edges": edges, "failures": failures}
'''


def req(method: str, path: str, body=None, headers: dict | None = None) -> tuple[int, Any]:
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
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


def graph_query(query: str) -> list[dict]:
    r = urllib.request.Request(
        "http://localhost:8090/api/v1/query/read",
        data=json.dumps({"query": query}).encode(),
        method="POST",
    )
    r.add_header("X-API-Key", "ysukeg")
    r.add_header("X-Graph-Space", GRAPH_SPACE)
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("data", {}).get("records") or data.get("records") or []


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


def reset_mysql():
    import subprocess
    subprocess.run(
        # 必须显式 utf8mb4：不指定时 client 按 latin1 解释中文入参，源数据变双重编码 mojibake
        ["docker", "exec", MYSQL_CONTAINER, "mysql", "--default-character-set=utf8mb4",
         "-uroot", "-ptemporal", "-e", f"""
CREATE DATABASE IF NOT EXISTS {DS_DB} DEFAULT CHARACTER SET utf8mb4;
USE {DS_DB};
DROP TABLE IF EXISTS papers;
CREATE TABLE papers (
  id VARCHAR(32) NOT NULL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  author_name VARCHAR(128) NOT NULL,
  publish_year INT NOT NULL,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
INSERT INTO papers (id, title, author_name, publish_year) VALUES
  ('p1', '知识图谱构建方法研究', '张三', 2024),
  ('p2', '大模型驱动的实体抽取', '李四', 2025),
  ('p3', '图数据库查询优化', '王五', 2023),
  ('p4', '多源数据融合综述', '赵六', 2026);
DROP TABLE IF EXISTS experts;
CREATE TABLE experts (
  id VARCHAR(32) NOT NULL PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  org VARCHAR(255) NOT NULL,
  job_title VARCHAR(128) NOT NULL,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
INSERT INTO experts (id, name, org, job_title) VALUES
  ('e1', '张三', '中科院计算所', '研究员'),
  ('e2', '李四', '清华大学', '副教授'),
  ('e3', '王五', '北京大学', '助理研究员');
"""],
        check=True, capture_output=True,
    )


def ensure_datasource(run: str) -> str:
    code, resp = req("GET", "/mysql-datasources")
    data = resp.get("data") or []
    items = data.get("items", []) if isinstance(data, dict) else data
    # 列表项没有 database 字段（只有 defaultDatabase，常为空），按 name 前缀 + host + port 查重
    ds = next(
        (i for i in items if str(i.get("name", "")).startswith("yunfei3-e2e-")
         and i.get("host") == DS_HOST and i.get("port") == DS_PORT),
        None,
    )
    if ds is None:
        code, resp = req(
            "POST",
            "/mysql-datasources",
            {
                "name": f"yunfei3-e2e-{run}",
                "host": DS_HOST,
                "port": DS_PORT,
                "username": "root",
                "password": "temporal",
                "database": DS_DB,
                "description": "yunfei_test 平台 e2e",
            },
        )
        ok(code in (200, 201), f"创建数据源 {code}: {str(resp)[:200]}")
        ds = resp["data"]
    return ds["id"]


def create_entity_schema(run: str, name: str, label: str, props: list[dict]) -> str:
    return _create_schema(run, "/schema-management/schemas/entities", name, label, props)


def create_relation_schema(run: str, name: str, label: str, props: list[dict],
                           source_id: str, target_id: str) -> str:
    return _create_schema(
        run, "/schema-management/schemas/relations", name, label, props,
        extra={"sourceSchemaId": source_id, "targetSchemaId": target_id,
               "relationCategory": "fact"},
    )


def _delete_same_name(name: str) -> None:
    code, resp = req("GET", f"/schema-management/schemas?keyword={name}&pageSize=100")
    for item in (resp.get("data") or {}).get("items") or []:
        if item.get("name") == name and item.get("graphSpace") == GRAPH_SPACE:
            req("DELETE", f"/schema-management/schemas/{item['id']}")


def _create_schema(run: str, path: str, name: str, label: str, props: list[dict],
                   extra: dict | None = None) -> str:
    # 幂等：删 yunfei_test 空间下同名旧 schema（techkg 等其它空间不动）
    _delete_same_name(name)
    body = {
        "schemaKey": f"e2e-{name.lower()}-{run}",
        "name": name,
        "label": label,
        "description": f"yunfei_test e2e {label}",
        "identityKey": "id",
        "properties": props,
        "isCore": False,
        "version": "v1.0",
        "graphSpace": GRAPH_SPACE,
    }
    body.update(extra or {})
    code, resp = req("POST", path, body)
    ok(code in (200, 201), f"创建 schema {name}（graphSpace={GRAPH_SPACE}） {code}: {str(resp)[:200]}")
    return resp["data"]["id"]


def upload_script(schema_id: str, script: str, run: str, tag: str) -> None:
    import pathlib
    import subprocess
    script_file = pathlib.Path(f"/tmp/e2e_{tag}_{run}.py")
    script_file.write_text(script, encoding="utf-8")
    r = subprocess.run(
        ["curl", "-sS", "-m", "60", "-X", "PUT",
         f"{API}/schema-management/schemas/{schema_id}/script",
         "-F", f"script=@{script_file}"],
        capture_output=True, text=True,
    )
    resp = json.loads(r.stdout or "{}")
    ok(resp.get("code", 0) == 200, f"上传 {tag} 脚本 inner={resp.get('code')}: {str(resp)[:200]}")


def bind_source(schema_id: str, datasource_id: str, table: str) -> None:
    code, resp = req(
        "PUT",
        f"/schema-management/schemas/{schema_id}/sources",
        {"sources": [{
            "datasourceId": datasource_id,
            "databaseName": DS_DB,
            "tableName": table,
            "pkColumn": "id",
            "timeColumn": "update_time",
        }]},
    )
    ok(code in (200, 201), f"绑定来源 {table} {code}: {str(resp)[:200]}")


# querySql 读取模式：以其为基表包水位/keyset 条件，须暴露 pk/time 同名列。
# 作者名 join 专家名 → 3 行（p4 赵六无匹配专家，正好验证只产出匹配的边）
RELATION_QUERY_SQL = (
    "SELECT p.id AS paper_id, e.id AS expert_id, p.update_time AS update_time "
    "FROM papers p JOIN experts e ON p.author_name = e.name"
)


def bind_query_source(schema_id: str, datasource_id: str) -> None:
    code, resp = req(
        "PUT",
        f"/schema-management/schemas/{schema_id}/sources",
        {"sources": [{
            "datasourceId": datasource_id,
            "databaseName": DS_DB,
            "tableName": "papers",  # querySql 提供时的名义基表
            "pkColumn": "paper_id",
            "timeColumn": "update_time",
            "querySql": RELATION_QUERY_SQL,
        }]},
    )
    ok(code in (200, 201), f"绑定 querySql 来源 {code}: {str(resp)[:200]}")


def run_extract(job_name: str, schema_id: str, expect_rows: int, expect_batches: int) -> dict:
    code, resp = req(
        "POST",
        "/workflow-system/jobs",
        {
            "name": job_name,
            "taskType": "extract",
            "schemaId": schema_id,
            "schedule": {"kind": "once"},
            "graphSpace": GRAPH_SPACE,
            "batchSize": 2,
        },
    )
    ok(code in (200, 201), f"创建任务 {job_name} {code}: {str(resp)[:200]}")
    job_id = resp["data"]["id"]
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    ok(code in (200, 201), f"触发 {job_name} {code}: {str(resp)[:150]}")
    execution_id = resp["data"]["id"]

    execution = wait_execution(execution_id)
    ok(execution["status"] == "COMPLETED",
       f"{job_name} 执行 COMPLETED（{execution['status']} {str(execution.get('message'))[:150]}）")
    out = execution.get("output") or {}
    src = (out.get("sources") or [{}])[0]
    ok(src.get("rows") == expect_rows and src.get("batches") == expect_batches,
       f"{job_name} 读取 {expect_rows} 行 / {expect_batches} 批（实际 {src.get('rows')}/{src.get('batches')}）")
    ok(src.get("written") == expect_rows, f"{job_name} 写图 {expect_rows} 实体（实际 {src.get('written')}）")
    ok((out.get("failures") or {}).get("count") == 0,
       f"{job_name} 0 失败记录（实际 {(out.get('failures') or {}).get('count')}）")
    return execution


def main():
    run = uuid.uuid4().hex[:6]

    step("0. 准备源数据（yunfei3-test-mysql / techkg_e2e：papers 4 行 + experts 3 行）")
    reset_mysql()
    print("  源表就绪")

    step("1. 注册数据源（host.docker.internal:33306）")
    datasource_id = ensure_datasource(run)
    print(f"  datasource={datasource_id}")

    step("2. 创建实体 Schema：Paper / Expert（graphSpace=yunfei_test，DDL 定向该空间）")
    # 幂等清理顺序：先删关系（AUTHORED 引用实体，不先删则实体删除被 409 拒绝）
    _delete_same_name("AUTHORED")
    paper_id = create_entity_schema(
        run, "Paper", "论文",
        [
            {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
            {"name": "title", "dataType": "string", "required": True, "category": "core", "rule": ""},
            {"name": "author_name", "dataType": "string", "required": False, "category": "core", "rule": ""},
            {"name": "publish_year", "dataType": "int64", "required": False, "category": "core", "rule": ""},
        ],
    )
    expert_id = create_entity_schema(
        run, "Expert", "专家",
        [
            {"name": "id", "dataType": "string", "required": True, "category": "core", "rule": ""},
            {"name": "name", "dataType": "string", "required": True, "category": "core", "rule": ""},
            {"name": "org", "dataType": "string", "required": False, "category": "core", "rule": ""},
            {"name": "job_title", "dataType": "string", "required": False, "category": "core", "rule": ""},
        ],
    )
    print(f"  paper={paper_id} expert={expert_id}")

    step("3. 上传抽取脚本（transform 入口）")
    upload_script(paper_id, PAPER_SCRIPT, run, "paper")
    upload_script(expert_id, EXPERT_SCRIPT, run, "expert")

    step("4. 绑定来源表（pk=id, time=update_time）")
    bind_source(paper_id, datasource_id, "papers")
    bind_source(expert_id, datasource_id, "experts")

    step("5. 图谱构建：创建抽取任务并触发（batchSize=2）")
    run_extract(f"e2e论文抽取-{run}", paper_id, expect_rows=4, expect_batches=2)
    run_extract(f"e2e专家抽取-{run}", expert_id, expect_rows=3, expect_batches=2)

    step("5.5 关系：创建 AUTHORED（Expert→Paper）+ querySql 来源 join 抽取")
    authored_id = create_relation_schema(
        run, "AUTHORED", "撰写",
        [{"name": "author_role", "dataType": "string", "required": False,
          "category": "core", "rule": ""}],
        source_id=expert_id, target_id=paper_id,
    )
    print(f"  relation={authored_id}")
    upload_script(authored_id, AUTHORED_SCRIPT, run, "authored")
    bind_query_source(authored_id, datasource_id)
    run_extract(f"e2e关系抽取-{run}", authored_id, expect_rows=3, expect_batches=2)

    step("6. 图库验证（yunfei_test 空间）")
    # 裸列（v.title）经 trs-graph 返回 None，须用 properties(v) 聚合取属性
    papers = graph_query(
        "MATCH (v:Paper) RETURN id(v) AS vid, properties(v) AS props "
        "ORDER BY vid LIMIT 20"
    )
    paper_vids = {r.get("vid") for r in papers}
    ok({"paper_p1", "paper_p2", "paper_p3", "paper_p4"} <= paper_vids,
       f"Paper 4 节点入库（{sorted(v for v in paper_vids if v)}）")
    sample = next(r for r in papers if r.get("vid") == "paper_p1")
    props = sample.get("props") or {}
    ok(str(props.get("title")) == "知识图谱构建方法研究",
       f"属性正确（title={props.get('title')}）")
    ok(props.get("publish_year") == 2024, f"int 属性正确（publish_year={props.get('publish_year')}）")
    ok(props.get("source_table") == "techkg_e2e.papers",
       f"溯源列写入（source_table={props.get('source_table')}）")

    experts = graph_query(
        "MATCH (v:Expert) RETURN id(v) AS vid, properties(v) AS props "
        "ORDER BY vid LIMIT 20"
    )
    expert_vids = {r.get("vid") for r in experts}
    ok({"expert_e1", "expert_e2", "expert_e3"} <= expert_vids,
       f"Expert 3 节点入库（{sorted(v for v in expert_vids if v)}）")
    sample = next(r for r in experts if r.get("vid") == "expert_e1")
    props = sample.get("props") or {}
    ok(str(props.get("name")) == "张三" and "中科院" in str(props.get("org")),
       f"属性正确（name={props.get('name')} org={props.get('org')}）")

    edges = graph_query(
        "MATCH (s:Expert)-[e:AUTHORED]->(t:Paper) "
        "RETURN id(s) AS src, id(t) AS dst, properties(e) AS props ORDER BY src LIMIT 20"
    )
    pairs = {(r.get("src"), r.get("dst")) for r in edges}
    expect_pairs = {
        ("expert_e1", "paper_p1"), ("expert_e2", "paper_p2"), ("expert_e3", "paper_p3"),
    }
    ok(pairs == expect_pairs,
       f"AUTHORED 3 条边且方向正确（实际 {sorted(str(p) for p in pairs)}）")
    ok(all((r.get("props") or {}).get("author_role") == "第一作者" for r in edges),
       "边属性正确（author_role=第一作者）")

    step("7. 水位推进：再次触发论文任务应读 0 行")
    code, resp = req(
        "POST", "/workflow-system/jobs",
        {"name": f"e2e论文水位-{run}", "taskType": "extract", "schemaId": paper_id,
         "schedule": {"kind": "once"}, "graphSpace": GRAPH_SPACE, "batchSize": 2},
    )
    job_id = resp["data"]["id"]
    code, resp = req("POST", f"/workflow-system/jobs/{job_id}/trigger")
    execution = wait_execution(resp["data"]["id"])
    src = (execution.get("output") or {}).get("sources") or [{}]
    ok(src and src[0].get("rows") == 0, f"第二跑读取 0 行（实际 {src[0].get('rows') if src else '?'}）")

    print("\n全部 E2E 通过 ✔")


if __name__ == "__main__":
    main()
