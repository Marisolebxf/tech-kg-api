# 周四演示备忘（space=`dev`）

演示项目 VID：`project_fake-zh-proj-001`

## Studio

1. 打开 Studio（本机映射通常 `http://localhost:7002` 或实验室 `http://211.81.248.211:7002`）
2. 连接 Graph（本机 `localhost:9677` / 实验室 `211.81.248.211:9677`），用户 `root`
3. 选择图空间 **`dev`**
4. 依次执行 `script/ngql/project_accept_demo.ngql` 中的 4 条查询

## 已验收结果（2026-07-21 BATCH_20260721_DEMO）

| 查询 | 结果摘要 |
|------|----------|
| FETCH Project | title=面向知识图谱的多源异构科技数据融合方法研究；funded_amount=80；patents_count=1 |
| LEADS / FUNDED_BY | Person 桩（张伟）+ Organization 桩（清华大学） |
| HAS_KEYWORD | 3 个 Keyword（知识图谱 / 数据融合 / 科技情报） |
| OUTPUT_OF REVERSELY | Paper 桩 + `patent_CN201811394750.6` |

## 重跑（如需）

```bash
cd backend
TRS_GRAPH_SPACE=dev TRS_GRAPH_API_KEY=<key> \
  uv run python -m script.load_project_graph --id-prefix fake- --ingest-batch BATCH_DEMO
```
