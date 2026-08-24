#!/usr/bin/env python3
"""批量通过 API 流程测试 entity 抽取脚本：模拟前端用户操作。

对每个 entity：
1. 若 techkg_control 已有同名 schema → DELETE（含引用关系级联）
2. 若 dev2 已有同名 TAG → DROP TAG
3. POST /schemas/entities 带业务属性（auto-provenance 自动补 11 个溯源）
4. PUT /schemas/{id}/script 绑定 dual-mode 脚本
5. POST /workflow-system/definitions/schema-{name}/execute payload {limit:2}
6. 等 COMPLETED + 验证 dev2 图有节点

用法：
    python3 dev2_api_flow_batch.py [--entity NAME] [--skip-cleanup]
    不带 --entity 跑全部 13 个（除 project/datasource 已测过）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

API = "http://localhost:8002/api/v1"
GRAPH = "http://localhost:8090/api/v1/query/write"
GRAPH_HEADERS = {"X-API-Key": "ysukeg", "X-Graph-Space": "dev2", "Content-Type": "application/json"}

# 13 个 entity（除 project/datasource 已测过）的业务属性集，来自 mapper introspection。
# 11 个溯源属性由 SCHEMA_AUTO_PROVENANCE 自动注入，不在此列。
ENTITY_PROPS: dict[str, list[str]] = {
    "person": ["avatar","bio_zh","biography","citation_nums","education_background_date","education_background_degree_en","education_background_degree_zh","education_background_institution_en","education_background_institution_zh","email","h_index","is_academician","name_en","name_zh","organization_id","paper_nums","research_fields","scholar_org","scholar_status","source","work_experience_date","work_experience_department_en","work_experience_department_zh","work_experience_institution_en","work_experience_institution_zh","work_experience_position_en","work_experience_position_zh","extra_json"],
    "organization": ["address","area","capital_currency","city","country","country_code","description","email","external_id","founded_year","industry_class","legal_rep","listed_date","listing_status","main_products","name_cn","name_en","org_id","org_kind","org_size","org_type","organization_id","phone","postal_code","province","registered_capital","stock_code","stock_noun","stock_type","extra_json"],
    "paper": ["doi","publication_name","publication_year","source","title_en","title_zh","extra_json"],
    "journal": ["name_en","name_zh","issn","country","extra_json"],
    "patent": ["abstract_zh","anticipated_expiration","application_date","application_kind","application_number","citation_nums","cited_by_nums","country","country_code","create_time","db_source","further_cpc","further_ipcr","grant_date","granted_number","keywords","language","main_cpc","main_ipcr","organization_base","organization_id","patent_id","patent_value","publication_date","publication_number","simple_family_number","status","title_en","title_original","title_zh","update_time","extra_json"],
    "patent_family": ["family_number","organization_base","organization_id","extra_json"],
    "keyword": ["keyword","extra_json"],
    "report": ["abstract","title","extra_json"],
    "event": ["amount","case_cause","case_no","content","currency","event_type","occur_date","organization_id","raw_id","title","extra_json"],
    "news": ["content","organization_id","original_url","release_date","title","extra_json"],
    "product": ["category","description","name","organization_id","extra_json"],
    "industry_chain": ["chain_code","chain_name","extra_json"],
    "industry_node": ["level","node_id","node_imp_level","node_name","node_path","node_seq","node_stage","node_type","extra_json"],
}

# entity name → TAG name (PascalCase)
ENTITY_TAG: dict[str, str] = {
    "person": "Person", "organization": "Organization", "paper": "Paper",
    "journal": "Journal", "patent": "Patent", "patent_family": "PatentFamily",
    "keyword": "Keyword", "report": "Report", "event": "Event", "news": "News",
    "product": "Product", "industry_chain": "IndustryChain", "industry_node": "IndustryNode",
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


def _find_schema_id(name: str) -> str | None:
    code, resp = _req("GET", f"{API}/schema-management/schemas?limit=200")
    if not isinstance(resp, dict):
        return None
    for s in resp.get("data", {}).get("items", []):
        if s.get("name") == name:
            return s["id"]
    return None


def _find_referencing_relations(entity_schema_id: str) -> list[str]:
    """直接查 techkg_control 找引用此 entity 的 relations。"""
    import subprocess
    out = subprocess.check_output([
        "docker", "exec", "tech-kg-temporal-mysql-dev2", "mysql", "-uroot", "-ptemporal",
        "techkg_control", "-N", "-e",
        f"SELECT id FROM kg_schema_definition WHERE kind='relation' AND (source_schema_id='{entity_schema_id}' OR target_schema_id='{entity_schema_id}');"
    ], text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _delete_schema(schema_id: str) -> bool:
    code, resp = _req("DELETE", f"{API}/schema-management/schemas/{schema_id}")
    return code == 200


def _drop_tag(tag_name: str) -> bool:
    r = _nGQL(f"DROP TAG IF EXISTS {tag_name};")
    return "error" not in r


def _create_schema(name: str, label: str, props: list[str]) -> str | None:
    properties = [{"name": p, "dataType": "string", "required": False, "category": "core", "rule": ""}
                   for p in props]
    body = {
        "schemaKey": name.replace("_", "-"),
        "name": ENTITY_TAG[name],
        "label": label,
        "description": f"{label} 实体（API 流程测试）",
        "identityKey": "id",
        "properties": properties,
        "isCore": False,
        "version": "v2.1",
    }
    code, resp = _req("POST", f"{API}/schema-management/schemas/entities",
                       {"Content-Type": "application/json"},
                       json.dumps(body).encode())
    if code not in (200, 201):
        print(f"    POST schema FAIL {code}: {str(resp)[:200]}")
        return None
    return resp["data"]["id"]


def _bind_script(schema_id: str, script_path: str) -> bool:
    # multipart/form-data via urllib is painful; use curl via subprocess
    import subprocess
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


def _trigger_and_wait(workflow_def_id: str, limit: int = 2, wait_s: int = 25) -> tuple[str, dict | None]:
    body = json.dumps({"payload": {"limit": limit}}).encode()
    code, resp = _req("POST", f"{API}/workflow-system/definitions/{workflow_def_id}/execute",
                       {"Content-Type": "application/json"}, body)
    if code != 200:
        return f"trigger_fail_{code}", None
    exec_id = resp["data"]["id"]
    time.sleep(wait_s)
    code, resp = _req("GET", f"{API}/workflow-system/executions/{exec_id}")
    if not isinstance(resp, dict):
        return "status_unknown", None
    d = resp.get("data", {})
    out = d.get("output")
    if isinstance(out, str):
        try:
            out = json.loads(out)
        except Exception:
            out = {"_raw": out}
    return d.get("status", "unknown"), out


def _count_nodes(tag: str) -> int:
    # 用 REST get_nodes_by_label 查（不依赖 TAG 索引，比 nGQL MATCH 可靠）
    code, resp = _req("GET", f"http://localhost:8090/api/v1/nodes/label/{tag}?limit=1",
                       {"X-API-Key": "ysukeg", "X-Graph-Space": "dev2"})
    if not isinstance(resp, dict):
        return 0
    return resp.get("page", {}).get("total", 0)


def test_entity(name: str, *, skip_cleanup: bool = False) -> dict:
    tag = ENTITY_TAG[name]
    print(f"\n=== {name} (TAG={tag}) ===")
    result = {"entity": name, "tag": tag, "steps": {}}

    # 1. find existing schema + relations, delete
    if not skip_cleanup:
        existing_id = _find_schema_id(tag)
        if existing_id:
            refs = _find_referencing_relations(existing_id)
            for rid in refs:
                _delete_schema(rid)
            _delete_schema(existing_id)
            print(f"  step1 delete schema+{len(refs)} refs: done")
            # 2. drop TAG (allow propagation)
            time.sleep(2)
            _drop_tag(tag)
            print(f"  step2 drop TAG: done")
            time.sleep(5)  # NebulaGraph DDL 传播延迟，DROP TAG 后等几秒再 CREATE
            result["steps"]["delete"] = "ok"
        else:
            print(f"  step1/2: no existing schema, skip")
            result["steps"]["delete"] = "skip"

    # 3. POST schema
    schema_id = _create_schema(name, tag, ENTITY_PROPS[name])
    if not schema_id:
        result["steps"]["create"] = "FAIL"
        return result
    print(f"  step3 POST schema: id={schema_id}")
    result["schema_id"] = schema_id
    result["steps"]["create"] = "ok"

    # 4. bind script
    script_path = f"backend/script/entity_extractors_one_entity/{name}_entity.py"
    ok = _bind_script(schema_id, script_path)
    print(f"  step4 bind script: {'ok' if ok else 'FAIL'}")
    result["steps"]["bind_script"] = "ok" if ok else "FAIL"
    if not ok:
        return result

    # 5. trigger + wait. workflow_def_id = schema-{schemaKey}，schemaKey 用 dash
    wf_id = f"schema-{name.replace('_', '-')}"
    status, out = _trigger_and_wait(wf_id)
    srcs = (out or {}).get("sources", {}) if isinstance(out, dict) else {}
    total_written = sum(v.get("written", 0) for v in srcs.values()) if isinstance(srcs, dict) else 0
    print(f"  step5 trigger: status={status} written={total_written}")
    result["steps"]["trigger"] = status
    result["written"] = total_written

    # 6. verify dev2 graph
    cnt = _count_nodes(tag)
    print(f"  step6 dev2 graph {tag} count={cnt}")
    result["dev2_node_count"] = cnt
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--entity", help="只测一个 entity")
    p.add_argument("--skip-cleanup", action="store_true", help="跳过 DELETE+DROP 步骤")
    args = p.parse_args()

    names = [args.entity] if args.entity else list(ENTITY_PROPS.keys())
    results = []
    for name in names:
        try:
            r = test_entity(name, skip_cleanup=args.skip_cleanup)
            results.append(r)
        except Exception as e:
            print(f"  EXCEPTION: {e!r}")
            results.append({"entity": name, "error": repr(e)})

    print("\n=== SUMMARY ===")
    for r in results:
        if "error" in r:
            print(f"  {r['entity']:20s} EXCEPTION: {r['error'][:80]}")
            continue
        ok = (r.get("steps", {}).get("trigger") == "COMPLETED"
              and r.get("dev2_node_count", 0) > 0)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {r['entity']:20s} trigger={r.get('steps',{}).get('trigger','?'):12s} written={r.get('written','?')} dev2_nodes={r.get('dev2_node_count','?')}")


if __name__ == "__main__":
    main()
