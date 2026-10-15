#!/usr/bin/env python3
"""gkx_local_1 三件套灌入:Schema(50) -> 来源绑定(152) -> 脚本(46)。遇错即停。"""
import json
from pathlib import Path

import requests

API = "http://localhost:8004"        # yunfei3 栈;换栈改这里(开鉴权的栈自行带 headers)
NEW_SPACE = "gkx_local_rb1"          # 新空间名(须已建好)
DS = "MYSQL-DWD-LOCAL"               # 数据源 id;换栈时改成新数据源
M = Path(__file__).parent            # 物料包目录

schemas = json.loads((M / "schemas.json").read_text())["schemas"]
bindings = json.loads((M / "bindings.json").read_text())["bindings"]

def call(method, path, **kw):
    r = requests.request(method, f"{API}/api/v1/schema-management{path}", timeout=120, **kw)
    j = r.json()
    if r.status_code >= 400 or not j.get("success"):
        raise SystemExit(f"{method} {path} -> {r.status_code} {j}")
    return j["data"]

# 1) 建 Schema:先实体后关系(关系按 name 解析源/目标新 id)
id_by_name = {}
for kind, path in (("entity", "/schemas/entities"), ("relation", "/schemas/relations")):
    for s in [x for x in schemas if x["kind"] == kind]:
        body = {
            "schemaKey": s["key"], "name": s["name"], "label": s["label"],
            "description": s.get("description") or "", "identityKey": s.get("identityKey") or "",
            "properties": [
                {"name": p["name"], "dataType": p["dataType"], "required": p.get("required", False),
                 "rule": p.get("rule") or "", "category": p.get("category") or "core"}
                for p in s["properties"]
            ],
            "graphSpace": NEW_SPACE,
        }
        if kind == "relation":
            body["sourceSchemaId"] = id_by_name[s["sourceSchemaName"]]
            body["targetSchemaId"] = id_by_name[s["targetSchemaName"]]
        id_by_name[s["name"]] = call("POST", path, json=body)["id"]
        print("created", s["name"])

# 2) 绑来源(按 schema 聚合后全量替换)
by_schema = {}
for b in bindings:
    by_schema.setdefault(b["schemaName"], []).append({
        "datasourceId": DS, "databaseName": b["databaseName"], "tableName": b["tableName"],
        "pkColumn": b["pkColumn"], "timeColumn": b["timeColumn"], "querySql": b["querySql"],
    })
for name, srcs in by_schema.items():
    call("PUT", f"/schemas/{id_by_name[name]}/sources", json={"sources": srcs})
    print("bound", name, len(srcs))

# 3) 传脚本(multipart 字段名 script;文件名与 schema 登记一致)
for s in schemas:
    fn = s.get("scriptFilename")
    if not fn:
        continue
    with open(M / "scripts" / fn, "rb") as f:
        call("PUT", f"/schemas/{id_by_name[s['name']]}/script", files={"script": (fn, f)})
    print("scripted", fn)
