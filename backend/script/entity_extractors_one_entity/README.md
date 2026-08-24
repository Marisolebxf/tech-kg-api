# One Entity Per Script Extractors

This folder is a refactored entity extraction implementation. It does not import, delegate to, or copy the old ETL scripts under `backend/script/load_*`, `backend/script/organization_*`, or `backend/script/workflow/*`.

The design principle is one graph entity Tag per entrypoint:

- Each script declares its own source tables and SQL.
- `mappers.py` contains explicit field mapping functions for each entity type.
- `org_catalog.py` holds the organization-domain table catalog (table names, Chinese
  names, entity kinds, composite stable keys), replicating the legacy
  `DOMAIN_TABLE_SPECS`.
- `common.py` contains shared extraction primitives: MySQL paging (OFFSET or keyset
  cursor), VID helpers, provenance, `extra_json` preservation, and graph writes.
- Every source row is preserved in `extra_json`, so fields not mapped to first-class
  graph properties are still retained.

## Legacy-equivalent behavior

Entity data content is strictly aligned with the legacy scripts (see
`docs/实体抽取脚本旧新逻辑等价性清单.md` for the full checklist):

- Stable VID conventions replicate the legacy formulas exactly, including
  `person_{md5(kind|org|name|birth|country)}`, `product_{md5(normalized name)}`
  (full 32-char md5), `event_{table}_{composite key}`, `news_{table}_{row hash}`
  for org news, and `ds_{table}` for DataSource.
- Organization-domain entities (Organization/Event/News/Product/Person
  organization-role) use the legacy text/number semantics: blank values become
  NULL (omitted properties), 20K truncation, `entity_confidence` dynamic scoring,
  virtual/synthetic source-row filtering, and legacy field candidate chains.
- Organization-domain writes read existing nodes first and replicate the legacy
  merge protection: preserve existing non-null canonical properties, confidence
  never decreases, and `extra_json.source_records` accumulates every source row.
- Paper/Journal/Report/Patent/Project keep the legacy `value or ""` raw-text
  semantics; Patent replicates `original_text`/`normalized_language`/
  `json_snapshot`/`ngql_datetime` value semantics and the keyset cursor paging
  (`CAST(p.id AS UNSIGNED) > :cursor`); Project replicates field-completeness
  confidence scoring.
- `--since` incremental mode (`updated_time > since`) is supported wherever the
  legacy scripts had it (Paper/Journal/Report/News/机构域).

Intentionally retained architectural differences: per-record `merge_node` HTTP
upsert instead of batched nGQL `INSERT VERTEX`, no `organization_base` mixin tag
(provenance lives as node properties), dynamic `ingest_batch`/`ingest_time`,
uniform `vid`/`match_method`/`match_evidence` properties, and edges are out of
scope (separate relation scripts).

## Entrypoints

| Entity | Script |
| --- | --- |
| `Person` | `python -m script.entity_extractors_one_entity.person_entity`（`--source scholar/paper-author/organization-role`） |
| `Organization` | `python -m script.entity_extractors_one_entity.organization_entity` |
| `Project` | `python -m script.entity_extractors_one_entity.project_entity`（`--project-id`/`--id-prefix`） |
| `Paper` | `python -m script.entity_extractors_one_entity.paper_entity` |
| `Journal` | `python -m script.entity_extractors_one_entity.journal_entity` |
| `Patent` | `python -m script.entity_extractors_one_entity.patent_entity` |
| `PatentFamily` | `python -m script.entity_extractors_one_entity.patent_family_entity` |
| `Keyword` | `python -m script.entity_extractors_one_entity.keyword_entity` |
| `Report` | `python -m script.entity_extractors_one_entity.report_entity` |
| `Event` | `python -m script.entity_extractors_one_entity.event_entity` |
| `News` | `python -m script.entity_extractors_one_entity.news_entity` |
| `Product` | `python -m script.entity_extractors_one_entity.product_entity` |
| `IndustryChain` | `python -m script.entity_extractors_one_entity.industry_chain_entity` |
| `IndustryNode` | `python -m script.entity_extractors_one_entity.industry_node_entity` |
| `DataSource` | `python -m script.entity_extractors_one_entity.datasource_entity` |

## Common Options

Most scripts support:

```bash
--database gkx_element
--batch-size 500
--limit 100
--since 2026-01-01T00:00:00
--dry-run
--ingest-batch BATCH_ID
```

`--dry-run` reads and maps data but does not write graph nodes. `--since` injects
`updated_time > :since` into each source SQL.

## Scope

These scripts only extract entities. Relationship extraction should be handled by
separate relation scripts.
