#!/usr/bin/env python3
"""批量通过 API 流程测试 relation 抽取脚本：模拟前端用户操作。

对每个 relation：
1. 若 techkg_control 已有同名 schema（系统 53 个 relation）→ DELETE（relation 不被引用，不需级联）
2. 若 dev2 已有同名 EDGE → DROP EDGE IF EXISTS，加 time.sleep(5) 等 DDL 传播
3. 查 source/target entity 的 schema_id（在 techkg_control.kg_schema_definition 按 name 找）
4. POST /schemas/relations 带 schemaKey/name/label/source_schema_id/target_schema_id/
   source_expression/target_expression/properties
5. PUT /schemas/{id}/script 上传 backend/script/relation_extractors_one_relation/{name}_relation.py
6. POST /workflow-system/definitions/schema-{name with dash}/execute payload {limit:2} 等 25s
7. 验证 execution COMPLETED + dev2 图 EDGE count > 0

用法：
    python3 dev2_api_flow_batch_relations.py [--relation NAME] [--skip-cleanup]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "http://localhost:8002/api/v1"
GRAPH = "http://localhost:8090/api/v1/query/write"
GRAPH_HEADERS = {"X-API-Key": "ysukeg", "X-Graph-Space": "dev2", "Content-Type": "application/json"}
SCRIPT_DIR = "backend/script/relation_extractors_one_relation"


def _props(specs: list[tuple[str, str]]) -> list[dict]:
    """specs: [(name, dataType)]。默认 string；数值/布尔走对应类型避免 merge_edge 400。"""
    return [{"name": n, "dataType": t, "required": False, "category": "core", "rule": ""}
            for n, t in specs]


# 数值/布尔属性的真实类型（仅 REST merge 模式影响；rank 模式 INSERT EDGE 会自动转）。
NUMERIC_PROPS = {"confidence", "co_paper_count", "funded_amount", "investment_amount",
                 "investment_ratio", "ownership_percentage", "direct_percent", "indirect_percent",
                 "total_percent", "direct_pct", "total_pct", "ma_amount", "chain_score",
                 "sequence", "citations"}
BOOL_PROPS = {"is_current", "is_corresponding"}


def _typed_props(names: list[str]) -> list[dict]:
    specs = []
    for n in names:
        if n in NUMERIC_PROPS:
            specs.append((n, "double"))
        elif n in BOOL_PROPS:
            specs.append((n, "bool"))
        else:
            specs.append((n, "string"))
    return _props(specs)


# 每个 relation 的 spec：
#   script  = 脚本文件名（不含路径），用于 _bind_script
#   edges   = 该脚本会写的 EDGE 类型列表，每个 EDGE 一份 schema
# 每个 edge：
#   edge_type, source_tag, target_tag, source_expr, target_expr, properties
# catalog 驱动的 11 个 relation 共用 org_edges.py，source/target 取主端点。
RELATION_SPECS: dict[str, dict] = {
    # --- 简单脚本（单 EDGE，rank 模式） ---
    "authored_by": {
        "script": "authored_by_relation.py",
        "edges": [{
            "edge_type": "AUTHORED_BY", "source_tag": "Paper", "target_tag": "Person",
            "source_expr": "Paper", "target_expr": "Person",
            "properties": ["author_order", "is_corresponding", "confidence"],
        }],
    },
    "authored_by_fallback": {
        "script": "authored_by_fallback_relation.py",
        "edges": [{
            "edge_type": "AUTHORED_BY", "source_tag": "Paper", "target_tag": "Person",
            "source_expr": "Paper", "target_expr": "Person",
            "properties": ["citations", "source_table", "source_record_id", "ingest_batch",
                           "ingest_time", "confidence", "match_method", "match_evidence"],
        }],
    },
    "belongs_to_node": {
        "script": "belongs_to_node_relation.py",
        "edges": [{
            "edge_type": "BELONGS_TO_NODE", "source_tag": "Organization", "target_tag": "IndustryNode",
            "source_expr": "Organization", "target_expr": "IndustryNode",
            "properties": ["chain_score", "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "child_of": {
        "script": "child_of_relation.py",
        "edges": [{
            "edge_type": "CHILD_OF", "source_tag": "IndustryNode", "target_tag": "IndustryNode",
            "source_expr": "IndustryNode", "target_expr": "IndustryNode",
            "properties": ["extra_json"],
        }],
    },
    "coauthor_with": {
        "script": "coauthor_with_relation.py",
        "edges": [{
            "edge_type": "COAUTHOR_WITH", "source_tag": "Person", "target_tag": "Person",
            "source_expr": "Person", "target_expr": "Person",
            "properties": ["co_paper_count", "confidence", "match_method", "match_evidence",
                           "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "covers_chain": {
        "script": "covers_chain_relation.py",
        "edges": [{
            "edge_type": "COVERS_CHAIN", "source_tag": "News", "target_tag": "IndustryChain",
            "source_expr": "News", "target_expr": "IndustryChain",
            "properties": ["source_table", "ingest_batch", "ingest_time"],
        }],
    },
    "downstream_of": {
        "script": "downstream_of_relation.py",
        "edges": [{
            "edge_type": "DOWNSTREAM_OF", "source_tag": "IndustryNode", "target_tag": "IndustryNode",
            "source_expr": "IndustryNode", "target_expr": "IndustryNode",
            "properties": ["extra_json"],
        }],
    },
    "has_node": {
        "script": "has_node_relation.py",
        "edges": [{
            "edge_type": "HAS_NODE", "source_tag": "IndustryChain", "target_tag": "IndustryNode",
            "source_expr": "IndustryChain", "target_expr": "IndustryNode",
            "properties": ["extra_json"],
        }],
    },
    "member_of_family": {
        "script": "member_of_family_relation.py",
        "edges": [{
            "edge_type": "MEMBER_OF_FAMILY", "source_tag": "Patent", "target_tag": "PatentFamily",
            "source_expr": "Patent", "target_expr": "PatentFamily",
            "properties": ["confidence", "match_method", "match_evidence", "source_table", "source_record_id"],
        }],
    },
    "paper_has_keyword": {
        "script": "paper_has_keyword_relation.py",
        "edges": [{
            "edge_type": "HAS_KEYWORD", "source_tag": "Paper", "target_tag": "Keyword",
            "source_expr": "Paper", "target_expr": "Keyword",
            "properties": ["confidence"],
        }],
    },
    "patent_has_keyword": {
        "script": "patent_has_keyword_relation.py",
        "edges": [{
            "edge_type": "HAS_KEYWORD", "source_tag": "Patent", "target_tag": "Keyword",
            "source_expr": "Patent", "target_expr": "Keyword",
            "properties": ["confidence", "source_table", "source_record_id"],
        }],
    },
    "published_in": {
        "script": "published_in_relation.py",
        "edges": [{
            "edge_type": "PUBLISHED_IN", "source_tag": "Paper", "target_tag": "Journal",
            "source_expr": "Paper", "target_expr": "Journal",
            "properties": ["confidence"],
        }],
    },
    "referenced_by": {
        "script": "referenced_by_relation.py",
        "edges": [{
            "edge_type": "REFERENCED_BY", "source_tag": "Paper", "target_tag": "Report",
            "source_expr": "Paper", "target_expr": "Report",
            "properties": ["confidence"],
        }],
    },
    # --- 多 EDGE 脚本 ---
    "paper_cites": {
        "script": "paper_cites_relation.py",
        "edges": [
            {"edge_type": "CITES", "source_tag": "Paper", "target_tag": "Paper",
             "source_expr": "Paper", "target_expr": "Paper",
             "properties": ["reference_identifier", "confidence"]},
            {"edge_type": "CITED_BY", "source_tag": "Paper", "target_tag": "Paper",
             "source_expr": "Paper", "target_expr": "Paper",
             "properties": ["citation_identifier", "confidence"]},
            {"edge_type": "RELATED_TO", "source_tag": "Paper", "target_tag": "Paper",
             "source_expr": "Paper", "target_expr": "Paper",
             "properties": ["confidence"]},
        ],
    },
    "applied_by": {
        "script": "applied_by_relation.py",
        "edges": [
            {"edge_type": "APPLIED_BY", "source_tag": "Patent", "target_tag": "Organization",
             "source_expr": "Patent", "target_expr": "Organization",
             "properties": ["sequence", "role", "source_name", "confidence", "subject_type",
                            "resolution_status", "match_method", "match_evidence", "source_table",
                            "source_record_id"]},
            {"edge_type": "OWNED_BY", "source_tag": "Patent", "target_tag": "Organization",
             "source_expr": "Patent", "target_expr": "Organization",
             "properties": ["sequence", "role", "is_current", "source_name", "confidence",
                            "subject_type", "resolution_status", "match_method", "match_evidence",
                            "source_table", "source_record_id"]},
        ],
    },
    # --- 复杂脚本（单 EDGE，REST merge 模式） ---
    "affiliated_with": {
        "script": "affiliated_with_relation.py",
        "edges": [{
            "edge_type": "AFFILIATED_WITH", "source_tag": "Person", "target_tag": "Organization",
            "source_expr": "Person", "target_expr": "Organization",
            "properties": ["affiliation_name", "work_experience_date", "work_experience_department_zh",
                           "work_experience_position_zh", "source", "source_table", "source_record_id",
                           "ingest_batch", "ingest_time", "organization_base", "organization_id",
                           "confidence", "match_method", "match_evidence"],
        }],
    },
    "funded_by": {
        "script": "funded_by_relation.py",
        "edges": [{
            "edge_type": "FUNDED_BY", "source_tag": "Project", "target_tag": "Organization",
            "source_expr": "Project", "target_expr": "Organization",
            "properties": ["source_table", "source_record_id", "ingest_batch", "ingest_time",
                           "funded_amount", "fund_category", "match_method", "match_evidence",
                           "confidence", "organization_id", "organization_source_table"],
        }],
    },
    "has_output": {
        "script": "has_output_relation.py",
        "edges": [{
            "edge_type": "HAS_OUTPUT", "source_tag": "Project", "target_tag": "Paper",
            "source_expr": "Project", "target_expr": "Paper",
            "properties": ["output_type", "output_title", "output_identifier", "match_method",
                           "match_evidence", "confidence", "source_table", "source_record_id",
                           "ingest_batch", "ingest_time"],
        }],
    },
    "has_participant": {
        "script": "has_participant_relation.py",
        "edges": [{
            "edge_type": "HAS_PARTICIPANT", "source_tag": "Project", "target_tag": "Person",
            "source_expr": "Project", "target_expr": "Person",
            "properties": ["source_table", "source_record_id", "ingest_batch", "ingest_time",
                           "match_method", "match_evidence", "confidence"],
        }],
    },
    "invented_by": {
        "script": "invented_by_relation.py",
        "edges": [{
            "edge_type": "INVENTED_BY", "source_tag": "Patent", "target_tag": "Person",
            "source_expr": "Patent", "target_expr": "Person",
            "properties": ["sequence", "source_name", "confidence", "subject_type",
                           "resolution_status", "match_method", "match_evidence", "source_table",
                           "source_record_id"],
        }],
    },
    "leads": {
        "script": "leads_relation.py",
        "edges": [{
            "edge_type": "LEADS", "source_tag": "Project", "target_tag": "Person",
            "source_expr": "Project", "target_expr": "Person",
            "properties": ["source_table", "source_record_id", "ingest_batch", "ingest_time",
                           "match_method", "match_evidence", "confidence"],
        }],
    },
    "patent_cites": {
        "script": "patent_cites_relation.py",
        "edges": [{
            "edge_type": "CITES", "source_tag": "Patent", "target_tag": "Patent",
            "source_expr": "Patent", "target_expr": "Patent",
            "properties": ["reference_identifier", "sequence", "confidence", "match_method",
                           "match_evidence", "source_table", "source_record_id"],
        }],
    },
    "project_has_keyword": {
        "script": "project_has_keyword_relation.py",
        "edges": [{
            "edge_type": "HAS_KEYWORD", "source_tag": "Project", "target_tag": "Keyword",
            "source_expr": "Project", "target_expr": "Keyword",
            "properties": ["source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    # --- catalog 驱动的 11 个 relation（org_edges.py，rank 模式） ---
    "legal_rep_of": {
        "script": "legal_rep_of_relation.py",
        "edges": [{
            "edge_type": "LEGAL_REP_OF", "source_tag": "Person", "target_tag": "Organization",
            "source_expr": "Person", "target_expr": "Organization",
            "properties": ["extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "shareholder_of": {
        "script": "shareholder_of_relation.py",
        "edges": [{
            "edge_type": "SHAREHOLDER_OF", "source_tag": "Organization", "target_tag": "Organization",
            "source_expr": "Organization", "target_expr": "Organization",
            "properties": ["ownership_percentage", "extra_json", "organization_id", "confidence",
                           "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "executive_of": {
        "script": "executive_of_relation.py",
        "edges": [{
            "edge_type": "EXECUTIVE_OF", "source_tag": "Person", "target_tag": "Organization",
            "source_expr": "Person", "target_expr": "Organization",
            "properties": ["position", "extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "beneficial_owner_of": {
        "script": "beneficial_owner_of_relation.py",
        "edges": [{
            "edge_type": "BENEFICIAL_OWNER_OF", "source_tag": "Person", "target_tag": "Organization",
            "source_expr": "Person", "target_expr": "Organization",
            "properties": ["direct_percent", "indirect_percent", "total_percent", "extra_json",
                           "organization_id", "confidence", "source_table", "source_record_id",
                           "ingest_batch", "ingest_time"],
        }],
    },
    "actual_controller_of": {
        "script": "actual_controller_of_relation.py",
        "edges": [{
            "edge_type": "ACTUAL_CONTROLLER_OF", "source_tag": "Organization", "target_tag": "Organization",
            "source_expr": "Organization", "target_expr": "Organization",
            "properties": ["direct_pct", "total_pct", "extra_json", "organization_id", "confidence",
                           "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "invests_in": {
        "script": "invests_in_relation.py",
        "edges": [{
            "edge_type": "INVESTS_IN", "source_tag": "Organization", "target_tag": "Organization",
            "source_expr": "Organization", "target_expr": "Organization",
            "properties": ["investment_amount", "investment_ratio", "extra_json", "organization_id",
                           "confidence", "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "acquires": {
        "script": "acquires_relation.py",
        "edges": [{
            "edge_type": "ACQUIRES", "source_tag": "Organization", "target_tag": "Organization",
            "source_expr": "Organization", "target_expr": "Organization",
            "properties": ["ma_amount", "currency_code", "extra_json", "organization_id", "confidence",
                           "source_table", "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "subsidiary_of": {
        "script": "subsidiary_of_relation.py",
        "edges": [{
            "edge_type": "SUBSIDIARY_OF", "source_tag": "Organization", "target_tag": "Organization",
            "source_expr": "Organization", "target_expr": "Organization",
            "properties": ["extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "has_news": {
        "script": "has_news_relation.py",
        "edges": [{
            "edge_type": "HAS_NEWS", "source_tag": "Organization", "target_tag": "News",
            "source_expr": "Organization", "target_expr": "News",
            "properties": ["extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "involved_in": {
        "script": "involved_in_relation.py",
        "edges": [{
            "edge_type": "INVOLVED_IN", "source_tag": "Organization", "target_tag": "Event",
            "source_expr": "Organization", "target_expr": "Event",
            "properties": ["role", "extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
    "produces": {
        "script": "produces_relation.py",
        "edges": [{
            "edge_type": "PRODUCES", "source_tag": "Organization", "target_tag": "Product",
            "source_expr": "Organization", "target_expr": "Product",
            "properties": ["extra_json", "organization_id", "confidence", "source_table",
                           "source_record_id", "ingest_batch", "ingest_time"],
        }],
    },
}


def _req(method: str, url: str, headers: dict | None = None, data: bytes | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:
        return 0, f"network err: {e!r}"


def _nGQL(query: str) -> dict:
    code, resp = _req("POST", GRAPH, GRAPH_HEADERS, json.dumps({"query": query}).encode())
    return resp if isinstance(resp, dict) else {"error": resp}


def _find_schema(name: str) -> dict | None:
    """分页查 schema 全记录（含 schemaKey/id）。优先 kind=relation 过滤缩小范围。"""
    for kind in ("relation", "entity"):
        page = 1
        while True:
            path = f"{API}/schema-management/schemas?limit=20&page={page}&kind={kind}"
            code, resp = _req("GET", path)
            if not isinstance(resp, dict):
                break
            data = resp.get("data", {})
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for s in items:
                if s.get("name") == name:
                    return s
            if len(items) < 20:
                break
            page += 1
            if page > 10:
                break
    return None


def _find_schema_id(name: str) -> str | None:
    s = _find_schema(name)
    return s["id"] if s else None
    """分页查 schemas（后端 pageSize 上限 20）。优先 kind=relation 过滤缩小范围。"""
    for kind in ("relation", "entity"):
        page = 1
        while True:
            path = f"{API}/schema-management/schemas?limit=20&page={page}&kind={kind}"
            code, resp = _req("GET", path)
            if not isinstance(resp, dict):
                break
            data = resp.get("data", {})
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for s in items:
                if s.get("name") == name:
                    return s["id"]
            if len(items) < 20:
                break
            page += 1
            if page > 10:  # 安全上限
                break
    return None


def _find_entity_schema_id(entity_name: str) -> str | None:
    """查 techkg_control.kg_schema_definition 找 entity name 的 schema_id（PascalCase）。"""
    out = subprocess.check_output([
        "docker", "exec", "tech-kg-temporal-mysql-dev2", "mysql", "-uroot", "-ptemporal",
        "techkg_control", "-N", "-e",
        f"SELECT id FROM kg_schema_definition WHERE kind='entity' AND name='{entity_name}' LIMIT 1;"
    ], text=True)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[0] if lines else None


def _delete_schema(schema_id: str) -> bool:
    code, resp = _req("DELETE", f"{API}/schema-management/schemas/{schema_id}")
    return code == 200


def _drop_edge(edge_type: str) -> bool:
    r = _nGQL(f"DROP EDGE IF EXISTS {edge_type};")
    return "error" not in r


def _edge_exists(edge_type: str) -> bool:
    r = _nGQL(f"DESCRIBE EDGE {edge_type};")
    if not isinstance(r, dict):
        return False
    if r.get("error"):
        return False
    # 响应结构：records 在顶层（trs-graph /api/v1/query/write）
    recs = r.get("records") or r.get("data", {}).get("records", [])
    return bool(recs)


def _create_edge_ddl(edge_type: str, prop_names: list[str]) -> bool:
    """图内不存在时手动 CREATE EDGE，让 nGQL 传播稳定。数值/布尔用对应类型。"""
    if _edge_exists(edge_type):
        return True
    parts = []
    for p in prop_names:
        if p in NUMERIC_PROPS:
            parts.append(f"`{p}` double")
        elif p in BOOL_PROPS:
            parts.append(f"`{p}` bool")
        else:
            parts.append(f"`{p}` string")
    cols = ",".join(parts)
    ddl = f"CREATE EDGE IF NOT EXISTS `{edge_type}` ({cols});" if parts else f"CREATE EDGE IF NOT EXISTS `{edge_type}`();"
    r = _nGQL(ddl)
    if isinstance(r, dict) and r.get("error"):
        return False
    time.sleep(3)
    return _edge_exists(edge_type)


def _create_relation_schema(name: str, edge: dict, source_id: str, target_id: str) -> tuple[str | None, str] | None:
    """返回 (schema_id, schemaKey) 或 None。"""
    body = {
        "schemaKey": name.replace("_", "-"),
        "name": edge["edge_type"],
        "label": edge["edge_type"].title().replace("_", " "),
        "description": f"{edge['edge_type']} 关系（API 流程测试）",
        "identityKey": "",
        "properties": _typed_props(edge["properties"]),
        "sourceSchemaId": source_id,
        "targetSchemaId": target_id,
        "sourceExpression": edge["source_expr"],
        "targetExpression": edge["target_expr"],
        "relationCategory": "fact",
        "isCore": False,
        "version": "v2.1",
    }
    code, resp = _req("POST", f"{API}/schema-management/schemas/relations",
                      {"Content-Type": "application/json"}, json.dumps(body).encode())
    if code == 409:
        # 共享 EDGE 的 schema 已存在（多脚本写同一 EDGE，如 HAS_KEYWORD/CITES），
        # 复用现有 schema，仅重新绑定脚本——用其真实 schemaKey 做 workflow_def_id。
        existing = _find_schema(edge["edge_type"])
        if existing:
            print(f"    409 复用已存在 schema {edge['edge_type']}: id={existing['id']} key={existing.get('key')}")
            if not _create_edge_ddl(edge["edge_type"], edge["properties"]):
                print(f"    WARN: CREATE EDGE {edge['edge_type']} 仍不存在")
            return existing["id"], existing.get("key") or existing["id"]
        print(f"    POST relation schema FAIL 409 且找不到现有 schema: {str(resp)[:200]}")
        return None
    if code not in (200, 201):
        print(f"    POST relation schema FAIL {code}: {str(resp)[:300]}")
        return None
    # schema API 触发的 CREATE EDGE IF NOT EXISTS 有时被 DROP 的旧状态覆盖，
    # 这里兜底手动 CREATE，保证 graph 里 EDGE 真实存在。
    if not _create_edge_ddl(edge["edge_type"], edge["properties"]):
        print(f"    WARN: CREATE EDGE {edge['edge_type']} 仍不存在，worker 写边将失败")
    data = resp.get("data", {})
    return data["id"], name.replace("_", "-")


def _bind_script(schema_id: str, script_path: str) -> bool:
    r = subprocess.run([
        "curl", "-sS", "-m", "30", "-X", "PUT",
        f"{API}/schema-management/schemas/{schema_id}/script",
        "-F", f"script=@{script_path}",
    ], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return d.get("code") == 200
    except Exception:
        return False


def _trigger_and_wait(workflow_def_id: str, limit: int = 2, wait_s: int = 35) -> tuple[str, dict | None, str | None]:
    """返回 (status, output_dict, error_msg)。若 wait_s 后仍 RUNNING，最多再等 60s。"""
    body = json.dumps({"payload": {"limit": limit}}).encode()
    code, resp = _req("POST", f"{API}/workflow-system/definitions/{workflow_def_id}/execute",
                      {"Content-Type": "application/json"}, body)
    if code != 200:
        return f"trigger_fail_{code}", None, str(resp)[:300]
    exec_id = resp["data"]["id"]
    time.sleep(wait_s)
    total_waited = wait_s
    while total_waited < wait_s + 60:
        code, resp = _req("GET", f"{API}/workflow-system/executions/{exec_id}")
        if not isinstance(resp, dict):
            return "status_unknown", None, str(resp)[:300]
        d = resp.get("data", {})
        st = d.get("status", "unknown")
        if st in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
            out = d.get("output")
            if isinstance(out, str):
                try:
                    out = json.loads(out)
                except Exception:
                    out = {"_raw": out}
            err = d.get("error") or (out.get("error") if isinstance(out, dict) else None)
            return st, out, (str(err)[:300] if err else None)
        time.sleep(10)
        total_waited += 10
    return "RUNNING", None, None


def _count_edges(edge_type: str) -> int:
    """用 REST /api/v1/edges/type/{EDGE_TYPE}?limit=1 拿 total。"""
    code, resp = _req("GET", f"http://localhost:8090/api/v1/edges/type/{edge_type}?limit=1",
                      {"X-API-Key": "ysukeg", "X-Graph-Space": "dev2"})
    if not isinstance(resp, dict):
        # 回退到 nGQL
        r = _nGQL(f"MATCH ()-[e:{edge_type}]->() RETURN count(*) AS cnt;")
        recs = r.get("data", {}).get("records", []) if isinstance(r, dict) else []
        for rec in recs:
            if "cnt" in rec:
                try:
                    return int(rec["cnt"])
                except (TypeError, ValueError):
                    pass
        return 0
    return resp.get("page", {}).get("total", 0)


def test_relation(name: str, *, skip_cleanup: bool = False) -> dict:
    spec = RELATION_SPECS[name]
    script = spec["script"]
    edges = spec["edges"]
    print(f"\n=== {name} (script={script}, {len(edges)} edge(s)) ===")
    result = {"relation": name, "edges": [], "steps": {}}

    # 1. cleanup：对每个 edge_type，先 DELETE 系统 schema（同名），再 DROP EDGE
    if not skip_cleanup:
        for edge in edges:
            et = edge["edge_type"]
            existing_id = _find_schema_id(et)
            if existing_id:
                _delete_schema(existing_id)
                print(f"  step1 DELETE schema {et}: done")
        time.sleep(2)
        for edge in edges:
            et = edge["edge_type"]
            _drop_edge(et)
            print(f"  step2 DROP EDGE {et}: done")
        time.sleep(12)  # NebulaGraph DDL 传播延迟（~2 个心跳，默认 heartbeat 10s）
        result["steps"]["delete"] = "ok"

    # 2. 查 source/target entity schema_id
    created: list[dict] = []
    all_create_ok = True
    for edge in edges:
        src_id = _find_entity_schema_id(edge["source_tag"])
        tgt_id = _find_entity_schema_id(edge["target_tag"])
        if not src_id or not tgt_id:
            print(f"  step3 MISSING entity schema: src={edge['source_tag']}({src_id}) tgt={edge['target_tag']}({tgt_id})")
            all_create_ok = False
            continue
        # 3. POST relation schema（schemaKey 用 relation name + edge_type 防多 edge 冲突）
        schema_key_name = f"{name}_{et_safe(edge['edge_type'])}" if len(edges) > 1 else name
        ret = _create_relation_schema(schema_key_name, edge, src_id, tgt_id)
        if not ret:
            all_create_ok = False
            continue
        schema_id, schema_key = ret
        et = edge["edge_type"]
        print(f"  step3 POST schema {et}: id={schema_id}")
        # 4. PUT script（同一脚本绑到每个 schema——多 edge 时绑多次，只 trigger 第一个）
        ok = _bind_script(schema_id, f"{SCRIPT_DIR}/{script}")
        print(f"  step4 bind script: {'ok' if ok else 'FAIL'} (edge={et})")
        created.append({"edge_type": et, "schema_key": schema_key,
                        "schema_id": schema_id, "bind_ok": ok})
    if not all_create_ok or not created:
        result["steps"]["create"] = "FAIL"
        return result
    result["steps"]["create"] = "ok"

    # 5. trigger + wait。多 edge 脚本用第一个绑过脚本的 schema_key 做 workflow_def_id；
    # 单 edge 脚本用 name with dash。
    trigger_key = next((c["schema_key"] for c in created if c["bind_ok"]), created[0]["schema_key"])
    wf_id = f"schema-{trigger_key}"
    status, out, err = _trigger_and_wait(wf_id)
    srcs = (out or {}).get("sources", {}) if isinstance(out, dict) else {}
    total_written = sum(v.get("written", 0) for v in srcs.values()) if isinstance(srcs, dict) else 0
    print(f"  step5 trigger: status={status} written={total_written}" + (f" err={err}" if err else ""))
    result["steps"]["trigger"] = status
    result["written"] = total_written
    if err:
        result["error"] = err

    # 6. verify dev2 graph edge count（每个 edge_type）
    edge_counts: dict[str, int] = {}
    for edge in edges:
        et = edge["edge_type"]
        cnt = _count_edges(et)
        print(f"  step6 dev2 graph EDGE {et} count={cnt}")
        edge_counts[et] = cnt
    result["edge_counts"] = edge_counts
    result["edges"] = [{"edge_type": e["edge_type"], "source": e["source_tag"], "target": e["target_tag"]}
                       for e in edges]
    return result


def et_safe(edge_type: str) -> str:
    return edge_type.lower()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--relation", help="只测一个 relation")
    p.add_argument("--skip-cleanup", action="store_true", help="跳过 DELETE+DROP 步骤")
    args = p.parse_args()

    names = [args.relation] if args.relation else list(RELATION_SPECS.keys())
    results = []
    for name in names:
        try:
            r = test_relation(name, skip_cleanup=args.skip_cleanup)
            results.append(r)
        except Exception as e:
            print(f"  EXCEPTION: {e!r}")
            results.append({"relation": name, "error": repr(e)})

    print("\n=== SUMMARY ===")
    for r in results:
        if "error" in r and "steps" not in r:
            print(f"  {r['relation']:28s} EXCEPTION: {r['error'][:80]}")
            continue
        ok = (r.get("steps", {}).get("trigger") == "COMPLETED"
              and any(c > 0 for c in r.get("edge_counts", {}).values()))
        mark = "PASS" if ok else "FAIL"
        trig = r.get("steps", {}).get("trigger", "?")
        written = r.get("written", "?")
        ec = r.get("edge_counts", {})
        ec_str = ",".join(f"{k}={v}" for k, v in ec.items())
        print(f"  {mark} {r['relation']:28s} trigger={trig:12s} written={written} edges=[{ec_str}]")


if __name__ == "__main__":
    main()
