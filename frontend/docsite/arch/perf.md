# 性能优化：结果缓存

> 来源：`CLAUDE.md` Performance 节 · `backend/biz/prewarm_business.py`

## infra/result_cache.py

进程内的**预序列化 JSON 响应缓存**：dict 结构，键为请求参数，值为已序列化的 JSON 字符串。

命中时 handler 直接 `return Response(cached_json_str)`——**零 Pydantic 序列化**。这在高并发下是关键：FastAPI `response_model` 的 `jsonable_encoder` 是 ~500 并发压测时的瓶颈。

| 配置 | 说明 |
|---|---|
| `RESULT_CACHE_TTL` | TTL（load-test 里 600s） |
| 锁 | **刻意不加锁**——CPython GIL 下 dict get/set 原子。**不要给缓存加锁** |

## 启动预热

`biz/prewarm_business.py` 在 lifespan 触发的后台任务里预热九大业务模块的结果缓存（`PREWARM_BUSINESS=true` 门控）——避免重启后的冷启动请求集中打到 trs-graph。

## LLM 降级也影响性能面

`infra/llm.py` 的 `get_llm_client()` 是进程单例；`LLM_API_KEY` / `ZHIPUAI_API_KEY` 未配置时返回 `None`，`synthesize()` 任何错误都返回 `None`——调用方（如企业背景分析）降级为模板/结构化结果，**不会**因 LLM 故障拖垮接口延迟。默认模型 `glm-4.7-flash`；专利混合检索用独立的 m3e embedding 服务（`PATENT_EMBEDDING_BASE_URL`，默认 `http://m3e-embedding:8010/v1`）。
