# 五个功能页面设计规范整改记录

> 整改日期：2026-08-28  
> 依据：`docs/DESIGN_RULES.md`、Arco Design Form 组件文档  
> 范围：Schema 管理、图谱构建、人工审核、配置管理、图谱查询  
> 说明：Arco Form 的 Input 外观未作为参考；本次未修改后端、全局 Shell、业务服务页面或其他功能页面。

## 改动原则

- 页面内容区域使用 16px 主间距，组件内部使用 4px / 8px 节奏。
- 普通卡片统一 6px 圆角、1px 中性边框、白色表面、无阴影。
- Button、Select 等标准控件统一 32px 高、4px 圆角、14/22px 文字。
- 正文与表格统一 14/22px，辅助文字统一 12/20px，分区标题统一 16/24px、600。
- 表格默认 40px 行高、单元格左右 16px、表头 500 字重。
- 业务状态改为“6px 语义色圆点 + 状态文字”，取消带底色胶囊。
- Modal 使用规范尺寸，并统一 56px Header、24px Body、64px Footer。
- 所有覆盖均限定在目标页面根类或图谱查询分支内，避免影响其他页面。

## 修改文件

### `frontend/src/views/platform/SchemaBrowserView.vue`

- 摘要卡改为无外框 KPI 分隔布局，去除渐变装饰与阴影。
- 页面 Tab 统一为 36px 一级 Tab；工具栏使用 16px 间距。
- 表格统一字号、行高、内距、表头背景和字重。
- 状态改为圆点加文字；脚本文件标记保留分类 Tag 语义。
- Trace 卡片统一为中性边框、6px 圆角和无阴影。
- 普通弹窗调整为 560px，创建弹窗调整为 640px。
- Modal Header、Body、Footer 和按钮间距按规范统一。
- 创建表单的 Label、Select、动态属性行和来源表选择区统一密度。
- 900px 以下摘要和表单改为单列/双列响应式布局。

### `frontend/src/views/platform/GraphBuildView.vue`

- 移除与 Shell 面包屑重复的页面大标题，仅保留操作区。
- 摘要卡改为 KPI 分隔布局。
- 主从布局调整为任务表 Fill + 360px 详情栏，间距 16px。
- 两侧面板统一 6px 圆角、无阴影和独立滚动。
- 表格统一 40px 行高、14/22px 字体、16px 左右内距。
- 详情元信息、步骤列表、日志和按钮统一字体与间距。
- 任务和步骤状态改为圆点加文字。
- 1100px 以下切换为上下单列布局。

### `frontend/src/views/platform/OperationsCenterView.vue`

- 人工审核指标改为无外框 KPI 分隔布局。
- 审核面板去除阴影并统一 6px 圆角。
- 一级 Tab、分类筛选、查询筛选统一到 32/36px 控件体系。
- 筛选区采用三列布局和 16px 间距，窄屏改为单列。
- 审核表格统一 40px 行高、14/22px 字体、16px 内距和 500 表头字重。
- 审核状态改为圆点加文字。
- 风险说明块统一为 16px 间距及规范字号。
- 分页页项统一 32px。
- 审核 Drawer 调整为 640px安全宽度，并统一 Header、Body、Footer。

### `frontend/src/views/platform/ManualReviewWorkspaceView.vue`

- 根容器取消重复页面滚动，主审核内容区负责滚动。
- 对象标题、元信息、诊断区和分区标题统一字体层级。
- 状态和处理范围改为圆点加文字。
- 审核分区使用浅灰模块底，减少卡片套卡片。
- 三列信息区统一 16px 间距和规范字号。
- 表单控件、备注区和审核动作统一 32px控件体系。
- 接受/拒绝操作统一按钮圆角、字体和 16px间距。
- 960px 以下切换为单列并恢复自然页面滚动。

### `frontend/src/views/platform/ConfigurationManagementView.vue`

- 移除与 Shell 重复的页面标题，保留新增操作。
- 摘要卡改为 KPI 分隔布局。
- 页面内配置目录从 248px 调整为 240px。
- 目录项统一 40px高、20px图标、8px图文间距；Active 去除左侧竖条。
- 1024px 以下目录收缩为 84px图标栏，隐藏辅助说明。
- 主列表工具栏、Input、Select、表格统一规范尺寸。
- 表格文字、代码辅助信息、表头和操作链接统一字号。
- 状态改为圆点加文字；“默认配置”保留分类 Tag。
- 新建弹窗调整为 640px，详情 Drawer 使用 640px安全宽度。
- 表单 Label、字段间距、控件和 Footer 按 Modal 表单规范统一。

### `frontend/src/views/platform/PlatformWorkbenchView.vue`

- 仅修改 `.platform-query` 图谱查询分支，不影响平台总览和同文件其他功能。
- 查询区、图谱画布和右侧详情之间统一为 16px间距。
- 保留 340px右侧详情栏，符合 320–400px工作区辅助栏规范。
- 查询表单改为最多三列的响应式 Grid；1100px以下两列，768px以下单列。
- Label、Select、Button统一 14/22px和32px高。
- 图谱与详情面板统一中性边框、6px圆角和无阴影。
- 图例统一字体与间距并移除圆点阴影。
- 详情切换改为二级 Tab 视觉。
- 详情字段、空态、状态和局部表格统一规范。
- 1100px 以下右侧详情移动到图谱下方。

## 范围控制

本次实际修改仅包含以上六个 Vue 文件和本记录文件。未修改：

- `frontend/src/views/business-service/**`
- 其他前端功能页面
- `frontend/src/layouts/AppLayout.vue`
- 全局共享样式文件
- 后端代码
- `docs/DESIGN_RULES.md`

## 验证结果

- `pnpm build`：通过。Vite 成功完成 2095 个模块转换和生产构建；仅保留既有的大分包体积警告。
- `pnpm test`：4 个测试文件通过，66 项测试通过；`review-full-integration.spec.ts` 因环境无法解析 `temporal-mysql`，后端健康检查超时，导致 1 个测试文件失败、90 项跳过。
- `git diff --check`：通过。
