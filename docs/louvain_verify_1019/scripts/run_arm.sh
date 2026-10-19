#!/bin/bash
# 用法: run_arm.sh <标签> —— 向隔离 runner(8095) 提交 louvain 作业并等结果
set -u
TAG=$1
RUNNER=http://<RUNNER-HOST>:8095
JOB=$(curl -s -X POST $RUNNER/jobs -H 'Content-Type: application/json' -d '{
  "algorithm":"louvain","source":"nebula","sink":"csv","space":"graphalgo_lv_1019",
  "labels":["link"],"hasWeight":false,"partitionNum":1,
  "parameters":{"maxIter":20,"internalIter":10,"tol":0.5,"encodeId":true}}' | python3 -c 'import json,sys;print(json.load(sys.stdin).get("jobId",""))')
echo "[$TAG] jobId=$JOB"
if [ -z "$JOB" ]; then echo "[$TAG] submit failed"; exit 1; fi
for i in $(seq 1 120); do
  sleep 5
  ST=$(curl -s $RUNNER/jobs/$JOB | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("status",""),d.get("exitCode",""))')
  set -- $ST
  if [ "$1" != "running" ]; then echo "[$TAG] status=$ST"; break; fi
done
echo "$JOB" > ~/louvain-verify-1019/runner-data/${TAG}.jobid
curl -s $RUNNER/jobs/$JOB/result | python3 -c '
import json,sys
d=json.load(sys.stdin)
rows=d.get("rows") or []
print("count:",d.get("count"))
comm={}
for r in rows: comm.setdefault(r.get("louvain") or r.get("communityId") or list(r.values())[1], []).append(list(r.values())[0])
for cid in sorted(comm, key=lambda c: min(comm[c])):
    members=sorted(comm[cid]); print(f"  community {cid}: n={len(members)} {members}")
'
