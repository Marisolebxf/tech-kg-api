import { defineConfig } from "vitepress";
import { loadEnv } from "vite";

// 与 vite.config.ts 同源读取 VITE_BASE（loadEnv 覆盖 process.env 与 frontend/.env* 文件），
// 保证文档站 base 与主应用部署前缀一致；相对 './' 或 '/' 都按根路径部署处理。
const env = loadEnv(process.env.NODE_ENV || "production", process.cwd(), "");
const rawBase = (env.VITE_BASE || process.env.VITE_BASE || "./").trim();
const normalized = rawBase.endsWith("/") ? rawBase : rawBase + "/";
const appBase = normalized === "./" || normalized === "/" ? "/" : normalized;

export default defineConfig({
  base: `${appBase}docs/`,
  outDir: "../dist/docs",
  lang: "zh-CN",
  title: "Tech KG 文档中心",
  description:
    "科技知识图谱平台文档：抽取脚本 SDK（kg_sdk）、后端架构（DDD 分层 / Temporal 工作流 / trs-graph 图数据库）与部署运维。",
  lastUpdated: false,
  themeConfig: {
    nav: [
      { text: "首页", link: "/" },
      { text: "SDK 文档", link: "/sdk/context" },
      { text: "项目架构", link: "/arch/overview" },
      { text: "部署运维", link: "/deploy/docker" },
    ],
    sidebar: {
      "/guide/": [
        {
          text: "指南",
          items: [{ text: "文档站维护指南", link: "/guide/maintain" }],
        },
      ],
      "/sdk/": [
        {
          text: "SDK 文档（kg_sdk）",
          items: [
            { text: "运行上下文 Context", link: "/sdk/context" },
            { text: "数据读取与增量水位", link: "/sdk/incremental" },
            { text: "标识与值语义", link: "/sdk/identity" },
            { text: "实体抽取与写入", link: "/sdk/entities" },
            { text: "关系抽取与写入", link: "/sdk/relations" },
            { text: "抽取主流程与双入口", link: "/sdk/runners" },
            { text: "平台喂数模式", link: "/sdk/platform-fed" },
            { text: "数据访问溯源", link: "/sdk/observability" },
            { text: "API 速查表", link: "/sdk/reference" },
          ],
        },
      ],
      "/arch/": [
        {
          text: "项目架构",
          items: [
            { text: "总体架构与 DDD 分层", link: "/arch/overview" },
            { text: "认证与权限", link: "/arch/auth" },
            { text: "权限边界与治理", link: "/arch/admin" },
            { text: "图数据库 trs-graph", link: "/arch/graph" },
            { text: "Schema 管理", link: "/arch/schema" },
            { text: "Temporal 工作流系统", link: "/arch/workflow" },
            { text: "算子注册表", link: "/arch/operators" },
            { text: "人工审核与修正中心", link: "/arch/review" },
            { text: "任务中心与公共能力", link: "/arch/tasks" },
            { text: "性能优化：结果缓存", link: "/arch/perf" },
          ],
        },
      ],
      "/deploy/": [
        {
          text: "部署运维",
          items: [
            { text: "Docker 部署", link: "/deploy/docker" },
            { text: "环境变量参考", link: "/deploy/env" },
            { text: "测试约定", link: "/deploy/testing" },
          ],
        },
      ],
    },
    outline: { level: [2, 3], label: "本页目录" },
    docFooter: { prev: "上一页", next: "下一页" },
    returnToTopLabel: "回到顶部",
    sidebarMenuLabel: "菜单",
    darkModeSwitchLabel: "主题",
    lightModeSwitchTitle: "切换到浅色模式",
    darkModeSwitchTitle: "切换到深色模式",
    search: {
      provider: "local",
      options: {
        translations: {
          button: { buttonText: "搜索文档", buttonAriaLabel: "搜索文档" },
          modal: {
            noResultsText: "未找到相关结果",
            resetButtonTitle: "清除查询",
            footer: { selectText: "选择", navigateText: "切换", closeText: "关闭" },
          },
        },
      },
    },
    socialLinks: [],
  },
});
