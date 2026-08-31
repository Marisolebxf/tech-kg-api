# 文档站维护指南

> 本站由 [VitePress](https://vitepress.dev/) 构建，源文件位于仓库 `frontend/docsite/`，
> 构建产物落在前端 `dist/docs/`，由 nginx 与主应用一同提供（路径 `/docs/`）。

## 本地预览与构建

在 `frontend/` 目录下：

```bash
pnpm docs:dev       # 本地开发服务器（默认 http://localhost:5173）
pnpm docs:build     # 构建到 frontend/dist/docs/
pnpm docs:preview   # 本地预览构建产物
```

`pnpm build`（主应用构建）**不**包含文档；Docker 构建里两步都会跑（见下）。

## 目录结构

```
frontend/docsite/
├── .vitepress/config.ts   # 站点配置：base、导航、侧边栏、本地搜索
├── index.md               # 首页（hero + feature 卡片）
├── guide/maintain.md      # 本页
├── sdk/                   # kg_sdk 使用文档（8 页）
├── arch/                  # 项目架构（9 页）
└── deploy/                # 部署运维（3 页）
```

新增页面：在对应目录建 `.md`，再到 `.vitepress/config.ts` 的 `sidebar` 里登记条目。

## 配置要点

- **base**：从 `process.env.VITE_BASE` 归一化推导（`./` 或 `/` → `/docs/`；子路径部署如 `/app/` → `/app/docs/`），与主应用的部署前缀保持一致。
- **outDir**：`../dist/docs`——Docker builder 阶段先 `pnpm build` 再 `pnpm docs:build`，两份产物合并进最终 nginx 镜像，`location /` 的 `try_files` 天然服务 `/docs/`，**nginx 无需任何额外配置**。
- **搜索**：VitePress 内置 local search（MiniSearch），适合内网部署；中文长句分词较粗，标题/关键词检索效果好。
- **类型检查**：`vue-tsc` 的编译范围是 `tsconfig.app.json`（仅 `src/**`），docsite 下的 ts 文件不参与——**不要**把 `docsite/` 加进 tsconfig include。

## 与源文档的同步责任

本站内容是**转写版**而非实时引用。各页顶部标注了权威源：

| 章节 | 权威源（代码变更时需回填） |
|---|---|
| SDK 文档 | `backend/sdk/kg_sdk.py`、`backend/sdk/access.py`、`backend/docs/kg_sdk.md`、`docs/script-sdk/` |
| 项目架构 | 根 `CLAUDE.md`、`backend/docs/*.md` 各子系统文档、根/backend `README.md` |
| 部署运维 | `docker-compose.yml`、`docker-compose.dev2.yml`、`frontend/Dockerfile`、`backend/pyproject.toml` |

约定：**改代码的人在改动的同批提交里同步对应文档页**；页面顶部的 `> 来源：` 行指明上游，冲突时以上游为准。

## 部署

`frontend/Dockerfile` builder 阶段在 `pnpm build` 后执行 `pnpm docs:build`；产物随 `dist/` 一起拷入 nginx 镜像。访问入口：主应用顶部操作栏的"文档中心"图标按钮（新标签页打开 `/docs/`）。
