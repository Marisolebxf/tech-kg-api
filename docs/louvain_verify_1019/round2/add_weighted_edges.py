#!/usr/bin/env python3
"""在 graphalgo_lv_1019 追加非负权边型 wlink(w int)：环/桥=2、K8=1、星=1。
先跑 load_fixture2.py（无权 link + 33 点），再跑本脚本。DDL 传播竞态已按重试处理。"""
import json, time, urllib.request
SP = "graphalgo_lv_1019"
W = "http://localhost:8090/api/v1/query/write"; R = "http://localhost:8090/api/v1/query/read"
def call(url, query, timeout=60):
    req = urllib.request.Request(url, data=json.dumps({"query": query}).encode(), headers={
        "Content-Type": "application/json", "X-API-Key": "<REDACTED-API-KEY>", "X-Graph-Space": SP})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e: return {"http": e.code, "body": e.read().decode()[:150]}
edges = []
for g in ("a","b"):
    for i in range(1,8): edges.append((f"{g}{i}", f"{g}{i+1}", 2))
    edges.append((f"{g}8", f"{g}1", 2))
edges.append(("a1","b1",2))
for i in range(1,9):
    for j in range(i+1,9): edges.append((f"c{i}", f"c{j}", 1))
edges += [("st1c","st1l1",1),("st1c","st1l2",1),("st2c","st2l1",1),("st2c","st2l2",1),("st2c","st2l3",1),("st3c","st3l1",1)]
print("ddl:", str(call(W, "CREATE EDGE IF NOT EXISTS wlink(w int)"))[:80])
for _ in range(20):
    if "wlink" in [r.get("Name") for r in call(R, "SHOW EDGES").get("records", [])]: break
    time.sleep(3)
ins_w = " ".join(f'INSERT EDGE wlink(w) VALUES "{s}"->"{d}":({w});' for s,d,w in edges)
for attempt in range(1, 8):
    r = call(W, ins_w); ok = "http" not in r
    print(f"ins attempt {attempt}: {'OK' if ok else r.get('body','')[:60]}")
    if ok: break
    time.sleep(8)
call(W, "CREATE EDGE INDEX IF NOT EXISTS wlink_idx ON wlink(w)"); time.sleep(3)
r = call(W, "REBUILD EDGE INDEX wlink_idx")
while "http" in r: time.sleep(8); r = call(W, "REBUILD EDGE INDEX wlink_idx")
for _ in range(30):
    time.sleep(2)
    rows = [x for x in call(R, "SHOW EDGE INDEX STATUS").get("records", []) if x.get("Name")=="wlink_idx"]
    if rows and rows[0].get("Index Status") == "FINISHED": break
print("wlink edges:", call(R, 'LOOKUP ON wlink YIELD edge AS e | YIELD count(*) AS c').get("records"))
