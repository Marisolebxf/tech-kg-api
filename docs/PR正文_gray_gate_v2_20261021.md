# feat(manual-review): enforce gray-gate-v2 routing and replay safety

Base: `kgetl`。Head: `feat/gray-gate-v2-1021`。代码复核提交：`8ab5e3dc`。创建为 Draft PR。

## 变更

抽取脚本的 pending 实体现在先走统一的同名候选 eligibility 与真实评分。只有真实 gray 才建立 T_LINK；无候选/低分实体按描述符门控正常写入。取消原强制送审旁路和新执行的写后碰撞建案；auto-merge 保持禁用，真实 merge 在持久 remap 未就绪时以 DEFERRED_MERGE_BLOCKED 失败关闭，受影响来源不推进水位。

源事件去重不再依赖 execution 或可变候选快照；已有案件与耐久裁决应用状态在 resolve 及写前守卫前查询，支持终态裁决重放并阻止 UNKNOWN/FAILED 绕过。pending 声明事件版本在内联与 S3 路径保持一致。案件来源追加、应用记录及计数模型/DDL 文件随代码提交。

边写入增加双端点路由与存在性终判。裁决补边在另一端未决时耐久转交；暂存、转交和精确摘除通过 version + 旧快照双谓词 CAS 短事务重试，避免并发覆盖。建案评分证据保持只读，详情的当前图库重算单列展示。

## 代码复核与本地验证

- 前两轮独立契约复现：11 passed，原断言未改。
- 新增真实 CAS 更新冲突与精确摘除测试：2 passed。
- 本机相关 4 个单测文件：157 passed（Python 3.11.13、UTF-8、水位读取本地空桩）。
- 本次变更 4 个 Python 文件：ruff check / format --check 通过。
- git diff --check 通过。

复核依据与逐项结果见通信分支 `docs/manual-review-gray-gate-review-1021` 的 `docs/人工审核专项实现复核_20261021.md`，可复现脚本位于同分支 `docs/review_probes/`。本地复核使用假图客户端与内存 SQLite，不将 GLM 容器内报告的全量/集成结果冒充本机验证；CI 结果以本 PR 实际运行记录为准。

## 阶段边界

持久 remap 方案 A、v3 auto-merge、历史强制案/应用状态迁移、生产密钥与配置、claim-check 生命周期/清理作业、数据盘点/补样本和数仓改动均未随本阶段执行。DDL 文件仅供审核；实际环境 DDL、生产数据及历史案件操作、合并和部署继续按既定审批范围处理。
