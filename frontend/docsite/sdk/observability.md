# 数据访问溯源（access report）

> 来源：`backend/sdk/access.py` · `backend/service/temporal_workflows.py`

脚本运行期间对 MySQL / trs-graph / Milvus / LLM / embedding 的**每一次访问**都被观测层记录，运行结束后聚合成 access report，随任务展示——回答「这次任务到底读写了哪些数据」。

## 工作机制

`Context` 构造客户端时（`kg_sdk.Context`），SDK 会把真实客户端包进观测包装器：

| 包装器 | 覆盖 |
|---|---|
| `observe_mysql_client(client, default_db)` | MySQL：每条 SQL 语句（`record_mysql_statement(sql, db)`） |
| `ObservedGraphClient(client)` | trs-graph：`merge_node` / `create_edge` / `execute_query` 等方法调用，记录读/写与涉及的 label/edge 类型 |
| `ObservedMilvusClient(client)` | Milvus：collection 级读写 |
| `ObservedLLMClient(client)` / `ObservedEmbeddingClient(client)` | LLM / embedding 调用次数 |

包装器**不改任何行为**——纯观测，透传方法调用。

## sidecar：跨进程报告收集

Temporal activity 在**子进程**里跑脚本，观测状态在子进程内。收集链路：

1. activity 启动子进程前设置 `KG_ACCESS_LOG` env 指向一个临时文件路径；
2. 子进程内每条访问事件同时追加写入该 sidecar 文件（`_append_sidecar`）；
3. 子进程结束后，服务侧 `report_from_sidecar(path)` 读回；
4. 多次 attempt / 多个 sidecar 用 `merge_access_reports()` 合并（计数累加、命名集合并）。

## 公开 API

```python
from kg_sdk import access_report, reset_access_report, flush_access_sidecar

access_report() -> dict          # 当前进程累计的访问报告
reset_access_report() -> None    # 清零（测试用）
flush_access_sidecar() -> None   # 把当前报告落盘到 KG_ACCESS_LOG 指向的 sidecar
```

报告按「类别 → 计数 + 涉及对象名」组织：MySQL 记语句计数与库，图记读写次数与 label/edge 类型集合，Milvus 记 collection，模型记调用数。

## 脚本侧要不要关心？

通常不用——包装由 `Context` 自动完成。只有两种情况直接接触：

- **手写读取循环、不走 `ctx.mysql`** 的 legacy 路径：不会进报告；
- **单测**里断言访问行为：`reset_access_report()` → 跑代码 → `access_report()`。

相关端点：任务详情接口返回的执行记录里携带各 step 的 access report；前端任务中心据此展示「本次运行访问了哪些表 / 图数据空间 / collection」。
