# 数据库 Schema 说明

本目录维护与厂商源 MySQL 数据库 `gkx` 当前真实结构一致的字段规范和建表脚本。
DDL 与字段说明由 `script/sync_schema_from_mysql.py` 从 `information_schema` 和 `SHOW CREATE TABLE` 生成。

生成日期：`2026-06-25`
表总数：`93`
字段总数：`1686`

## 目录结构

```text
schemas/
├── specifications/    字段规范、表注释、字段注释和估算行数
├── ddl/               按数据域拆分的 MySQL 建表 SQL
└── README.md          本说明文件
```

## 数据域清单

| 数据域 | 字段规范 | DDL 目录 | 表数 | 字段数 | 估算行数 |
|---|---|---|---:|---:|---:|
| 人才专家 | `specifications/scholar.md` | `ddl/scholar/` | 6 | 67 | 759380 |
| 中文论文 | `specifications/chinese_paper.md` | `ddl/chinese_paper/` | 4 | 100 | 11481 |
| 外文论文 | `specifications/foreign_paper.md` | `ddl/foreign_paper/` | 6 | 154 | 253246 |
| 论文通用 | `specifications/paper_common.md` | `ddl/paper_common/` | 2 | 47 | 1619 |
| 专利 | `specifications/patent.md` | `ddl/patent/` | 9 | 273 | 7019 |
| 国内项目 | `specifications/domestic_project.md` | `ddl/domestic_project/` | 2 | 47 | 2891 |
| 国外项目 | `specifications/foreign_project.md` | `ddl/foreign_project/` | 2 | 46 | 2760 |
| 国内机构 | `specifications/domestic_organization.md` | `ddl/domestic_organization/` | 41 | 671 | 90024 |
| 国外机构 | `specifications/foreign_organization.md` | `ddl/foreign_organization/` | 10 | 63 | 58655 |
| 产业链 | `specifications/industry_chain.md` | `ddl/industry_chain/` | 5 | 60 | 10497 |
| 政策 | `specifications/policy.md` | `ddl/policy/` | 4 | 97 | 221 |
| 报告 | `specifications/report.md` | `ddl/report/` | 2 | 61 | 1039 |

## 维护规则

1. 当前目录以厂商源数据库 `gkx` 的真实表结构为准，不再保留旧版 62 表的冗余拆分定义。
2. 表之间不额外补充物理外键；若源库没有主键或索引，本目录也不人为添加。
3. 若远程库结构变化，重新执行同步脚本生成 DDL、字段规范和 ORM。
4. 同步脚本只读取数据库元数据，不读取业务数据，也不会修改远程数据库。

## 同步命令

```bash
SOURCE_MYSQL_HOST=183.240.141.251 \
SOURCE_MYSQL_PORT=3318 \
SOURCE_MYSQL_DATABASE=gkx \
SOURCE_MYSQL_USERNAME=gkx_reader_zp \
SOURCE_MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```
