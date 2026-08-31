---
layout: home

hero:
  name: Tech KG 平台文档
  text: 科技知识图谱构建与治理平台
  tagline: 抽取脚本 SDK · 后端架构 · 部署运维
  actions:
    - theme: brand
      text: 快速开始：kg_sdk
      link: /sdk/context
    - theme: alt
      text: 项目架构
      link: /arch/overview
    - theme: alt
      text: 部署运维
      link: /deploy/docker

features:
  - icon: 🧩
    title: 抽取脚本 SDK（kg_sdk）
    details: 平台向脚本注入 Context（MySQL / trs-graph / Milvus / LLM / embedding 五类懒加载客户端），配合 watermark 水位做增量抽取、prev_outputs 做多步流水线、access report 做数据访问溯源。
    link: /sdk/context
    linkText: 查看 SDK 文档
  - icon: 🏛️
    title: DDD 分层后端
    details: FastAPI + biz/handler → application → service → dao/infra 五层架构；Temporal 工作流、算子注册表、人工审核、修正中心、schema 管理等子系统逐一拆解。
    link: /arch/overview
    linkText: 查看架构文档
  - icon: 🚀
    title: 部署与测试
    details: 双 compose 栈（生产 8001/8088、dev2 8002/8089）、前端两阶段 Docker 构建、容器内测试约定与环境变量速查。
    link: /deploy/docker
    linkText: 查看部署文档
---
