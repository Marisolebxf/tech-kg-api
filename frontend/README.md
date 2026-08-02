# 亿级科技知识图谱平台原型

这是一个用于评审和演示的知识图谱平台前端原型，基于 Vue 3、TypeScript、Vite 构建。仓库当前只保留原型系统，不再包含旧版后端服务和前后端整合代码。

## 功能范围

- 平台总览：展示数据接入、图谱构建、质量治理、增量更新和业务服务运行状态。
- 数据处理：展示数据接入、清洗、抽取、消歧、审核、入库闭环。
- 图谱构建：支持实体、关系、属性、规则的新增、编辑、删除、合并、驳回和批量审核原型。
- 图谱查询：展示核心子图、结构化结果和证据链。
- 业务服务：覆盖九大业务服务调用与接口文档，包括图谱结果、结构化返回、证据链、请求参数、返回字段和代码示例。

## 九大业务服务

1. 科技专家/人才直接关系
2. 科技单节点间接关系
3. 科技两点合作成果
4. 科技专家同事关系
5. 科技专家校友关系
6. 科技专家论文合作关系
7. 重点关注科技企业关系
8. 科技产业链点 TOP-N 事件关系
9. 科技产业链全景图

## 本地运行

```bash
pnpm install
pnpm dev
```

默认访问：

```text
http://localhost:5173/
```

如端口被占用，Vite 会自动切换到下一个可用端口。

## 构建

```bash
pnpm build
```

构建产物输出到 `dist/`。

## Docker 部署

```bash
docker compose up -d --build
```

默认访问：

```text
http://localhost:8080/
```

如果需要部署到 GitHub Pages 这类子路径，可在构建时设置：

```bash
VITE_BASE=/tech-kg-api-dev/ pnpm build
```

Docker 默认使用相对路径构建，适合部署到站点根路径。

## 目录结构

```text
.
├── public/                 # 静态资源
├── src/
│   ├── api/                # 前端 API 封装
│   ├── assets/             # 图标和图片资源
│   ├── layouts/            # 页面框架
│   ├── router/             # 路由配置
│   ├── stores/             # 状态管理
│   ├── styles/             # 样式与设计变量
│   └── views/platform/     # 知识图谱平台原型主页面
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── package.json
├── pnpm-lock.yaml
└── vite.config.ts
```

## 提交到目标仓库

目标仓库如果已有旧代码，推荐保留 Git 历史，用一次普通提交删除旧代码并加入当前原型：

```bash
git clone https://github.com/Marisolebxf/tech-kg-api-dev.git
cd tech-kg-api-dev
# 删除除 .git 外的旧文件后，复制当前原型文件到仓库根目录
git add -A
git commit -m "feat: replace repository with knowledge graph prototype"
git push origin main
```

这样不需要 `git push --force`，也能覆盖仓库当前内容。
