# 测试约定

> 来源：`CLAUDE.md` Backend commands / Tests run in containers 节

## 铁律：测试只在容器内跑

后端与全部基础设施（MySQL、RustFS、Temporal、Milvus、redis、trs-graph）**只跑在 Docker 里**，宿主机上什么都没有。**永远不要在宿主机跑依赖后端服务的测试**——会报 `Can't connect to MySQL server on 'temporal-mysql'`（DNS 不可解析）。

## 后端

```bash
# 在运行中的 api 容器内（924 passed，约 28s）
docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest tests -m "not external" -q

# 单测
docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest \
  tests/unit/test_trs_graph_client.py::TestExceptions::test_hierarchy
```

- `external` marker：需要真实 MySQL/Redis/TRSGraph/Kafka/Milvus 的测试，CI 跑 `-m "not external"`；
- 图客户端单测用 `httpx.MockTransport` 伪造 trs-graph REST，无需活服务；
- 集成测试用 `tests/conftest.py` 的 `async_client` fixture（ASGI transport 直连 `main.app`）；
- SDK 测试：`tests/unit/test_kg_sdk.py`、`tests/unit/test_extractor_sdk_context.py`。

## 前端

```bash
# 单测：在 builder 阶段镜像里跑（74 passed）
docker build --target builder --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg VITE_BASE=/ --build-arg VITE_API_BASE=/api \
  -t tech-kg-dev2-frontend-test ./frontend
docker run --rm tech-kg-dev2-frontend-test \
  pnpm vitest run --exclude "src/__tests__/review-full-integration.spec.ts"
```

- typecheck + build 也走容器：`docker compose -f docker-compose.dev2.yml build web-dev2`（builder 阶段 `vue-tsc -b && vite build`，现含 `pnpm docs:build`）；
- `src/__tests__/review-full-integration.spec.ts` 是**环境门控**测试：自己起 uvicorn 后端 + MinIO + 工作流 MySQL，现有容器都不满足——它在任何环境失败都是环境问题而非回归，一律 exclude。

## 覆盖率口径

- CI 后端：`PYTHONPATH=. uv run pytest tests -m "not external"` + ruff format/check；
- Milvus 相关重测试需 `--extra milvus`（pymilvus[model] + jieba + milvus-model）。
