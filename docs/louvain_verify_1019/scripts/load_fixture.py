#!/usr/bin/env python3
"""隔离空间 graphalgo_lv_1019 装载 Louvain 验证样例：K8+K8+桥（16 点大分量）+ 三颗星（9 点小分量）。"""
import json, time, urllib.request

API = "http://localhost:8090/api/v1/query/write"
READ = "http://localhost:8090/api/v1/query/read"
SP = "graphalgo_lv_1019"

def call(url, query, space=SP):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "X-API-Key": "<REDACTED-API-KEY>", "X-Graph-Space": space})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

verts = [f"a{i}" for i in range(1, 9)] + [f"b{i}" for i in range(1, 9)] + \
        ["st1c", "st1l1", "st1l2", "st2c", "st2l1", "st2l2", "st2l3", "st3c", "st3l1"]
edges = []
for group in ("a", "b"):
    for i in range(1, 9):
        for j in range(i + 1, 9):
            edges.append((f"{group}{i}", f"{group}{j}"))
edges.append(("a1", "b1"))                      # 桥
edges += [("st1c", "st1l1"), ("st1c", "st1l2")]          # 3 点星
edges += [("st2c", "st2l1"), ("st2c", "st2l2"), ("st2c", "st2l3")]  # 4 点星
edges += [("st3c", "st3l1")]                    # 2 点分量
print(f"vertices={len(verts)} edges={len(edges)} (K8x2=56, bridge=1, stars=6)")

ins_v = " ".join(f'INSERT VERTEX node() VALUES "{v}":();' for v in verts)
ins_e = " ".join(f'INSERT EDGE link() VALUES "{s}"->"{d}":();' for s, d in edges)
print("insert vertices:", str(call(API, ins_v))[:150])
print("insert edges:", str(call(API, ins_e))[:150])

# 零属性索引（对齐真实空间的 schema 同步索引，算法读边可用）
print("create indexes:", str(call(API, "CREATE EDGE INDEX IF NOT EXISTS link_idx ON link()"))[:150])
print("rebuild:", str(call(API, "REBUILD EDGE INDEX link_idx"))[:150])
for _ in range(30):
    time.sleep(2)
    st = call(READ, "SHOW EDGE INDEX STATUS")
    rows = [r for r in st.get("records", []) if r.get("Name") == "link_idx"]
    status = rows[0].get("Index Status") if rows else None
    if status == "FINISHED":
        break
print("index status:", status)
cnt = call(READ, 'LOOKUP ON link YIELD edge AS e | YIELD count(*) AS c')
print("edge count:", cnt.get("records"))
