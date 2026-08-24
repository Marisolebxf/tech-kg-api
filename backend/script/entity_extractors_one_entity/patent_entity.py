"""One-entity extractor for Patent.

聚合 SQL 复刻旧 dao/sql/patent_entity_extract.sql（过滤 ``p.id REGEXP '^[0-9]+$'``），
分页复刻旧 keyset 游标（``CAST(p.id AS UNSIGNED) > :cursor``）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import patent_record

PATENT_SQL = """
SELECT
  p.id AS source_row_id, p.patent_id, p.publication_number,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apno')) AS application_number,
  p.application_kind, p.country_code, p.country,
  JSON_UNQUOTE(JSON_EXTRACT(p.publication_reference, '$.pbdt')) AS publication_date,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apdt')) AS application_date,
  p.granted_number,
  JSON_UNQUOTE(JSON_EXTRACT(l.dates_of_public_availability, '$.date')) AS grant_date,
  l.status, l.anticipated_expiration, t.titles,
  t.title_localized AS title_en, t.title_zh, a.abstract_zh, p.language,
  p.main_classification_ipcr AS main_ipcr,
  p.further_classification_ipcr AS further_ipcr,
  p.main_classification_cpc AS main_cpc,
  p.further_classification_cpc AS further_cpc,
  p.keywords, c.reference_cited AS citation_nums, c.cited_by_nums,
  p.value AS patent_value, f.simple_family_number,
  p.db_source, p.create_time, p.update_time
FROM dwd_patent p
LEFT JOIN (
  SELECT patent_id, MAX(titles) AS titles, MAX(title_localized) AS title_localized,
         MAX(title_zh) AS title_zh
  FROM dwd_patent_title
  GROUP BY patent_id
) t ON t.patent_id = p.patent_id
LEFT JOIN (
  SELECT patent_id, MAX(abstract_zh) AS abstract_zh
  FROM dwd_patent_abstract
  GROUP BY patent_id
) a ON a.patent_id = p.patent_id
LEFT JOIN (
  SELECT patent_id, MAX(dates_of_public_availability) AS dates_of_public_availability,
         MAX(status) AS status, MAX(anticipated_expiration) AS anticipated_expiration
  FROM dwd_patent_legal
  GROUP BY patent_id
) l ON l.patent_id = p.patent_id
LEFT JOIN (
  SELECT patent_id, MAX(reference_cited) AS reference_cited,
         MAX(cited_by_nums) AS cited_by_nums
  FROM dwd_patent_cited
  GROUP BY patent_id
) c ON c.patent_id = p.patent_id
LEFT JOIN (
  SELECT patent_id, MAX(simple_family_number) AS simple_family_number
  FROM dwd_patent_family
  GROUP BY patent_id
) f ON f.patent_id = p.patent_id
WHERE p.id REGEXP '^[0-9]+$' AND CAST(p.id AS UNSIGNED) > :cursor
ORDER BY CAST(p.id AS UNSIGNED)
LIMIT :limit
"""


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = [("dwd_patent", PATENT_SQL, patent_record)]
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
            cursor_column="source_row_id",
        )
    )


if __name__ == "__main__":
    main()
