# 专利图谱Schema

本目录只保留当前专利图谱设计与装载所需文件。

```text
schemas/
├── specifications/
│   ├── patent_ontology.md                本体、实体、属性、关系和约束
│   ├── patent_mapping.md                 源表到实体与索引字段的映射
│   └── patent_relation_extraction.md     逐关系抽取、对齐和消歧流程
├── ddl/
│   └── patent_ddl.ngql       Patent、Keyword和HAS_KEYWORD图Schema
└── README.md
```

执行顺序：

1. 新图空间首次初始化时执行`ddl/patent_ddl.ngql`。
2. MySQL抽取SQL位于`dao/sql/patent_entity_extract.sql`。
3. 日常装载运行`script/load_patent_graph.py`。
4. Schema不变时不重复执行DDL。
