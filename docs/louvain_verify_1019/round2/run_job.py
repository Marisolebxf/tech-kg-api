#!/usr/bin/env python3
"""round2 参数化作业驱动：submit → poll → result 摘要 → jobid 落盘。

用法：run_job.py <tag> <space> <labels csv> <maxIter> <internalIter> <tol> [--weighted <wcol>]
"""
import json, sys, time, urllib.request, urllib.error, pathlib

RUNNER = "http://<RUNNER-HOST>:8091"
OUT = pathlib.Path(__file__).parent

def http(method, path, body=None, timeout=60):
    req = urllib.request.Request(RUNNER + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:300]}

def main():
    tag, space, labels = sys.argv[1], sys.argv[2], sys.argv[3]
    params = {"maxIter": int(sys.argv[4]), "internalIter": int(sys.argv[5]), "tol": float(sys.argv[6]),
              "encodeId": True}
    body = {"algorithm": "louvain", "source": "nebula", "sink": "csv", "space": space,
            "labels": labels.split(","), "hasWeight": False, "partitionNum": 1, "parameters": params}
    if "--weighted" in sys.argv:
        wcol = sys.argv[sys.argv.index("--weighted") + 1]
        body["hasWeight"] = True
        body["weightCols"] = [wcol] * len(body["labels"])
    sub = http("POST", "/jobs", body)
    job = sub.get("jobId", "")
    print(f"[{tag}] submit: {str(sub)[:120]}")
    if not job:
        (OUT / f"{tag}.jobid").write_text("")
        sys.exit(1)
    (OUT / f"{tag}.jobid").write_text(job)
    for _ in range(120):
        time.sleep(5)
        st = http("GET", f"/jobs/{job}")
        if st.get("status") != "running":
            print(f"[{tag}] final: status={st.get('status')} exit={st.get('exitCode')} err={str(st.get('error'))[:200]}")
            break
    else:
        print(f"[{tag}] TIMEOUT still running"); sys.exit(2)
    res = http("GET", f"/jobs/{job}/result")
    rows = res.get("rows") or []
    print(f"[{tag}] count={res.get('count')}")
    comm = {}
    for r in rows:
        comm.setdefault(r.get("louvain") or list(r.values())[1], []).append(list(r.values())[0])
    for cid in sorted(comm, key=lambda c: min(comm[c])):
        m = sorted(comm[cid]); print(f"  community {cid}: n={len(m)} {m}")
    (OUT / f"{tag}_rows.json").write_text(json.dumps(rows, ensure_ascii=False))

if __name__ == "__main__":
    main()
