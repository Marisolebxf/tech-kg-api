#!/usr/bin/env bash
# 批量上传 + 触发 dual-mode ETL 脚本作为 kg.custom.python 工作流。
# 用法：bash dev2_upload_and_trigger.sh [upload|trigger|verify]
# 默认（无参）：跑完整 upload → trigger → verify 三步。

set -uo pipefail

API="${API:-http://localhost:8002/api/v1}"

ENTITY_DIR="backend/script/entity_extractors_one_entity"
RELATION_DIR="backend/script/relation_extractors_one_relation"

# 共享模块（非脚本，跳过）
ENTITY_SKIP="__init__.py|common.py|mappers.py|org_catalog.py"
RELATION_SKIP="__init__.py|common.py|catalog.py|org_edges.py|patent_matching.py|resolvers.py"

upload_one() {
  local file="$1" def_id="$2" name="$3"
  local resp
  resp=$(curl -sS -m 30 -X POST "$API/workflow-system/definitions/python" \
    -F "file=@$file" \
    -F "function_name=workflow" \
    -F "definition_id=$def_id" \
    -F "name=$name" \
    -F "timeoutSeconds=300" 2>&1)
  local code msg
  code=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code','?'))" 2>/dev/null || echo "ERR")
  msg=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('msg','?')[:80])" 2>/dev/null || echo "$resp")
  printf "  %-40s %s | %s\n" "$def_id" "$code" "$msg"
}

trigger_one() {
  local def_id="$1"
  local resp exec_id
  resp=$(curl -sS -m 15 -X POST "$API/workflow-system/definitions/$def_id/execute" \
    -H "Content-Type: application/json" -d '{"payload": {"limit": 1, "dry_run": true}}' 2>&1)
  exec_id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('id',''))" 2>/dev/null)
  if [ -z "$exec_id" ]; then
    printf "  %-40s TRIGGER_FAIL: %s\n" "$def_id" "$(echo "$resp" | head -c 100)"
    return
  fi
  sleep 6  # 大部分 dry-run < 5s 完成
  local status output
  status=$(curl -sS -m 5 "$API/workflow-system/executions/$exec_id" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('status','?'))" 2>/dev/null)
  output=$(curl -sS -m 5 "$API/workflow-system/executions/$exec_id" | python3 -c "
import sys,json
d=json.load(sys.stdin).get('data',{})
out=d.get('output') or {}
if isinstance(out,str):
    import json as j
    try: out=j.loads(out)
    except: pass
srcs=out.get('result',{}).get('sources') or out.get('sources') or {}
tot=sum(v.get('scanned',0) for v in srcs.values()) if isinstance(srcs,dict) else 0
print(f\"scanned_total={tot}\")
" 2>/dev/null)
  printf "  %-40s %s | %s\n" "$def_id" "$status" "$output"
}

upload_all() {
  echo "=== upload entity scripts ==="
  for f in "$ENTITY_DIR"/*_entity.py; do
    base=$(basename "$f" .py)
    def_id="py-entity-${base%_entity}"
    name="Entity: ${base%_entity}"
    upload_one "$f" "$def_id" "$name"
  done
  echo "=== upload relation scripts ==="
  for f in "$RELATION_DIR"/*_relation.py; do
    base=$(basename "$f" .py)
    def_id="py-relation-${base%_relation}"
    name="Relation: ${base%_relation}"
    upload_one "$f" "$def_id" "$name"
  done
}

trigger_all() {
  echo "=== trigger entity workflows (limit=1, dry_run=true) ==="
  for f in "$ENTITY_DIR"/*_entity.py; do
    base=$(basename "$f" .py)
    def_id="py-entity-${base%_entity}"
    trigger_one "$def_id"
  done
  echo "=== trigger relation workflows (limit=1, dry_run=true) ==="
  for f in "$RELATION_DIR"/*_relation.py; do
    base=$(basename "$f" .py)
    def_id="py-relation-${base%_relation}"
    trigger_one "$def_id"
  done
}

verify_clean_state() {
  echo "=== /workflow-system/definitions count ==="
  curl -sS -m 5 "$API/workflow-system/definitions?limit=200" | python3 -c "
import sys,json
d=json.load(sys.stdin)['data']
print(f\"total={d['total']}\")
for i in d['items']:
    print(f\"  {i['id']:40s} type={i['workflowType']:25s} source={i['sourceKind']}\")
" 2>/dev/null
}

case "${1:-all}" in
  upload) upload_all ;;
  trigger) trigger_all ;;
  verify) verify_clean_state ;;
  all) upload_all; echo; trigger_all ;;
  *) echo "usage: $0 [upload|trigger|verify|all]"; exit 1 ;;
esac
