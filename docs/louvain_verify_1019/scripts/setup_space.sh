#!/bin/bash
# 隔离验证空间：独立空间 graphalgo_lv_1019 + 小连通分量样例（BTN 星型）+ 大分量（K8+K8+桥）
set -u
API=http://localhost:8090/api/v1/query
H1="X-API-Key: <REDACTED-API-KEY>"
H2="X-Graph-Space: entity_binding_demo"
H3="X-Graph-Space: graphalgo_lv_1019"
SP=graphalgo_lv_1019

q() { # q <space-header> <query>
  curl -s --max-time 30 -X POST $API/write -H "Content-Type: application/json" -H "$1" -H "$H1" -d "{\"query\": $2}"
}

echo "--- create space"
q "$H2" '"CREATE SPACE IF NOT EXISTS graphalgo_lv_1019 (vid_type = FIXED_STRING(64))"' | head -c 300; echo
sleep 12   # CREATE SPACE 传播延迟

echo "--- ddl"
q "$H3" '"CREATE TAG IF NOT EXISTS node()"' | head -c 200; echo
q "$H3" '"CREATE EDGE IF NOT EXISTS link()"' | head -c 200; echo
sleep 8

echo "--- vertices"
VS=""
for v in a1 a2 a3 a4 a5 a6 a7 a8 b1 b2 b3 b4 b5 b6 b7 b8 st1c st1l1 st1l2 st2c st2l1 st2l2 st2l3 st3c st3l1; do
  VS="$VS INSERT VERTEX node() VALUES \"$v\":();"
done
q "$H3" "\"$VS\"" | head -c 200; echo

echo "--- edges: K8(a) + K8(b) + bridge a1-b1 + 三颗星"
ES=""
for i in 1 2 3 4 5 6 7 8; do for j in $(seq $((i+1)) 8); do ES="$ES INSERT EDGE link() VALUES \"a$i\"->\"a$j\":();"; ES="$ES INSERT EDGE link() VALUES \"b$i\"->\"b$j\":();"; done; done
ES="$ES INSERT EDGE link() VALUES \"a1\"->\"b1\":();"
ES="$ES INSERT EDGE link() VALUES \"st1c\"->\"st1l1\":(); INSERT EDGE link() VALUES \"st1c\"->\"st1l2\":();"
ES="$ES INSERT EDGE link() VALUES \"st2c\"->\"st2l1\":(); INSERT EDGE link() VALUES \"st2c\"->\"st2l2\":(); INSERT EDGE link() VALUES \"st2c\"->\"st2l3\":();"
ES="$ES INSERT EDGE link() VALUES \"st3c\"->\"st3l1\":();"
q "$H3" "\"$ES\"" | head -c 300; echo

echo "--- verify counts"
curl -s --max-time 30 -X POST $API/read -H "Content-Type: application/json" -H "$H3" -H "$H1" -d '{"query":"LOOKUP ON link YIELD edge AS e | YIELD count(*) AS c"}' | head -c 200; echo
