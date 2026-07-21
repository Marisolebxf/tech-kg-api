# 国内外项目：SQL → Graph 字段级映射

> 责任域：国内外项目（兴坤）  
> 本体：[`docs/ontology.md`](../../docs/ontology.md) Tag `Project`  
> 总表映射：[`docs/mapping.md`](../../docs/mapping.md) §6  
> 图空间：TRSGraph **`dev`**  
> 源库默认：`gkx_local` 的 `ods_*_project*`（与 mapping 中 `dwd_*_project*` 字段一一对应）

## 0. 命名对照

| mapping.md / 要素库语义名 | 本仓库 `gkx_local` 实际表名 | 说明 |
|---------------------------|------------------------------|------|
| `dwd_zh_project` | `ods_zh_project` | 国内项目主表 |
| `dwd_en_project` | `ods_en_project` | 国外项目主表 |
| `dwd_zh_project_output` | `ods_zh_project_output` | 国内项目产出 |
| `dwd_en_project_output` | `ods_en_project_output` | 国外项目产出 |
| `dwd_rel_project_paper` | （211/`gkx_local` 当前不存在） | 有表则建 `OUTPUT_OF` |
| `dwd_rel_project_patent` | （211/`gkx_local` 当前不存在） | 有表则建 `OUTPUT_OF` |

**探测结论（2026-07-21，`gkx_local`）：**

- `ods_zh_project` / `ods_zh_project_output` 行数一致（约 2000），且 **`output.id = project.id`**（1:1）。
- `ods_en_project` / `ods_en_project_output` 同理（约 1994）。
- 无 `*_rel_project_*` 表；产出边来自 output 表 JSON 字段。

## 1. 通用规则

### 1.1 VID

| 实体 | VID | 说明 |
|------|-----|------|
| Project | `project_{id}` | `id` 为项目主键（UUID） |
| Person（桩） | `person_{md5(norm_name)}` | 来自主持人/参与人姓名 |
| Organization（桩） | `org_{md5(norm_name)}` | 来自依托/参与单位名 |
| Keyword | `keyword_{md5(norm)}` | 关键词小写 trim |
| Paper（桩） | `paper_{md5(title\|doi)}` | output JSON 无 paper_id 时 |
| Patent（桩） | `patent_{patent_number}` 或 `patent_{md5(title)}` | 优先公开号/申请号 |
| DataSource | `ds_{source_table}` | 每张源表一个 |

名称规范化：`strip` + 连续空白压成单空格；关键词额外 `lower()`。

### 1.2 顶点溯源块（7 字段）

| 图属性 | 取值 |
|--------|------|
| `source_system` | 固定 `gkx_local`（要素副本入图） |
| `source_table` | 实际表名，如 `ods_zh_project` |
| `source_record_id` | 行主键 `id` |
| `source_url` | `project_page_url`（可空） |
| `ingest_batch` | ETL 注入，如 `BATCH_20260721_01` |
| `ingest_time` | ETL 执行时间 ISO8601 |
| `source_update_time` | `update_time` → 字符串 |

### 1.3 边溯源块（4 字段）

`source_table`、`source_record_id`、`ingest_batch`、`ingest_time`。边的 `source_table` 为生成该边的表（通常为主表或 output 表），独立于端点溯源。

---

## 2. `ods_zh_project` → Tag `Project` + 边

| # | SQL 字段 | 类型 | 图映射 | disposition |
|---|----------|------|--------|-------------|
| 1 | `id` | varchar(64) PK | VID `project_{id}`；溯源 `source_record_id` | 入图 |
| 2 | `project_number` | varchar(64) | `Project.project_number` | 入图；建索引 |
| 3 | `title` | varchar(1000) | `Project.title` | 入图 |
| 4 | `project_source` | varchar(128) | `Project.project_source` | 入图 |
| 5 | `funded_institution` | varchar(255) | **边** `FUNDED_BY`：Project → Organization 桩；不落 Project 业务属性 | 展开为边 |
| 6 | `project_level` | varchar(64) | `Project.project_level` | 入图 |
| 7 | `funded_amount` | decimal(12,2) | `Project.funded_amount` + `FUNDED_BY.funded_amount` | 入图 |
| 8 | `discipline` | varchar(500) | `Project.discipline` | 入图 |
| 9 | `discipline_code` | varchar(128) | `Project.discipline_code` | 入图 |
| 10 | `fund_category` | varchar(128) | `Project.fund_category` + `FUNDED_BY.fund_category` | 入图 |
| 11 | `funded_province` | varchar(64) | `Project.funded_region` | 入图（属性名按 ontology） |
| 12 | `participating_institution` | varchar(255) | **边** `PARTICIPATES_IN`：Organization → Project | 展开为边 |
| 13 | `approval_year` | date | `Project.approval_year`（`YYYY-MM-DD` 或取年） | 入图 |
| 14 | `approval_time` | date | `Project.approval_time`（`YYYY-MM-DD`） | 入图 |
| 15 | `research_period` | varchar(128) | `Project.research_period` | 入图 |
| 16 | `project_host` | varchar(100) | **边** `LEADS`：Project → Person 桩 | 展开为边 |
| 17 | `participants` | mediumtext JSON | **边** `HAS_PARTICIPANT`：每个姓名一条 | UNWIND |
| 18 | `keywords` | mediumtext JSON | Tag `Keyword` + **边** `HAS_KEYWORD` | UNWIND |
| 19 | `abstract` | mediumtext | `Project.abstract` | 入图 |
| 20 | `final_report_abstract` | mediumtext | `Project.final_report_abstract` | 入图（仅 zh） |
| 21 | `project_page_url` | varchar(1024) | `Project.project_page_url` + 溯源 `source_url` | 入图 |
| 22 | `create_time` | datetime | 不单列业务属性；可参考入溯源 | 并入溯源 |
| 23 | `update_time` | datetime | 溯源 `source_update_time` | 并入溯源 |

固定属性：`Project.source = "zh_project"`。

### 2.1 边明细

| Edge | 方向 | 触发字段 | 边属性 |
|------|------|----------|--------|
| `FUNDED_BY` | Project → Organization | `funded_institution` | `funded_amount`, `fund_category` + 边溯源 |
| `LEADS` | Project → Person | `project_host` | 边溯源 |
| `HAS_PARTICIPANT` | Project → Person | `participants[]` | 边溯源 |
| `PARTICIPATES_IN` | Organization → Project | `participating_institution`（JSON/逗号分隔） | 边溯源 |
| `HAS_KEYWORD` | Project → Keyword | `keywords[]` | 边溯源 |
| `SOURCED_FROM` | Project → DataSource | 每行 | `source_record_id`, `ingest_batch`, `ingest_time` |

---

## 3. `ods_en_project` → Tag `Project` + 边

字段映射与 §2 相同，差异：

| 差异项 | 说明 |
|--------|------|
| 无 `final_report_abstract` 列 | 图属性置空字符串 |
| `Project.source` | 固定 `en_project` |
| `source_table` | `ods_en_project` |
| 文本语言 | title/abstract/机构名多为英文；桩 VID 仍按规范化字符串 md5 |

其余 `project_number`…`project_page_url`、`create_time`/`update_time` 及边规则同 §2。

---

## 4. `ods_zh_project_output` / `ods_en_project_output`

> **关联约定**：主键 `id` **等于** 对应项目表 `id`（已在 `gkx_local` 抽样验证）。映射文档与假数据均按此约定；若源库未来变更需增加显式 `project_id`。

### 4.1 计数字段 → 更新 `Project` 属性

| SQL 字段 | 图属性 |
|----------|--------|
| `total_outputs` | `Project.total_outputs` |
| `journal_articles_count` | `Project.journal_articles_count` |
| `conference_papers_count` | `Project.conference_papers_count` |
| `books_count` | `Project.books_count` |
| `degree_papers_count` | `Project.degree_papers_count` |
| `patents_count` | `Project.patents_count` |
| `clinical_trials_count` | `Project.clinical_trials_count` |
| `products_count` | `Project.products_count` |
| `awards_count` | `Project.awards_count` |
| `reports_count` | `Project.reports_count` |
| `other_outputs_count` | `Project.other_outputs_count` |
| `create_time` / `update_time` | 不覆盖主表溯源；边溯源可用 output 表名 |

### 4.2 JSON 产出 → `OUTPUT_OF` 边

| SQL 字段 | 终点实体 | 对齐键 | 边 |
|----------|----------|--------|----|
| `output_journal_articles` | Paper | `doi` / `title` → VID | Paper → Project `OUTPUT_OF` |
| `output_conference_papers` | Paper | 同上 | 同上 |
| `output_degree_papers` | Paper | 同上 | 同上 |
| `output_patents` | Patent | `patent_number` / `patent_title` | Patent → Project `OUTPUT_OF` |
| `output_books` / `output_clinical_trials` / `output_products` / `output_awards` / `output_reports` / `output_other` | 本期不建独立 Tag | 内容可忽略或仅计数字段已覆盖 | **暂不入图实体**（disposition: count-only） |

样例 JSON（期刊）：

```json
{"title": "...", "authors": ["..."], "journal": "..."}
```

样例 JSON（专利）：

```json
{"patent_title": "...", "patent_number": "201811394750.6", "patent_inventor": ["..."]}
```

无 DOI/`paper_id` 时建桩 Paper：`paper_{md5(title)}`，属性 `title` + `source=project_stub`。

---

## 5. 关系表（可选，当前库不存在）

若后续出现：

### 5.1 `dwd_rel_project_paper`

| 字段 | 映射 |
|------|------|
| `paper_id` | 起点 `paper_{paper_id}` |
| `project_id` | 终点 `project_{project_id}` |
| （逻辑主键） | 边溯源 `source_record_id` |

边：`OUTPUT_OF`（Paper → Project）。

### 5.2 `dwd_rel_project_patent`

| 字段 | 映射 |
|------|------|
| `patent_id` | 起点 `patent_{patent_id}` |
| `project_id` | 终点 `project_{project_id}` |

边：`OUTPUT_OF`（Patent → Project）。

---

## 6. 桩节点最小属性

> `dev` 空间上 Person / Organization / Paper / DataSource 可能已由同事建成更宽 schema。ETL **适配已有列**，不写入不存在的属性（例如不用 `Organization.source`）。

| Tag | 写入属性（适配 `dev` 现网） | 桩标记 |
|-----|---------------------------|--------|
| `Person` | `name_cn` / `name_en` + 溯源块 | `person_kind=project_stub` |
| `Organization` | `org_id`, `name_cn` / `name_en` + 溯源块 | `org_kind=project_stub` |
| `Keyword` | `keyword` + 溯源块 | — |
| `Paper` | `title_zh` / `title_en`, `doi` + 溯源块 | — |
| `Patent` | `publication_number` / `title`，`source=project_stub` + 溯源块 | `source=project_stub` |
| `DataSource` | `source_table`, `table_cn_name`, `tier=raw`, `library=gkx_local` | — |

同事灌入真实 Person/Organization/Paper/Patent 后，可用 `SAME_AS` 或名称对齐合并桩节点（本期不做自动合并）。

---

## 7. 跨域协作约定（假数据共享 ID）

| 协作方 | 共享内容 |
|--------|----------|
| 亚涛（论文） | 假 Paper VID：`paper_fake_proj_001` … `_003`（若对方建点，output JSON 的 title 可对齐） |
| 鑫凤（专利） | 假公开号：`CN201811394750.6` 风格与 fake 项目产出一致 |
| 伟宁（学者） | 主持人名「王岩飞」「张伟」等可对齐 Person |
| 周威（机构） | 「清华大学」「中国科学院空天信息创新研究院」等可对齐 Organization |

演示专用项目主键：`fake-zh-proj-001` … `fake-zh-proj-008`，`fake-en-proj-001` … `fake-en-proj-008`。

---

## 8. 验收 nGQL（space=`dev`）

```ngql
USE dev;
FETCH PROP ON Project "project_fake-zh-proj-001" YIELD properties(vertex);
GO FROM "project_fake-zh-proj-001" OVER LEADS, FUNDED_BY YIELD dst(edge);
GO FROM "project_fake-zh-proj-001" OVER HAS_KEYWORD YIELD dst(edge);
GO FROM "project_fake-zh-proj-001" OVER OUTPUT_OF REVERSELY YIELD src(edge);
```

---

## 9. 代码入口

| 步骤 | 命令 |
|------|------|
| 灌假数据 | `docker exec -i mysql mysql -uroot -p... gkx_local < backend/schemas/seed/project_fake_data.sql` |
| 建 Schema | `cd backend && TRS_GRAPH_SPACE=dev uv run python -m script.init_project_schema` |
| 入图 | `cd backend && TRS_GRAPH_SPACE=dev uv run python -m script.load_project_graph --id-prefix fake-` |
| 全量（可选） | `uv run python -m script.load_project_graph --limit 500` |
