#!/usr/bin/env python3
"""单关系复刻空间 graphalgo_lv_sr_1019：
link_ab=双环+桥（17 边/16 点，大分量）；link_pl=三颗星 3/4/2（6 边/9 点，小分量）；
link_none=零边（空输入边界）。对应平台「单关系选择」验收场景的隔离复刻。"""
import json, time, urllib.request
NEW = "graphalgo_lv_sr_1019"
W = "http://localhost:8090/api/v1/query/write"; R = "http://localhost:8090/api/v1/query/read"
def call(url, query, space=NEW, timeout=90):
    req = urllib.request.Request(url, data=json.dumps({"query": query}).encode(), headers={
        "Content-Type": "application/json", "X-API-Key": "<REDACTED-API-KEY>", "X-Graph-Space": space})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e: return {"http": e.code, "body": e.read().decode()[:150]}
call(W, "DROP SPACE IF EXISTS graphalgo_lv_sr_1019", space="entity_binding_demo"); time.sleep(12)
call(W, f"CREATE SPACE {NEW} (vid_type = FIXED_STRING(64))", space="entity_binding_demo"); time.sleep(12)
for q in ("CREATE TAG IF NOT EXISTS node()","CREATE EDGE IF NOT EXISTS link_ab()",
          "CREATE EDGE IF NOT EXISTS link_pl()","CREATE EDGE IF NOT EXISTS link_none()"):
    call(W, q)
for _ in range(30):
    if {"link_ab","link_pl","link_none"} <= set(r.get("Name") for r in call(R, "SHOW EDGES").get("records", [])): break
    time.sleep(3)
verts = [f"a{i}" for i in range(1,9)] + [f"b{i}" for i in range(1,9)] + \
        ["st1c","st1l1","st1l2","st2c","st2l1","st2l2","st2l3","st3c","st3l1"]
ab = []
for g in ("a","b"):
    for i in range(1,8): ab.append((f"{g}{i}", f"{g}{i+1}"))
    ab.append((f"{g}8", f"{g}1"))
ab.append(("a1","b1"))
pl = [("st1c","st1l1"),("st1c","st1l2"),("st2c","st2l1"),("st2c","st2l2"),("st2c","st2l3"),("st3c","st3l1")]
def ins(label, pairs, q=None):
    q = q or " ".join(f'INSERT EDGE {label}() VALUES "{s}"->"{d}":();' for s,d in pairs)
    for attempt in range(1,8):
        r = call(W, q); ok = "http" not in r
        print(f"{label} attempt {attempt}: {'OK' if ok else r.get('body','')[:60]}")
        if ok: return
        time.sleep(8)
ins("verts", [], " ".join(f'INSERT VERTEX node() VALUES "{v}":();' for v in verts))
ins("link_ab", ab); ins("link_pl", pl)
for idx, lbl in (("ab_idx","link_ab"),("pl_idx","link_pl"),("none_idx","link_none")):
    call(W, f"CREATE EDGE INDEX IF NOT EXISTS {idx} ON {lbl}()")
time.sleep(3)
for idx in ("ab_idx","pl_idx","none_idx"):
    r = call(W, f"REBUILD EDGE INDEX {idx}")
    while "http" in r: time.sleep(8); r = call(W, f"REBUILD EDGE INDEX {idx}")
    for _ in range(30):
        time.sleep(2)
        rows = [x for x in call(R, "SHOW EDGE INDEX STATUS").get("records", []) if x.get("Name")==idx]
        if rows and rows[0].get("Index Status")=="FINISHED": break
    print(idx, rows[0].get("Index Status") if rows else "?")
for lbl in ("link_ab","link_pl","link_none"):
    print(lbl, call(R, f'LOOKUP ON {lbl} YIELD edge AS e | YIELD count(*) AS c').get("records"))
