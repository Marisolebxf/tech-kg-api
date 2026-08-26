# 多步骤人工审核详情页修复 - 从已知状态继续

## 任务目标

让 `/manual-review/task/:caseId` 详情页正确渲染 T_DIRECT（kg.custom.steps 候选审核）case 的四段式布局：① 决策对象 ② 推理过程 ③ 辅助信息 ④ 决策按钮（通过·入库 / 驳回·丢弃）。

## 当前症状

用户访问 `http://10.50.183.56:8089/manual-review/task/MR-20260825-5AEA2B6440A1`（一个 OPEN 的 T_DIRECT case）：
- 浏览器 URL 停在详情页路径
- 但实际渲染的是 PlatformWorkbenchView（overview 首页），调了 `/api/v1/platform/overview` + `/api/v1/graph-search/*` API
- 用户看不到 T_DIRECT 四段式 + 决策按钮
- 即使用无痕窗口也复现

## 已完成的代码改动（已 commit + push 到 `kgetl` 分支）

1. `frontend/src/views/platform/ManualReviewWorkspaceView.vue`：加了 T_DIRECT section（四段式：决策对象 / 推理过程 / 辅助信息 / 决策）+ CSS + `directCandidate`/`directKind`/`directNodeLabel` 等 computed
2. `frontend/src/views/platform/manual-review-data.ts`：
   - `ReviewTemplateId` union 加 `'T_DIRECT'`
   - `templateCatalog` 加 T_DIRECT entry
   - `modeByRulePrefix` 开头加 `if (id === 'T_DIRECT') return 'T_DIRECT'` 短路
3. `frontend/src/api/workflowOperations.ts`：加 `directDecideProductionReview` 函数 + `workflowId`/`workflowRunId` 字段到 `ProductionReviewCase`
4. `frontend/src/views/platform/OperationsCenterView.vue`：productionTabs 加"全部"默认 tab + `category=A` 参数
5. `frontend/Dockerfile`：加 `ARG VITE_REVIEW_PRODUCTION_ENABLED`
6. `docker-compose.dev2.yml`：build args `VITE_BASE: "/"` + `VITE_REVIEW_PRODUCTION_ENABLED: "true"`；api-dev2 env `REVIEW_IDENTITY_REQUIRE_SIGNATURE: "false"`
7. `backend/biz/dependencies/review_identity.py`：dev fallback（require_signature=false 且无 X-User-Id 时返回 dev-anonymous）
8. `backend/biz/handler/manual_review.py` + `service/manual_review_production.py`：T_DIRECT template + create_direct_case + direct_decide + category 过滤 + T_RUNTIME 排除
9. `frontend/nginx.dev2.conf`：`location /` 加 `Cache-Control: no-cache, no-store, must-revalidate`

## 已验证（curl + bundle grep 都过）

- 后端 `/api/v1/manual-reviews/production/MR-20260825-5AEA2B6440A1` 返回 200，含 `templateId: "T_DIRECT"`, `status: "OPEN"`, `template.id: "T_DIRECT"`, `candidate` 含 `_kind:"entity"`, `_nodeLabel:"Paper"` 等
- nginx 服务最新 HTML，引用 `/assets/index-VEksL_QQ.js`（绝对路径）
- bundle grep 含 `"T_DIRECT"` / `direct-target-tag` / `direct-lineage-grid` / `决策对象` / `推理过程` / `辅助信息`
- nginx 返回 `Cache-Control: no-cache` header

## 仍未解决的核心问题

**为什么用户浏览器渲染 PlatformWorkbenchView 而不是 ManualReviewWorkspaceView？**

可能的根因（按可能性排序）：

### 假设 A：`VITE_REVIEW_PRODUCTION_ENABLED` 没真正打进 bundle
Vite 默认只从 `.env` 文件加载 env，**不自动从 process.env 加载**。Dockerfile 里 `ENV VITE_REVIEW_PRODUCTION_ENABLED=...` 设了 process.env，但 `pnpm build` 时 Vite 可能没读到。验证：
```bash
docker exec tech-kg-web-dev2 sh -c 'grep -o "VITE_REVIEW_PRODUCTION_ENABLED[^"]*\"[^\"]*\"" /usr/share/nginx/html/assets/*.js | head -3'
```
如果 bundle 里 `productionMode` 的值是 `false`（即 `import.meta.env.VITE_REVIEW_PRODUCTION_ENABLED === 'true'` 被替换成 `false === 'true'` 即 `false`），那 `productionMode=false`，OperationsCenterView 用老 `getManualReviews` API，ManualReviewWorkspaceView 也走 legacy 路径 → record 加载失败 → 渲染空 → 但用户看到 overview 不空白，所以这条假设不一定对。

修复方向：在 `frontend/vite.config.ts` 用 `define` 或在 Dockerfile build 阶段生成 `.env.production` 文件：
```dockerfile
RUN echo "VITE_REVIEW_PRODUCTION_ENABLED=${VITE_REVIEW_PRODUCTION_ENABLED}" > .env.production
RUN pnpm build
```

### 假设 B：router.beforeEach 跳到 /overview
`frontend/src/router/index.ts` L115-145 有 beforeEach。`/manual-review/task/:instanceId` 路由 meta 是 `{ title: '人工审核详情' }`，没 `public`/`admin`/`permission`。但 beforeEach 里 `authStore.loadCurrentUser()` 可能在某种条件下抛错或返回 null，跳到 `/login` → 如果 `VITE_AUTH_ENABLED === 'false'`，`/login` 又跳 `/overview`。

验证：在 `ManualReviewWorkspaceView.vue` 的 `onMounted` 第一行加 `console.log('ManualReviewWorkspaceView mounted, productionMode=', productionMode, 'route=', route.params.instanceId)`，让用户刷新后看 Console。或者直接 grep bundle 看 `VITE_AUTH_ENABLED` 的值。

### 假设 C：用户的浏览器加载的还是旧 JS
即使 nginx 加了 no-cache，浏览器可能仍有 JS cache（JS 有 7d 长缓存）。新 HTML 引用新 JS hash `index-VEksL_QQ.js`，浏览器应该 cache miss 重下。但如果浏览器之前从未加载过这个 hash，会直接下载新 JS——无痕窗口应该是新 cache，这条假设不太可能。

## 调试步骤（按顺序执行）

### 1. 验证 VITE_* env 真的打进 bundle
```bash
# 在 web-dev2 容器里 grep bundle，看 VITE_REVIEW_PRODUCTION_ENABLED 替换后的字面值
docker exec tech-kg-web-dev2 sh -c 'grep -o "REVIEW_PRODUCTION_ENABLED[^a-zA-Z]" /usr/share/nginx/html/assets/*.js | head -3'
# 或搜 productionMode 计算后的字面值
docker exec tech-kg-web-dev2 sh -c 'grep -oE "production[A-Z][a-zA-Z]*" /usr/share/nginx/html/assets/*.js | sort -u | head -10'
```

如果 env 没打进 bundle，**这是根因**。修复：在 `frontend/Dockerfile` 的 `RUN pnpm build` 之前加：
```dockerfile
RUN echo "VITE_REVIEW_PRODUCTION_ENABLED=${VITE_REVIEW_PRODUCTION_ENABLED}" > .env.production && \
    echo "VITE_API_BASE=${VITE_API_BASE}" >> .env.production && \
    echo "VITE_BASE=${VITE_BASE}" >> .env.production
```
然后 rebuild + restart web-dev2。

### 2. 如果 env 已打进 bundle，验证 router 实际行为
在 `ManualReviewWorkspaceView.vue` script 顶部加 console.log：
```typescript
console.log('[MRWV] mounted, productionMode=', productionMode, 'case_id=', route.params.instanceId, 'VITE_AUTH_ENABLED=', import.meta.env.VITE_AUTH_ENABLED)
```

让用户用无痕窗口访问详情页 URL，打开 DevTools Console，看打印什么。

如果**没看到打印** → ManualReviewWorkspaceView 根本没挂载 → router 没匹配这条路由 → 假设 B（router 跳转）
如果**打印 productionMode=false** → 假设 A（env 没打进 bundle）
如果**打印 productionMode=true 但页面还是 overview** → ManualReviewWorkspaceView 内部某处出错

### 3. 检查 router 完整 beforeEach + 后端 /auth/me 返回
```bash
# /auth/me 是否返回 profile（不返回 null）
curl -s http://localhost:8002/api/v1/auth/me | python3 -m json.tool
# 看是否有 isAdmin 字段（如果路由 meta.admin=true 但 profile.isAdmin 缺失，会跳 /forbidden）
```

如果 `/auth/me` response 缺 `isAdmin` 字段，但 router beforeEach 用 `profile.isAdmin`，可能引发问题。但 `/manual-review/task/:instanceId` 路由没 `admin:true`，理论上不影响。

### 4. 强制硬刷新 + 验证 bundle hash
用户在无痕窗口按 F12 打开 DevTools → Network tab → 勾选 "Disable cache" → 强制刷新 → 看 `/assets/index-VEksL_QQ.js` 是不是 200 OK 加载（不是 from cache）→ 看 Console 有没有 Vue runtime error。

## 用户最终应该看到

`/manual-review/task/MR-20260825-5AEA2B6440A1` 详情页（T_DIRECT OPEN case）渲染：

```
┌─────────────────────────────────────────┐
│ 案件信息与证据                            │（rw-sec--evidence，旧段保留）
├─────────────────────────────────────────┤
│ 裁决 · kg.custom.steps 候选审核           │（rw-body）
│                                         │
│ ① 决策对象（橙色背景）                    │
│   [决策对象] Paper  P-2  entity-2        │
│                                         │
│ ② 推理过程（白底）                        │
│   workflow_id / step=extract /           │
│   任务 ID / 执行 ID / 置信度 0.78 mid     │
│   触发理由：置信度 0.78 < 0.85...         │
│                                         │
│ ③ 辅助信息（白底）                        │
│   来源证据表 + 候选属性表                  │
│                                         │
│ ④ 决策（橙色背景 + 2px 边框）             │
│   备注: [______________]                  │
│   [通过·入库]    [驳回·丢弃]              │
│   merge_node(...)  candidate 丢弃        │
└─────────────────────────────────────────┘
```

## 工作目录

`/home/zhangzhong_e43d4db3/src/tech-kg-api-dev2/`，分支 `kgetl`，最新 commit `e6b6620`。

## 建议执行顺序

1. 跑步骤 1 的 grep 命令，**先确认 VITE_REVIEW_PRODUCTION_ENABLED 是否真打进 bundle**
2. 如果没打进，改 Dockerfile 加 `.env.production` 生成步骤 → rebuild + restart web-dev2 → 验证
3. 如果打进了，在 ManualReviewWorkspaceView 加 console.log → 让用户无痕窗口访问 → 看 Console 打印
4. 根据打印结果判断是 router 跳转 / env 未生效 / 别的问题
5. 修复后 commit + push
6. dev2 已有 3 个 OPEN T_DIRECT case 可测：MR-20260825-5AEA2B6440A1 / MR-20260825-8E3BF9BD9220 / MR-20260825-B45DF1EDC9EB

## 关键 CLAUDE.md 上下文

- 这是 monorepo：`backend/` (FastAPI) + `frontend/` (Vue 3 + TS + Vite)
- dev2 stack：`docker-compose.dev2.yml`，web-dev2 端口 8089，api-dev2 端口 8002，Temporal dev2
- 前端 build：`cd frontend && pnpm build`（Dockerfile 里跑 `pnpm build`）
- 改前端后必须 `docker compose -f docker-compose.dev2.yml build web-dev2 && up -d web-dev2`
- 改后端必须 `docker compose -f docker-compose.dev2.yml build api-dev2 && up -d api-dev2 temporal-worker-dev2`
- 类型检查：`cd frontend && ./node_modules/.bin/vue-tsc -b --noEmit`
- 后端 lint：`cd backend && uv run ruff check .`
- dev2 已配 `REVIEW_IDENTITY_REQUIRE_SIGNATURE=false` + `get_review_identity` dev fallback，所以审核 API 不需要鉴权头就能调
- 用户访问的是 `http://10.50.183.56:8089/`（不是 localhost），从远程机器访问
