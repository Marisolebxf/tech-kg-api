# 算子注册表

> 来源：`backend/docs/operator_registry.md` · `CLAUDE.md` 算子注册表节

`service/operator_registry.py` 是一个**线程安全、可热加载**的 Python 算子注册表。用户自定义工作流就是这些算子的组合。

## 算子契约

```python
list[dict] -> operator(data, ctx) -> list[dict]
```

每个算子接收 dict 列表，返回 dict 列表——批式数据流。

## 算子来源

| 来源 | 位置 | 说明 |
|---|---|---|
| 内置 | `service/operator_builtins.py` | 平台预置 |
| 学者域 | `operators/scholar/` | **已提交**的内置算子源码 |
| 用户上传 | `operators/user/`（gitignored 运行时缓存） | 上传时经 `infra/operator_store.py` 持久化到 S3（RustFS） |

## 生命周期

`main.py` lifespan 调 `REGISTRY.initialize_store()` + `start_watcher()`——watcher 监听 `operators/user/` 目录变化实现**热加载**：上传新算子包即刻可用，无需重启。

## 安全边界

用户算子是任意 Python 代码，运行在受控子进程；上传包的元数据（入口、参数声明）由注册表校验后入 SQLite 控制面，供工作流编辑器选择与编排。
