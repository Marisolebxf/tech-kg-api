# 数据库 Schema 说明

本目录只维护要素库的字段规范和 MySQL 建表脚本，用于将已确认的表结构导入实验室 MySQL 数据库。

当前阶段不维护示范数据，不建立表之间的物理外键约束，也不维护独立的关系建表脚本。表之间的关联只作为逻辑关系保留在字段规范、字段命名和后端查询/图谱构建逻辑中。

## 目录结构

```text
schemas/
├── specifications/    字段规范、来源说明、JSON 字段说明和待确认项
├── ddl/               正式建表 SQL，按数据域分目录
└── README.md          本说明文件
```

正式建表只以 `specifications/` 和 `ddl/` 为准。

## 数据域清单

| 数据域 | 字段规范 | DDL 目录 | 表数 |
|---|---|---|---:|
| 人才专家 | `specifications/scholar.md` | `ddl/scholar/` | 6 |
| 专利 | `specifications/patent.md` | `ddl/patent/` | 5 |
| 国内机构 | `specifications/domestic_organization.md` | `ddl/domestic_organization/` | 16 |
| 国外机构 | `specifications/foreign_organization.md` | `ddl/foreign_organization/` | 8 |
| 中文论文 | `specifications/chinese_paper.md` | `ddl/chinese_paper/` | 9 |
| 外文论文 | `specifications/foreign_paper.md` | `ddl/foreign_paper/` | 10 |
| 国内项目 | `specifications/domestic_project.md` | `ddl/domestic_project/` | 2 |
| 国外项目 | `specifications/foreign_project.md` | `ddl/foreign_project/` | 2 |
| 产业链 | `specifications/industry_chain.md` | `ddl/industry_chain/` | 4 |

当前共维护 9 个数据域、62 张表。

## 执行规则

1. 先阅读对应的 `specifications/*.md`，确认字段来源、类型映射、JSON 字段和待确认项。
2. 按文件名前的两位编号依次执行对应 `ddl/<数据域>/` 下的 SQL。
3. 不执行示范数据脚本。
4. 不执行关系表或外键脚本。
5. 不根据旧版合并 SQL 反向覆盖当前拆分后的 DDL。

例如，初始化人才专家表时：

```text
ddl/scholar/01_dwd_scholar.sql
ddl/scholar/02_dwd_scholar_talent_flag.sql
ddl/scholar/03_dwd_scholar_research_direction.sql
ddl/scholar/04_dwd_scholar_paper_relation.sql
ddl/scholar/05_dwd_scholar_papers.sql
ddl/scholar/06_dwd_scholar_coauthor.sql
```

## 建模约定

1. 第三方提供了英文表名和字段名时，DDL 保持原名。
2. 第三方只提供中文名称时，项目建议英文名必须在规范文档中明确标注。
3. 当前只约束单表结构：字段名、字段类型、字段长度、可空性、普通索引和必要主键。
4. 不主动建立表之间的物理外键，避免字段名、类型或导入顺序变化导致建库和导数失败。
5. 表之间需要关联时，保留统一 ID 字段和普通索引，由后端查询、数据处理或图谱构建逻辑按需关联。
6. JSON 主字段只建立一个物理列，JSON 内部属性记录在规范文档中，不拆成多个 SQL 列。
7. 明确标记为“深化设计中删除”的字段不进入 DDL，但保留在规范文档的原始记录或说明中。

## 修改流程

字段发生变化时，按以下顺序更新：

1. 更新 `specifications/` 中的字段规范和变更说明。
2. 同步修改对应的 `ddl/` 建表脚本。
3. 核对 README 中的数据域、表数和执行说明。
4. 将更新后的 DDL 导入实验室 MySQL 前，先确认同一数据域内表数量和字段数量无误。

不要只修改 DDL 而遗漏字段规范，也不要为了表达表关系额外添加 `FOREIGN KEY`。
