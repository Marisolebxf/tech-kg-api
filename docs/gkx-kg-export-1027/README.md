# gkx_kg 库导出：15 张实体表 + 25 张按型关系表（2026-10-27，10-28 增补第 15 张）

来源： MySQL `gkx_kg` 库（本机 tech-kg-mysql），导出于 2026-10-27；2026-10-28 增补第 15 张实体表 `kg_scholar_organization`（结构与数据）。
范围（共 40 张表，不含 kg_edge 正典本体、mk_* 中间表与 v_ 视图）：

- **15 张实体表**（一实体一表设计）：1,025,272 行
- **25 张关系拆分表**（由 kg_edge 按 edge_type 拆出，2026-10-27 拆分对账 25/25 零差行）：1,159,390 行

## 文件说明

| 文件 | 内容 |
|---|---|
| `01-entity-tables.sql` | 15 张 kg_* 实体表建表语句 |
| `02-kg-edge-split-25.sql` | 25 张 kg_edge_* 建表语句 |
| `data-01-<表名>.sql.gz` | 各实体表数据（gzip 压缩 mysqldump） |
| `data-02-kg-edge-split-25.sql.gz` | 25 张拆分表数据 |
| `rowcounts.txt` | 39 表精确行数（导出时对账） |
| `MANIFEST.txt` | 文件大小 + SHA256 |

## 25 张拆分表行数（与拆分时 kg_edge GROUP BY edge_type 完全一致）

| 表 | 行数 |
|---|---|
| kg_edge_authored_by | 779,256 |
| kg_edge_coauthor_with | 156,144 |
| kg_edge_cites | 147,720 |
| kg_edge_has_keyword | 20,259 |
| kg_edge_involved_in | 13,477 |
| kg_edge_executive_of | 7,199 |
| kg_edge_beneficial_owner_of | 6,348 |
| kg_edge_invests_in | 4,069 |
| kg_edge_published_in | 4,000 |
| kg_edge_belongs_to_node | 2,951 |
| kg_edge_shareholder_of | 2,407 |
| kg_edge_produces | 2,146 |
| kg_edge_applied_by | 2,000 |
| kg_edge_member_of_family | 2,000 |
| kg_edge_invented_by | 1,957 |
| kg_edge_legal_rep_of | 1,874 |
| kg_edge_has_participant | 1,620 |
| kg_edge_affiliated_with | 1,129 |
| kg_edge_has_news | 1,013 |
| kg_edge_acquires | 953 |
| kg_edge_leads | 386 |
| kg_edge_has_node | 180 |
| kg_edge_funded_by | 150 |
| kg_edge_subsidiary_of | 102 |
| kg_edge_actual_controller_of | 50 |

## 15 张实体表行数

| 表 | 行数 |
|---|---|
| kg_event | 24,669 |
| kg_industry_chain | 3 |
| kg_industry_node | 180 |
| kg_journal | 2,134 |
| kg_keyword | 31,645 |
| kg_news | 1,489 |
| kg_organization | 19,870 |
| kg_paper | 742,127 |
| kg_patent | 2,010 |
| kg_patent_family | 1,999 |
| kg_person | 190,021 |
| kg_product | 2,072 |
| kg_project | 4,008 |
| kg_report | 3,000 |
| kg_scholar_organization | 45 |

## 重灌方法

```bash
mysql -e "CREATE DATABASE IF NOT EXISTS gkx_kg DEFAULT CHARSET utf8mb4"
mysql gkx_kg < 01-entity-tables.sql
mysql gkx_kg < 02-kg-edge-split-25.sql
for f in data-01-*.sql.gz data-02-kg-edge-split-25.sql.gz; do gzip -dc "$f" | mysql gkx_kg; done
```

## 字段口径

- 拆分表同构：`src_id varchar(256), dst_id varchar(256), edge_rank int, props json`，主键 `(src_id, dst_id, edge_rank)`，二级索引 `idx_dst(dst_id)`；行数合计 1,159,390 即原 kg_edge 全量（kg_edge 本体未入档，可由 25 张拆表 UNION ALL 还原）。
- 实体表为「一实体一表」终态设计，字段名沿用数仓。
- `kg_scholar_organization`（10-28 增补）： 学者机构，`org_id` = MD5(单位名) 前 16 位，**与 `kg_edge_affiliated_with.dst_id` 同键**（该边 dst 的落点表）；由 dwd_scholar_work_experience 单位名 DISTINCT 物化，45 行；此前以 `mk_scholar_organization` 名义使用，10-28 起 kg_ 正名。
- 关系表血缘： kg_rel_* 六源表 + 数仓事件表按型 UNION + 人工回填（HAS_NEWS/HAS_NODE/LEGAL_REP_OF 等，标记 MANUAL_BACKFILL）。
