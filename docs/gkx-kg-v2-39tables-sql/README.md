# gkx_kg_v2：39 张表 SQL（两卷）+ 九大业务测试数据文档

新库 `gkx_kg_v2`（宿主 tech-kg-mysql:30306）的 SQL 物料 + 测试数据文档。上游口径：只取 14 张实体表 + 25 张关系表，
kg_scholar_organization 不作第 15 张实体表，按三档口径并入 Organization（props 逐字段展开、一列一属性、新列 `confidence double`）。
配套图空间 `gkx_kg_v2`（14 TAG 1,025,180 点 / 25 EDGE 1,159,390 边，39 项对账一致）；46 组九大业务测试数据
**42 组逐字命中 dp_gkx 基线 + 4 组差异全归因**（详见测试数据文档）。

## 文件清单

| 文件 | 内容 | 大小 |
|---|---|---:|
| `01_gkx_kg_v2_part1_schema_entities.sql` | **全 39 张表 DDL** + 8 张实体表整表全量（含 v_organization 合并版 19,895 行 = 19,870 企业 + 25 学者） | 47MB |
| `02_gkx_kg_v2_part2_edges.sql` | 22 张关系表整表全量（含 ev_affiliated_with 键对齐改写版 1,129 行） | 56MB |
| `nine-modules-testdata-gkx-kg-v2.md` | **九大业务测试数据文档**（46 组，2026-10-27 实跑验证；查询带 `X-Business-Graph-Space: gkx_kg_v2`） | 11KB |

- **为什么分两卷**：39 张表完整数据单文件约 103MB，超 GitHub 单文件 100MB 硬限制，故按实体/关系分为两卷，导入顺序 01→02。
- **9 张大表（v_person/v_paper/v_patent/v_event/v_keyword/v_project/ev_authored_by/ev_coauthor_with/ev_has_keyword）全量数据数 GB 不在本包内**（同样超限），30 张小表已全量收录；大表全量灌数见附录 A（对源库 gkx_kg 只读执行）。
- 建库语句在 01 卷首注释：`CREATE DATABASE IF NOT EXISTS gkx_kg_v2 DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_general_ci;`

总计 39 张表 = 14 实体（v_person/v_paper/v_patent/v_patent_family/v_project/v_organization/v_news/v_event/v_journal/v_keyword/v_report/v_product/v_industry_chain/v_industry_node）+ 25 关系（ev_acquires … ev_subsidiary_of）。

## 两键提醒

1. **ev_* 边表存带前缀 vid**（`person_xxx`/`paper_xxx`/`org_xxx`/`node_xxx`），**v_* 实体表存裸主键**（`xxx`）。图上 vid = 前缀 + 实体表主键。
2. **演示造数排除口径**（与 gkx_kg_full 一致，作用于建图时）：Paper 排除 `id LIKE '889900%'`（17 篇）；Organization 排除 `org_id LIKE 'MOCK%'` 与首字符为引号的行（52 行）。本包表数据为**如实快照**未剔除，重建图时由构建脚本排除；46 组验证结论均基于排除后口径（4 组差异中的 3 组即源于此，见测试数据文档）。

## 建图与验证（完整链路见 backend/script/gkx_kg_v2_build/）

```bash
PYTHONPATH=/app python -m script.gkx_kg_v2_build.create_space             # 建空间
PYTHONPATH=/app python -m script.gkx_kg_v2_build.register --database gkx_kg_v2 \
    --graph-space gkx_kg_v2 --datasource-id MYSQL-A176CF7A                # Schema+绑定+脚本
PYTHONPATH=/app python -m script.gkx_kg_v2_build.load_entities_ngql       # 14 TAG 直写
PYTHONPATH=/app python -m script.gkx_kg_v2_build.launch_clean_relations   # 净端点 14 边型走链
PYTHONPATH=/app python -m script.gkx_kg_v2_build.load_edges_ngql          # 悬挂 11 边型直写
PYTHONPATH=/app python -m script.gkx_kg_v2_build.verify_space             # 39 项对账
```

九大业务查询带请求头 `X-Business-Graph-Space: gkx_kg_v2` 即路由到新空间。

## 附录 A：9 大表全量灌数 / 从源库全量重建 39 张表

对源库 `gkx_kg` 只读执行（源库零改动；可重复执行前先 DROP 库）。前 30 张小表如已按 01/02 卷导入可跳过对应语句。

```sql
CREATE DATABASE IF NOT EXISTS gkx_kg_v2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- 13 张实体副本（LIKE 保结构）
CREATE TABLE gkx_kg_v2.v_person LIKE gkx_kg.kg_person;        INSERT INTO gkx_kg_v2.v_person SELECT * FROM gkx_kg.kg_person;
CREATE TABLE gkx_kg_v2.v_paper LIKE gkx_kg.kg_paper;          INSERT INTO gkx_kg_v2.v_paper SELECT * FROM gkx_kg.kg_paper;
CREATE TABLE gkx_kg_v2.v_patent LIKE gkx_kg.kg_patent;        INSERT INTO gkx_kg_v2.v_patent SELECT * FROM gkx_kg.kg_patent;
CREATE TABLE gkx_kg_v2.v_patent_family LIKE gkx_kg.kg_patent_family; INSERT INTO gkx_kg_v2.v_patent_family SELECT * FROM gkx_kg.kg_patent_family;
CREATE TABLE gkx_kg_v2.v_project LIKE gkx_kg.kg_project;      INSERT INTO gkx_kg_v2.v_project SELECT * FROM gkx_kg.kg_project;
CREATE TABLE gkx_kg_v2.v_news LIKE gkx_kg.kg_news;            INSERT INTO gkx_kg_v2.v_news SELECT * FROM gkx_kg.kg_news;
CREATE TABLE gkx_kg_v2.v_event LIKE gkx_kg.kg_event;          INSERT INTO gkx_kg_v2.v_event SELECT * FROM gkx_kg.kg_event;
CREATE TABLE gkx_kg_v2.v_journal LIKE gkx_kg.kg_journal;      INSERT INTO gkx_kg_v2.v_journal SELECT * FROM gkx_kg.kg_journal;
CREATE TABLE gkx_kg_v2.v_keyword LIKE gkx_kg.kg_keyword;      INSERT INTO gkx_kg_v2.v_keyword SELECT * FROM gkx_kg.kg_keyword;
CREATE TABLE gkx_kg_v2.v_report LIKE gkx_kg.kg_report;        INSERT INTO gkx_kg_v2.v_report SELECT * FROM gkx_kg.kg_report;
CREATE TABLE gkx_kg_v2.v_product LIKE gkx_kg.kg_product;      INSERT INTO gkx_kg_v2.v_product SELECT * FROM gkx_kg.kg_product;
CREATE TABLE gkx_kg_v2.v_industry_chain LIKE gkx_kg.kg_industry_chain; INSERT INTO gkx_kg_v2.v_industry_chain SELECT * FROM gkx_kg.kg_industry_chain;
CREATE TABLE gkx_kg_v2.v_industry_node LIKE gkx_kg.kg_industry_node;   INSERT INTO gkx_kg_v2.v_industry_node SELECT * FROM gkx_kg.kg_industry_node;

-- Organization 合并版：50 原列 + confidence 新列（③档 25 行 props 逐字段展开）
CREATE TABLE gkx_kg_v2.v_organization LIKE gkx_kg.kg_organization;
ALTER TABLE gkx_kg_v2.v_organization
  ADD COLUMN confidence double NULL
  COMMENT '置信度(scholar_affiliation行=dwd_scholar_work_experience物化props.confidence,企业行NULL)';
INSERT INTO gkx_kg_v2.v_organization SELECT o.*, NULL FROM gkx_kg.kg_organization o;
INSERT INTO gkx_kg_v2.v_organization
  (org_id, name_cn, name_en, org_kind, confidence,
   source_table, source_record_id, ingest_batch, ingest_time)
SELECT s.org_id, s.name_zh, NULLIF(s.name_en, ''),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.org_kind')),
       CAST(JSON_EXTRACT(s.props, '$.confidence') AS DOUBLE),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_table')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_record_id')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_batch')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_time'))
FROM gkx_kg.kg_scholar_organization s
WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
  AND NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization o WHERE o.name_cn = s.name_zh);

-- 24 张关系表原样副本
CREATE TABLE gkx_kg_v2.ev_acquires AS SELECT * FROM gkx_kg.ev_acquires;
CREATE TABLE gkx_kg_v2.ev_actual_controller_of AS SELECT * FROM gkx_kg.ev_actual_controller_of;
CREATE TABLE gkx_kg_v2.ev_applied_by AS SELECT * FROM gkx_kg.ev_applied_by;
CREATE TABLE gkx_kg_v2.ev_authored_by AS SELECT * FROM gkx_kg.ev_authored_by;
CREATE TABLE gkx_kg_v2.ev_belongs_to_node AS SELECT * FROM gkx_kg.ev_belongs_to_node;
CREATE TABLE gkx_kg_v2.ev_beneficial_owner_of AS SELECT * FROM gkx_kg.ev_beneficial_owner_of;
CREATE TABLE gkx_kg_v2.ev_cites AS SELECT * FROM gkx_kg.ev_cites;
CREATE TABLE gkx_kg_v2.ev_coauthor_with AS SELECT * FROM gkx_kg.ev_coauthor_with;
CREATE TABLE gkx_kg_v2.ev_executive_of AS SELECT * FROM gkx_kg.ev_executive_of;
CREATE TABLE gkx_kg_v2.ev_funded_by AS SELECT * FROM gkx_kg.ev_funded_by;
CREATE TABLE gkx_kg_v2.ev_has_keyword AS SELECT * FROM gkx_kg.ev_has_keyword;
CREATE TABLE gkx_kg_v2.ev_has_news AS SELECT * FROM gkx_kg.ev_has_news;
CREATE TABLE gkx_kg_v2.ev_has_node AS SELECT * FROM gkx_kg.ev_has_node;
CREATE TABLE gkx_kg_v2.ev_has_participant AS SELECT * FROM gkx_kg.ev_has_participant;
CREATE TABLE gkx_kg_v2.ev_invented_by AS SELECT * FROM gkx_kg.ev_invented_by;
CREATE TABLE gkx_kg_v2.ev_invests_in AS SELECT * FROM gkx_kg.ev_invests_in;
CREATE TABLE gkx_kg_v2.ev_involved_in AS SELECT * FROM gkx_kg.ev_involved_in;
CREATE TABLE gkx_kg_v2.ev_leads AS SELECT * FROM gkx_kg.ev_leads;
CREATE TABLE gkx_kg_v2.ev_legal_rep_of AS SELECT * FROM gkx_kg.ev_legal_rep_of;
CREATE TABLE gkx_kg_v2.ev_member_of_family AS SELECT * FROM gkx_kg.ev_member_of_family;
CREATE TABLE gkx_kg_v2.ev_produces AS SELECT * FROM gkx_kg.ev_produces;
CREATE TABLE gkx_kg_v2.ev_published_in AS SELECT * FROM gkx_kg.ev_published_in;
CREATE TABLE gkx_kg_v2.ev_shareholder_of AS SELECT * FROM gkx_kg.ev_shareholder_of;
CREATE TABLE gkx_kg_v2.ev_subsidiary_of AS SELECT * FROM gkx_kg.ev_subsidiary_of;

-- affiliated_with 键对齐版：①档 81 条 dst 不变；③档 796 条 dst 不变；②档 252 条 dst 改至同名企业键
CREATE TABLE gkx_kg_v2.ev_affiliated_with AS
SELECT e.src_id AS src_id,
       COALESCE(m.new_vid, e.dst_id) AS dst_id,
       e.edge_rank AS edge_rank,
       e.props_json AS props_json
FROM gkx_kg.ev_affiliated_with e
LEFT JOIN (
  SELECT CONCAT('org_', s.org_id COLLATE utf8mb4_general_ci) AS old_vid,
         CONCAT('org_', o.org_id COLLATE utf8mb4_general_ci) AS new_vid
  FROM gkx_kg.kg_scholar_organization s
  JOIN gkx_kg.kg_organization o
    ON o.name_cn COLLATE utf8mb4_general_ci = s.name_zh COLLATE utf8mb4_general_ci
  WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
) m ON e.dst_id COLLATE utf8mb4_general_ci = m.old_vid COLLATE utf8mb4_general_ci;
```

## 附录 B：学者机构合并审计（kg_scholar_organization 45 行 → v_organization 三档并入）

- ①同键 3 行（濠江測試數碼有限公司033 / 深圳市意天科技有限公司 / 清华大学计算机科学与技术系）：企业行已在 kg_organization，不导；81 条 affiliated_with 天然落企业键。
- ②同名不同键 17 行：不插行（避免同机构双顶点），252 条边 dst 改写至同名企业键（映射见下表）。
- ③纯学术缺失 25 行：INSERT 进 v_organization（confidence=0.6），796 条边落新键。
- 合计 81 + 252 + 796 = **1,129 条 affiliated_with 全部落 Organization 顶点**。

| 机构名 | 旧学者键 | 企业键 | 边数 |
|---|---|---|---:|
| 上海优宁维生物科技股份有限公司 | org_c9f0aeedec969a7a | org_059513c5797a1d7a3dfc8f8869c121d9 | 15 |
| 深圳前海骁客影像科技设计有限公司 | org_416f915d6dd55986 | org_040dd8acf11fa9dd34b6a4d85d5a1a81 | 15 |
| 法狮龙家居建材股份有限公司 | org_d28659e2040f5597 | org_0344e298274b97c8d5ae73c4ca56d7eb | 15 |
| 曼卡龙珠宝股份有限公司 | org_ce99386b26af7572 | org_04f92753c7f5da3b263b4fcc0f63adf9 | 15 |
| 宁夏凯添燃气发展股份有限公司 | org_8db6a0babaf97e2c | org_045d4a9b4621c5ef43acc5843955a157 | 15 |
| 四川安宁铁钛股份有限公司 | org_99d7d661612b4626 | org_0450afbd6e538fc350907b69806a91a5 | 15 |
| 金徽矿业股份有限公司 | org_50c0d243346a9821 | org_04305390561d54bd193d03223b74c9ab | 15 |
| 广东冠豪高新技术股份有限公司 | org_4b0035278409f065 | org_015e387d77361b95b2f6953a92059510 | 15 |
| 深圳市英威腾电气股份有限公司 | org_2872f986f442dc89 | org_04b75452bd230e38bd160bb12c13ce9e | 15 |
| 徐工集团工程机械股份有限公司 | org_8e29e54ff2065732 | org_047583dfefe252480e530d15c0d436df | 15 |
| 东方财富信息股份有限公司 | org_c80fc5d270af0bbc | org_04396b49d8e61600c5df4122d01255d4 | 15 |
| 上海雅创电子集团股份有限公司 | org_5152a01ff74054f8 | org_03226042bc98f15da8af47dfef8c3612 | 15 |
| 深圳市劲拓自动化设备股份有限公司 | org_03bb3039720c5388 | org_02c54b80822a08444c66d4f8be9d5304 | 15 |
| 金能科技股份有限公司 | org_0a0c3cfc66a9173c | org_028b0a4ebfb6ecaf48288dbd14272b33 | 15 |
| 新智认知数字科技股份有限公司 | org_988fc53d4950af9c | org_000213e718b09bd45e71789553cc53d7 | 15 |
| 北京航空材料研究院股份有限公司 | org_625476ac3c7a83fc | org_00a94a6adc3c65b318b7aeb0ea240ef9 | 14 |
| 江苏徐矿能源股份有限公司 | org_7cf77bdebc5e134e | org_057bd3d003c92ce097d82d9beeba3e2d | 13 |

建成后自检（gkx_kg_v2 内执行，期望值如注）：

```sql
SELECT COUNT(*) FROM v_organization;                              -- 19,895（19,870 企业 + 25 学者）
SELECT COUNT(*) FROM v_organization WHERE confidence IS NOT NULL; -- 25（全 =0.6）
SELECT COUNT(*) FROM ev_affiliated_with;                          -- 1,129
SELECT COUNT(*) FROM ev_affiliated_with e                         -- 0（旧学者键残留应为零，dst 全部可解析）
  LEFT JOIN v_organization o
    ON o.org_id = SUBSTRING(e.dst_id, 5) COLLATE utf8mb4_general_ci
 WHERE o.org_id IS NULL;
```
