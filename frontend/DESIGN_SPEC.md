# 前端视觉规范

本规范对齐 Figma「科技专家同事关系原型图」的 PC 端稿，基础画布为 1440 x 800。

## 设计读取方式

- Figma 开发者模式可以查看节点尺寸、颜色、字体、间距和代码片段。
- 本项目已通过 Figma 节点读取到 5 个 PC 状态稿，主框架为浅蓝背景、216px 左侧导航、白色圆角主工作区。
- 统一样式入口在 `src/styles/tokens.css`，业务通用类在 `src/styles/global.css`。

## Token

- 字体：PingFang SC，兜底 Microsoft YaHei / Helvetica Neue / Arial。
- 主色：`#165DFF`。
- 正文：`#1D2129`。
- 次级文本：`#4E5969`。
- 弱文本：`#86909C`。
- 边框：`#E5E6EB`，强边框 `#C9CDD4`。
- 页面背景：`#D8E7FC`。
- 内容浅底：`#F7F8FA`。
- 控件高度：32px。
- 左侧导航宽度：216px。
- 常规圆角：4px / 6px / 8px；主工作区圆角：16px。

## 页面结构

- `AppLayout.vue` 负责全局外壳：左侧导航、用户入口、白色主工作区。
- `ExpertColleagueView.vue` 负责当前功能页：顶部页签、参数区、测试结果预览、结果详情和列表。
- 组件内不直接写品牌色，优先使用 `tokens.css` 里的变量。

## 组件规则

- 按钮使用 `.kg-button`、`.kg-button--secondary`、`.kg-button--text`。
- 页签使用 `.kg-tabs`、`.kg-tabs__item`、`.is-active`。
- 面板使用 `.kg-panel`，标题使用 `.kg-panel__title`，标题左侧蓝色竖线与 Figma 一致。
- 表单控件高度保持 32px，边框 1px，圆角 4px。
- 表格行高保持 44px，表头背景使用 `--surface-subtle`。
