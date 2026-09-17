-- ============================================================================
-- 失败重跑与写前消歧 · 演示数据（配套本目录三个抽取脚本）
-- ============================================================================
-- 隔离约定：所有表建在**独立演示库** techkg_script_demo 里，不碰任何业务库
-- （gkx_element / gkx_local / techkg_control / techkg_e2e …），用完可整库删除：
--     DROP DATABASE IF EXISTS techkg_script_demo;
-- 图侧同理：抽取任务请指向**独立图空间**（见 README「隔离运行手册」）。
--
-- 分段：
--   A1 失败重跑_产品实体.py   ← 表 demo_fail_product（3 好行 + 3 毒行）
--   A2 写前消歧_同名专家.py   ← 表 demo_disambig_expert（第一轮种子 4 行 +
--                                第二轮冲突 4 行【默认注释，跑完第一轮再放开】）
--   A3 关系挂起_任职边.py     ← 表 demo_works_at_relation（2 可解析 + 1 多义 +
--                                1 未命中 + 2 毒行）
-- ============================================================================

CREATE DATABASE IF NOT EXISTS techkg_script_demo
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE techkg_script_demo;

-- ----------------------------------------------------------------------------
-- A1 失败重跑：Product 源表（pk=id，增量列 update_time）
-- 毒行 4/5/6 只进 failures → T_EXTRACT_FAIL 审核 case → 修数后点「重跑」。
-- 修数示例（把三条毒行修成可解析，然后重跑）：
--   UPDATE demo_fail_product SET product_name = '边缘计算网关'
--    WHERE id IN (4, 5, 6);
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS demo_fail_product;
CREATE TABLE demo_fail_product (
  id            INT          NOT NULL PRIMARY KEY,
  product_name  VARCHAR(256) NULL,
  product_seq   VARCHAR(64)  NULL,
  company_name  VARCHAR(256) NULL,
  credit_code   VARCHAR(64)  NULL,
  update_time   DATETIME     NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO demo_fail_product (id, product_name, product_seq, company_name, credit_code, update_time) VALUES
  (1, '智能语音识别系统',  'P-2024-001', '杭州云声科技有限公司',     '91330100MA2XYZ1234', '2026-09-17 10:00:00'),
  (2, '工业视觉检测平台',  'P-2024-002', '苏州视锐智能装备有限公司', '91320594MA1ABC5678', '2026-09-17 10:00:00'),
  (3, '车规级激光雷达',    'P-2024-003', '上海光启传感技术有限公司', '91310115MA3DEF9012', '2026-09-17 10:00:00'),
  (4, '',                 'P-2024-004', '某某科技有限公司',         '91330100MA2POI0987', '2026-09-17 10:00:00'),  -- 毒行：产品名为空
  (5, '   ',              'P-2024-005', '某某科技有限公司',         '91330100MA2POI0987', '2026-09-17 10:00:00'),  -- 毒行：产品名全空白
  (6, 'N/A',              'P-2024-006', '某某科技有限公司',         '91330100MA2POI0987', '2026-09-17 10:00:00');  -- 毒行：产品名占位

-- ----------------------------------------------------------------------------
-- A2 写前消歧：Expert 源表（pk=id，增量列 update_time）
-- 两轮编排（一次性全插入会失去演示效果：第二轮必须等第一轮实体已写图、
-- 水位已推进后再执行，同名冲突才会与图内实体比对进入消歧打分）：
--   第一轮：只执行下方「种子」4 行 → 触发抽取#1（图内尚无同名 → 全部直写）
--   第二轮：放开「冲突」4 行的注释并执行 → 触发抽取#2（增量水位只读新行）
-- 第二轮与图内同名实体的属性重合度 → 平台消歧三分支：
--   E2001 王伟 单位同+简介同  → 2/2 一致 → 得分 1.00 → merge 自动并入 E1001
--   E2002 李娜 单位同+简介异  → 1/2 一致 → 得分 0.80 → 灰区 → T_LINK 扣留
--   E2003 张敏 单位异+简介异  → 0/2 一致 → 得分 0.60 → new 直接新建
--   E2004 刘洋 无单位、图内同名者无简介 → 无可比属性(0.5) → 0.80 → 灰区 T_LINK
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS demo_disambig_expert;
CREATE TABLE demo_disambig_expert (
  id                   INT          NOT NULL PRIMARY KEY,
  expert_id            VARCHAR(64)  NOT NULL,
  name_zh              VARCHAR(128) NOT NULL,
  organization_name_zh VARCHAR(256) NULL,
  bio_zh               TEXT         NULL,
  update_time          DATETIME     NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- ── 第一轮：种子（直接执行） ────────────────────────────────────────────────
INSERT INTO demo_disambig_expert (id, expert_id, name_zh, organization_name_zh, bio_zh, update_time) VALUES
  (101, 'E1001', '王伟', '清华大学',   '自然语言处理方向',         '2026-09-17 10:00:00'),
  (102, 'E1002', '李娜', '北京大学',   '计算机视觉方向',           '2026-09-17 10:00:00'),
  (103, 'E1003', '张敏', '复旦大学',   '数据库系统方向',           '2026-09-17 10:00:00'),
  (104, 'E1004', '刘洋', '浙江大学',   NULL,                       '2026-09-17 10:00:00');  -- 无简介：为第二轮「无可比属性」埋点

-- ── 第二轮：冲突（先注释着；第一轮抽取#1 完成后放开注释执行，再触发抽取#2） ──
-- INSERT INTO demo_disambig_expert (id, expert_id, name_zh, organization_name_zh, bio_zh, update_time) VALUES
--   (105, 'E2001', '王伟', '清华大学',     '自然语言处理方向',       '2026-09-17 12:00:00'),  -- merge：与 E1001 全一致
--   (106, 'E2002', '李娜', '北京大学',     '机器学习与图像识别方向', '2026-09-17 12:00:00'),  -- 灰区：单位同、简介异
--   (107, 'E2003', '张敏', '上海交通大学', '分布式系统方向',         '2026-09-17 12:00:00'),  -- 新建：单位、简介都不同
--   (108, 'E2004', '刘洋', NULL,           '集成电路与芯片设计方向', '2026-09-17 12:00:00');  -- 灰区：双方无可比属性

-- ----------------------------------------------------------------------------
-- A3 关系挂起：WORKS_AT 源表（pk=id，增量列 update_time）
-- 配合脚本内联机构别名表（浙江大学/浙大/中国科学院/中科院 唯一；华科 多义；
-- 其余未命中）。编排：建议在「A2 第二轮抽取后」运行——id=2 的边端点
-- expert_E2002 正处灰区扣留，可顺带演示边停靠（_pendingRelations）。
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS demo_works_at_relation;
CREATE TABLE demo_works_at_relation (
  id          INT          NOT NULL PRIMARY KEY,
  expert_id   VARCHAR(64)  NULL,
  expert_name VARCHAR(128) NULL,
  org_name    VARCHAR(256) NULL,
  position    VARCHAR(128) NULL,
  start_date  DATE         NULL,
  update_time DATETIME     NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO demo_works_at_relation (id, expert_id, expert_name, org_name, position, start_date, update_time) VALUES
  (1, 'E1001', '王伟', '浙江大学',     '兼职教授',   '2015-09-01', '2026-09-17 10:00:00'),  -- 唯一命中 → 出边
  (2, 'E2002', '李娜', '中国科学院',   '兼职研究员', '2022-06-01', '2026-09-17 10:00:00'),  -- 出边；expert_E2002 若在灰区扣留 → 边停靠
  (3, 'E1003', '张敏', '华科',         '客座研究员', '2020-03-01', '2026-09-17 10:00:00'),  -- 多义（2 候选）→ pendingReview
  (4, 'E1004', '刘洋', '未来科技大学', '副教授',     '2019-07-01', '2026-09-17 10:00:00'),  -- 未命中 → pendingReview
  (5, NULL,    '未知专家', '浙江大学', '研究员',     '2021-01-01', '2026-09-17 10:00:00'),  -- 毒行：expert_id 缺失
  (6, 'E1002', '李娜', NULL,           '研究员',     '2018-09-01', '2026-09-17 10:00:00');  -- 毒行：org_name 缺失
