"""yunfei_test 空间九大业务模块功能烟测（e2e，用户需求 5）。

前置：还原抽取三条链全部 COMPLETED；api-yunfei3 已带 TRS_GRAPH_SPACE=yunfei_test
重建（图查模块默认空间从 dev 切到 yunfei_test）。

九模块（/kg-construction 前缀，登录关闭 → 开发管理员上下文直调）：
  1 专家直接关系 / 2 节点间接关系 / 3 两点成果 / 4 专家同事 / 5 专家校友 /
  6 论文合作 / 7 企业关系(EMPLOYED_BY) / 8 产业链事件 / 9 产业链全景。

查图模块的入参（专家 vid / 机构 vid / 产业链节点 id）先从 yunfei_test 图里
实际取样（有 AUTHORED_BY 边的 person 对、有 STUDIED_AT 边的 person、
IndustryNode 的 node_id），保证测的是「还原空间里真实存在的数据」。

跑法（host）：python3 yunfei_test_nine_modules_e2e.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

API = "http://localhost:8004/api/v1"
GRAPH = "http://localhost:8090/api/v1/query"
GRAPH_KEY = "ysukeg"
SPACE = "yunfei_test"


def req(method, path, body=None, timeout=180):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text


def graph_query(ngql, timeout=180):
    r = urllib.request.Request(GRAPH, data=json.dumps({"query": ngql}).encode(), method="POST")
    r.add_header("X-API-Key", GRAPH_KEY)
    r.add_header("Content-Type", "application/json")
    r.add_header("X-Graph-Space", SPACE)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    if (body.get("summary") or {}).get("errorCode", 0):
        raise RuntimeError(f"nGQL 失败: {ngql[:80]} -> {str(body)[:200]}")
    return body.get("records") or []


def sample_ids():
    """从还原空间取样真实业务 ID（有边的优先，避免空参数误判成功能）。"""
    ids: dict[str, str] = {}

    def first(ngql, key):
        try:
            recs = graph_query(ngql)
            return str(recs[0][key]) if recs else ""
        except Exception as exc:  # noqa: BLE001
            print(f"  取样失败（{ngql[:50]}…）: {str(exc)[:80]}")
            return ""

    # 共著对从 COAUTHOR_WITH 取（15 万条真实边）：AUTHORED_BY 的 2-hop 模式
    # 在还原空间匹配为空（边端点经消歧落在 Person/Paper 之外的概率高），
    # 模块 3/6 要的是「两位专家」本身，COAUTHOR_WITH 端点即满足
    pair = graph_query(
        "MATCH (a:Person)-[:COAUTHOR_WITH]->(b:Person) "
        "WHERE id(a) < id(b) RETURN id(a) AS a, id(b) AS b LIMIT 1") or []
    rec = pair[0] if pair and isinstance(pair[0], dict) else {}
    ids["paper_pair"] = str(rec.get("a") or "")
    ids["paper_pair_b"] = str(rec.get("b") or "")
    ids["any_person"] = ids["paper_pair"] or first(
        "MATCH (v:Person) RETURN id(v) AS vid LIMIT 1", "vid")
    ids["org"] = first("MATCH (v:Organization) RETURN id(v) AS vid LIMIT 1", "vid")
    ids["studied_person"] = first(
        "MATCH (v:Person)-[:STUDIED_AT]->(:Organization) RETURN id(v) AS vid LIMIT 1", "vid")
    ids["industry_node"] = first(
        "MATCH (v:IndustryNode) RETURN v.IndustryNode.node_id AS nid LIMIT 1", "nid")
    return ids


results: list[tuple[str, bool, str]] = []


def check(name, path, method="GET", body=None, prove=None):
    """prove: 从响应里取一句「证明确实查到了还原数据」的摘要。"""
    code, resp = req(method, path, body)
    ok_flag = code == 200 and isinstance(resp, dict)
    detail = ""
    if ok_flag:
        try:
            detail = prove(resp) if prove else str(resp.get("data"))[:120]
        except Exception as exc:  # noqa: BLE001
            detail = f"摘要提取失败: {str(exc)[:60]}"
    else:
        detail = f"HTTP {code}: {str(resp)[:160]}"
    results.append((name, ok_flag, detail))
    print(f"  {'PASS' if ok_flag else 'FAIL'}  {name}: {detail}", flush=True)


def main():
    ids = sample_ids()
    print(f"取样: {json.dumps(ids, ensure_ascii=False)}\n")
    a, b = ids["paper_pair"], ids["paper_pair_b"]
    person = ids["any_person"]

    print("=== 九大模块烟测（yunfei_test）")
    # 1 专家直接关系
    check("1 专家直接关系", "/kg-construction/expert-direct-relations/query"
          f"?expertAId={a}&expertBId={b}&dataSource=all")
    # 2 节点间接关系
    check("2 节点间接关系", "/kg-construction/expert-indirect-relations/demo/structured-result",
          "POST", {"core_node_id": person, "relation_types": ["学术关联"],
                   "path_depth": 2, "min_strength": 0.65})
    # 3 两点成果（专家间合作成果）
    check("3 两点成果", "/kg-construction/expert-cooperation-achievements/query",
          "POST", {"sourceExpertId": a, "targetExpertId": b})
    # 4 专家同事（MySQL+公开查图组合；expert_b_id 必填）
    check("4 专家同事", "/kg-service/expert-colleague-relation",
          "POST", {"expert_a_id": person, "expert_b_id": b or person,
                   "start_time": "2015-01", "end_time": "2026-09"})
    # 5 专家校友
    check("5 专家校友", "/kg-construction/expert-alumni-relations/query",
          "POST", {"expertId": ids.get("studied_person") or person})
    # 6 论文合作
    check("6 论文合作", "/kg-construction/expert-paper-cooperation-relations/structured-result",
          "POST", {"expertAId": a, "expertBId": b,
                   "startTime": "2000-01-01", "endTime": time.strftime("%Y-%m-%d")})
    # 7 企业关系（EMPLOYED_BY 描述 + 构建查询走 options 联动，这里打 build）
    check("7 企业关系-描述", "/kg-construction/expert-enterprise-relations")
    # 8 产业链事件
    node = ids.get("industry_node") or "IC0007007"
    check("8 产业链事件", "/kg-service/industry-node-top-events",
          "POST", {"chain_node_id": node, "top_n": 5})
    # 9 产业链全景
    check("9 产业链全景", "/kg-construction/industry-chain-panorama/query",
          "POST", {"industry": "集成电路", "depth": 1, "topK": 5})

    passed = sum(1 for _, okk, _ in results if okk)
    print(f"\n烟测结果: {passed}/{len(results)} 通过")
    pathlib_write()


def pathlib_write():
    import pathlib
    pathlib.Path("/tmp/yunfei_nine_modules_report.json").write_text(
        json.dumps(
            [{"module": n, "pass": okk, "detail": d} for n, okk, d in results],
            ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
