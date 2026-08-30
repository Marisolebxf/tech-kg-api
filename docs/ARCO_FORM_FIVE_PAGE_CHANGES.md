# 五个页面 Arco Vue Form 整改说明

## 整改范围

本次仅整改以下五个前端页面及其直接使用的表单组件：

- Schema 管理
- 图谱构建
- 人工审核
- 配置管理
- 图谱查询

输入框按要求继续保留原生 Vue `v-model` 实现；选择框、文本域、单选、复选、表单布局、必填标识及字段校验统一使用 Arco Design Vue。后端代码、路由和其他业务页面均未修改。

## 修改文件与改动

### `frontend/src/views/platform/SchemaBrowserView.vue`

- 新增 Schema 弹窗改为 `a-form` 垂直表单，并为名称、中文名、起终点实体、属性列表等字段配置 `a-form-item`。
- 起点实体、终点实体、默认 LLM 配置和属性类型统一使用 `a-select` / `a-option`。
- 建模说明统一使用 `a-textarea`。
- 来源表多选和属性必填开关改为 `a-checkbox`。
- 增加表单 ref、rules 和提交前 `validate()`；保留原业务格式检查和预览确认逻辑。
- 属性名称使用数组字段路径逐行校验；起点、终点实体改为仅关系 Schema 生效的条件校验。

### `frontend/src/views/platform/GraphBuildView.vue`

- 页面继续由专用 `JobLaunchDialog` 承载作业启动表单，作业列表、运行状态和执行详情逻辑保持不变。

### `frontend/src/components/JobLaunchDialog.vue`

- 作业启动区域使用 `a-form`、`a-form-item` 和稳定的计算表单 model。
- 作业、LLM 配置和执行频率使用 `a-select`，执行模式使用 `a-radio-group` / `a-radio`。
- 为作业、执行模式、频率和执行时间配置 field、rules、必填标识及提交前校验。
- 时间、增量游标和业务域输入框按要求保留原生控件。

### `frontend/src/views/platform/OperationsCenterView.vue`

- 人工审核列表筛选区改为 `a-form` 和 `a-form-item`。
- 风险、批次、业务域、状态和分页条数改为 `a-select`。
- “仅看已阻断”改为 `a-checkbox`。
- 列表查询、分类切换和清空筛选逻辑保持不变。

### `frontend/src/views/platform/ManualReviewWorkspaceView.vue`

- 人工审核详情裁决区纳入 Arco Vue `a-form`。
- 实体类型、字段映射、字典版本和重跑 Prompt 继续使用 `a-select`，带标签的 Prompt 字段使用 `a-form-item`。
- 实体裁决、关系裁决、属性裁决、主记录选择统一改为 `a-radio-group` / `a-radio`。
- 证据选择、保留原始值、合并字段和规则沉淀统一改为 `a-checkbox`。
- 增加稳定的计算表单 model、表单 ref 和 rules；实体、关系、属性、补录标题、主记录及证据字段注册到对应 `a-form-item`。
- 主提交动作执行前调用 `validate()`，次要处置动作保留原有业务通路，避免无关模板字段阻断驳回或隔离操作。
- 保留审核状态、禁用条件、提交载荷和业务决策逻辑。

### `frontend/src/components/manual-review/ManualReviewDynamicForm.vue`

- 动态人工审核组件改为 `a-form` / `a-form-item`。
- JSON 编辑区域改为 `a-textarea`，实体裁决改为 `a-select`，证据列表改为 `a-checkbox`。
- 保留动态 section 协议和 change 事件的数据结构。

### `frontend/src/components/manual-review/__tests__/ManualReviewDynamicForm.spec.ts`

- 补充 Arco 组件测试所需的 `matchMedia` 浏览器环境模拟。
- 将原生 `select` 断言更新为 Arco Select 组件结构断言，保持动态表单渲染与安全降级测试有效。

### `frontend/src/views/platform/ConfigurationManagementView.vue`

- 配置编辑抽屉和新建弹窗改为 `a-form` / `a-form-item` 垂直表单。
- 状态筛选继续使用 `a-select`，说明字段统一使用 `a-textarea`。
- “设为默认”改为 `a-checkbox`。
- 为不同配置类型的名称、Base URL、模型、主机和用户名配置 field、required、rules 及提交前校验。
- 配置编辑抽屉新增 form ref、field、required、rules 和保存前 `validate()`，与新建配置保持一致。
- 原生输入框和配置保存、探活、启停、删除逻辑保持不变。

### `frontend/src/views/platform/PlatformWorkbenchView.vue`

- 仅整改“图谱查询”分支，平台总览、数据处理等其他分支未调整。
- 查询条件区改为 `a-form` / `a-form-item`，桌面端保持四个筛选项同一行，响应式下为两列或单列。
- 图谱范围、关系类型、实体置信度和关系置信度使用 `a-select` / `a-option`。
- 查询关键词配置 field、required、rules 和提交前 `validate()`。
- 查询 Form 改用稳定的 computed model，避免模板每次渲染创建临时对象。
- 保留针对 Arco Select 隐藏输入层的局部样式隔离，避免项目全局原生 input 规则污染选择框显示。

## 校验结果

- 已执行 `pnpm run build`。
- Vue TypeScript 检查通过。
- Vite 生产构建通过。
- 人工审核动态表单及人工审核数据相关测试通过。
- 构建仅保留项目原有的大 chunk 体积提示，不影响构建成功。
- 后端目录未发生改动。
