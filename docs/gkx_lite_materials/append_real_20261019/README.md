# gkx_lite 真实数据追加（人工审核验收配套）——公开侧说明

批次 `real-append-20261019`。目的：为人工审核正式验收准备真实科研数据
（论文/署名/学者/机构），追加进现有 `gkx_lite` 测试库，**只增不改**。

## 物料两分法（仓库公开，真实数据不入库）

本仓库（GitHub 公开）只包含零真实字面量的结构与流程物料：

| 公开分支（本目录） | 服务器侧受限区 `~/deploy/review-suite-20261019/` |
|---|---|
| `append_template.sql`（列结构+幂等骨架模板） | `append/append.sql`（真实字面量全量 511 条，will-insert 全 1）/ `append/MANIFEST.md`（全量映射+核验证据）/ `cleanup.sql`（随附不执行） |
| `MANIFEST_TEMPLATE.md`（清单格式） | `selection/`（选样 JSON）/ `verification/`（DOI/ORCID 核验）/ `cases/`（30 案证据卡）/ `work/`（可重放脚本） |
| 本 README（流程+计数汇总+校验值） | `scripts/`（9 个基础脚本副本 + Person 触发版 + AUTHORED_BY 故障注入版） |

受限区内容（真实姓名、内部原始行、R-id 全映射）不推公开分支；
协作文档中只报该目录文件行数与 sha256 前 16 位校验值（见 MANIFEST §5）。

## 数据来源与核验状态

- 来源：本机实例 A `gkx_dwd_local` 数仓样本（中文源：dwd_zh_paper /
  dwd_zh_author / dwd_zh_journal / dwd_scholar / dwd_org_base_info），
  只读取样，固定种子可整批重放。内部数仓数据，物料不外发。
- 公开核验（DOI 80 条：已核验 77，其中五项全对 76、源期号/页码 NULL 比对
  3 项 1；元数据冲突 3 = 年份框架差（首发年 vs 刊出年，保留源值单列证据）；
  无法核验 0。ORCID 30 条：已核验 30/30（EN 姓名规范化全等，机构相容
  19/30），身份冲突 0）：三态标记+冲突单列；中文 DOI 走 doi.org→chndoi→
  CNKI 公开链路，Crossref 全 404 属预期（ISTIC 体系）。
- 敏感列（email/phone/avatar）零选用零输出。

## 批次规模（实测精确计数，详单在受限区 MANIFEST/counts.md）

- 来源记录：论文 80 / 作者行 377 / 期刊 4 / 学者 30 / 机构 10 /
  测试性链归属 10（合计 INSERT 511）
- 初始 VID：Paper 80 + Journal 4 + Person 407（学者 30 + 作者行 377，
  扣留前）+ Organization 10 = **501**
- 真实关系：AUTHORED_BY 377 + PUBLISHED_IN 80 = **457**（org 链归属
  10 条为测试性关联，不计入真实关系承诺）
- 审核用例 30 案：确认同人映射 4（强证据档，预设合并）+ 辅助证据合并
  4（不预设）+ 确认新实体 9（同名异人 8 组 + 重分类入组 1）+ 驳回 6
  （四分类：团体署名 4 / 损坏 1 / 信息不足 1；身份候选错误为 0，
  结构性原因见用例）+ 故障注入重跑 7
- 存量并入：验收绑定读追加后全表（处理行数 90/396/9/36/16/18），存量
  64 行一并进入新空间（另贡献 Person 25 / Paper 10 / Journal 5 / Org 6
  与 AUTHORED_BY 19 / PUBLISHED_IN 10 / BELONGS_TO_NODE 8）；对账时
  本批 R\* 行与存量行分列。

## 执行流程（管理员，与页面验收分开）

1. 核对前置：`rowcounts_before.txt` 与 `gkx_lite` 当前行数一致；
   确认无调度任务读取该库（已核：实例 B 全部 active 调度零引用 gkx_lite）。
2. 执行受限区 `append/append.sql`（幂等，重复执行只跳过已导入行）。
3. 对账：七表行数差值=清单行数；存量 64 行按主键比对未变。
4. 新建隔离图空间 + 新 Schema 绑定 dev2-default/gkx_lite（Person 双来源
   绑定顺序 dwd_scholar 在前、dwd_zh_author 在后——合并案学者候选须先
   入库），上传受限区 `scripts/`（全量跑批用 Person 触发版 + 基础版
   其余 8 个；故障注入版只用于重跑案轮），一次性全量任务（rbac 模式新
   definition_id，无既有水位，导入后按手册步骤核验 0 水位记录）。
5. 验收执行按《亿级科技知识图谱引擎测试文档》第 8 章「人工审核验收」。

## 安全边界

只 INSERT（NOT EXISTS 防重）；不 UPDATE/DELETE/TRUNCATE/REPLACE；
不 ALTER 共享表；不触碰旧图、旧水位、旧任务；`cleanup.sql` 随附受限区
**不自动执行**，留待后续裁决。真实数据字面量、凭证、敏感字段不进公开仓库。
