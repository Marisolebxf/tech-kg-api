# 专利抽取脚本工作流封装

## 背景

主分支已有 Python 工作流接口：`POST /api/v1/workflow-system/definitions/python` 上传脚本（要求定义 `workflow(payload)` 函数）→ Temporal `kg.custom.python` 工作流 → `execute_python_script` activity 以子进程方式执行。专利的实体/关系抽取脚本（`load_patent_graph.py`、`load_patent_relations.py`）原本是独立可导入函数，未接入该接口。

本次把两个 loader 封装为工作流可调用的薄包装脚本，分别对应"专利实体脚本上传"和"专利关系脚本上传"两个入口。

## 改动文件（仅新增，未改任何现有代码）

| 文件 | 说明 |
|---|---|
| `backend/script/patent_entity_workflow.py` | `workflow(payload)` → 调 `load_patent_graph.load_patents(batch_size)`，写入 Patent 实体及属性 |
| `backend/script/patent_relation_workflow.py` | `workflow(payload)` → 调 `load_patent_relations.load(apply, replace, use_vector, ...)`，一次处理全部 5 种专利关系 |
| `backend/tests/unit/test_patent_entity_workflow.py` | 5 用例 |
| `backend/tests/unit/test_patent_relation_workflow.py` | 6 用例 |

## 设计要点

- **统一入口 `workflow(payload)`**：函数名对齐工作流接口默认 `function_name`。
- **sys.path 自举**：`execute_python_script` 给子进程的 `PYTHONPATH` 只含脚本所在目录（`WORKFLOW_SCRIPT_DIR`，通常 /tmp），不含 backend 根。包装脚本通过 `_backend_root()` 定位 backend 根（优先 `TECH_KG_BACKEND_ROOT` env → 沿 `__file__` 父目录 → `Path.cwd()` 兜底），insert 到 `sys.path[0]`，才能 `from script.load_patent_graph import load_patents`。实测 worker 从 backend/ 启动时 `Path.cwd()` 兜底生效。
- **纯委托**：只做参数适配 + 结果 JSON 化（元组→命名 dict，`Counter`→`dict`），不复制/不修改抽取与建图逻辑。
- **失败向上抛出**：单阶段异常先记阶段信息到 stderr 再 re-raise 原异常，子进程非零退出 → activity 抛 `RuntimeError(stderr)` → Temporal 识别 FAILED 并按平台策略重试；不吞异常返回 `ok=False`。
- **无 stage 参数**：两个脚本各自单一职责；关系脚本一次执行原 loader 的全部 5 种边（`INVENTED_BY`/`APPLIED_BY`/`OWNED_BY`/`CITES`/`OUTPUT_OF`），不拆分、不过滤。

## payload 契约

### `patent_entity_workflow.py`
```json
{"batch_size": 50}
```
返回 `{"ok": true, "stats": {"patents": N, "keywordRefs": N, "hasKeywordEdges": N}}`。

### `patent_relation_workflow.py`
```json
{"apply": false, "replace": false, "use_vector": true,
 "vector_threshold": 0.88, "vector_margin": 0.08, "vector_top_k": 20,
 "vector_state_dir": null, "review_output": null}
```
默认值与 `load` 签名一致。返回 `{"ok": true, "stats": {<Counter>}}`。

## 联调验证（主分支现有工作流接口，未改公共平台）

起隔离 API+worker（独立 task queue/DB/script dir），上传脚本 → 执行 → 查 Temporal history 的 activity 返回值：

| 脚本 | payload | Temporal 状态 | 实际返回 |
|---|---|---|---|
| `patent_entity_workflow.py` | `{"batch_size":50}` | COMPLETED | `{"ok":true,"stats":{"patents":2000,"keywordRefs":9949,"hasKeywordEdges":9949}}` |
| `patent_relation_workflow.py` | `{"apply":false}` | COMPLETED | `{"ok":true,"stats":{"INVENTED_BY:review":2000,"APPLIED_BY:review":2000,"OWNED_BY:review":2000,"CITES:unmatched_target":13250,"OUTPUT_OF:unmatched_or_ambiguous_patent":2514,"review_records":6000}}` |

单测：`PYTHONPATH=. uv run pytest tests/unit/test_patent_entity_workflow.py tests/unit/test_patent_relation_workflow.py -v` → 11/11 通过。

## 已知公共平台限制（未修改公共平台）

1. 执行记录 `GET /workflow-system/executions/{id}` 恒为 `RUNNING`——公共接口无状态回写；实际状态需查 Temporal UI(8233) history。
2. `execute_python_script` 子进程 60s 超时为公共接口既有行为；本次 2000 专利实体灌图在时限内完成。
