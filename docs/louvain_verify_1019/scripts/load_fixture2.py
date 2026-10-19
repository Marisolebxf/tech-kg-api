#!/usr/bin/env python3
"""重建隔离样例 v2：
- 大分量 = 双环8+桥（会经历「压缩后再合并」的多级 Louvain 轮次）
- K8 分量 = 16...K8 内部增益 1-56/m < tol → 全 singleton（回归对照组）
- 三颗星（3/4/2 点）= 完全内部化的孤立社区（bug 触发器）
"""
import json, time, urllib.request, urllib.error

SP = "graphalgo_lv_1019"
W = "http://localhost:8090/api/v1/query/write"
R = "http://localhost:8090/api/v1/query/read"

def call(url, query, space=SP, timeout=60):
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "X-API-Key": "<REDACTED-API-KEY>", "X-Graph-Space": space})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:200]}

print("drop:", str(call(W, "DROP SPACE IF EXISTS graphalgo_lv_1019", space="entity_binding_demo"))[:120])
time.sleep(12)
print("create:", str(call(W, "CREATE SPACE graphalgo_lv_1019 (vid_type = FIXED_STRING(64))", space="entity_binding_demo"))[:120])
time.sleep(12)
print("tag:", str(call(W, "CREATE TAG IF NOT EXISTS node()"))[:120])
print("edge:", str(call(W, "CREATE EDGE IF NOT EXISTS link()"))[:120])
time.sleep(8)

verts = [f"a{i}" for i in range(1, 9)] + [f"b{i}" for i in range(1, 9)] + \
        [f"c{i}" for i in range(1, 9)] + \
        ["st1c", "st1l1", "st1l2", "st2c", "st2l1", "st2l2", "st2l3", "st3c", "st3l1"]
edges = []
for group in ("a", "b"):  # 环 a1-a2-...-a8-a1
    for i in range(1, 8):
        edges.append((f"{group}{i}", f"{group}{i+1}"))
    edges.append((f"{group}8", f"{group}1"))
edges.append(("a1", "b1"))  # 桥
for i in range(1, 9):       # K8
    for j in range(i + 1, 9):
        edges.append((f"c{i}", f"c{j}"))
edges += [("st1c", "st1l1"), ("st1c", "st1l2")]
edges += [("st2c", "st2l1"), ("st2c", "st2l2"), ("st2c", "st2l3")]
edges += [("st3c", "st3l1")]
print(f"vertices={len(verts)} edges={len(edges)} m={len(edges)} (双环16+桥1+K8=28+星6)")

print("ins v:", str(call(W, " ".join(f'INSERT VERTEX node() VALUES "{v}":();' for v in verts)))[:120])
print("ins e:", str(call(W, " ".join(f'INSERT EDGE link() VALUES "{s}"->"{d}":();' for s, d in edges)))[:120])
print("idx:", str(call(W, "CREATE EDGE INDEX IF NOT EXISTS link_idx ON link()"))[:120])
r = call(W, "REBUILD EDGE INDEX link_idx")
while "http" in r:
    time.sleep(8); r = call(W, "REBUILD EDGE INDEX link_idx")
print("rebuild:", str(r)[:120])
status = None
for _ in range(30):
    time.sleep(2)
    rows = [x for x in call(R, "SHOW EDGE INDEX STATUS").get("records", []) if x.get("Name") == "link_idx"]
    status = rows[0].get("Index Status") if rows else None
    if status == "FINISHED":
        break
print("index:", status, "edges:", call(R, 'LOOKUP ON link YIELD edge AS e | YIELD count(*) AS c').get("records"))
