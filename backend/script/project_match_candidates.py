"""Collect the exact graph lookup candidates needed by one Project ETL run."""

from __future__ import annotations

from typing import Any

from dao.project import ProjectDAO
from script.project_entity_matcher import normalize_doi, normalize_patent_number
from script.project_graph_utils import parse_json_objects, parse_list


def collect_match_candidates(
    dao: ProjectDAO,
    projects: list[tuple[Any, str, str]],
    *,
    id_prefix: str | None,
) -> dict[str, set[str]]:
    result = {
        "organization": set(),
        "person": set(),
        "paper_doi": set(),
        "paper_title": set(),
        "patent_number": set(),
        "patent_title": set(),
        "report_title": set(),
    }
    allowed_ids = {str(row.id) for row, _source, _table in projects}
    for row, _source, _table in projects:
        _add(result["organization"], row.funded_institution)
        _add(result["person"], row.project_host)
        result["person"].update(
            value.strip() for value in parse_list(row.participants) if value.strip()
        )

    for list_fn in (dao.list_zh_output, dao.list_en_output):
        offset = 0
        while True:
            rows = list_fn(offset=offset, limit=200, id_prefix=id_prefix)
            if not rows:
                break
            for row in rows:
                if str(row.id) not in allowed_ids:
                    continue
                for field in (
                    "output_journal_articles",
                    "output_conference_papers",
                    "output_degree_papers",
                ):
                    for item in parse_json_objects(getattr(row, field, None)):
                        _add(result["paper_doi"], item.get("doi"))
                        _add(result["paper_doi"], normalize_doi(item.get("doi")))
                        _add(result["paper_title"], item.get("title"))
                for item in parse_json_objects(getattr(row, "output_patents", None)):
                    number = (
                        item.get("patent_number")
                        or item.get("application_number")
                        or item.get("publication_number")
                        or item.get("patent_id")
                    )
                    _add(result["patent_number"], number)
                    _add(result["patent_number"], normalize_patent_number(number))
                    _add(
                        result["patent_title"],
                        item.get("patent_title") or item.get("title"),
                    )
                for item in parse_json_objects(getattr(row, "output_reports", None)):
                    _add(result["report_title"], item.get("title"))
            offset += len(rows)
            if len(rows) < 200:
                break
    return result


def _add(target: set[str], value: Any) -> None:
    cleaned = str(value or "").strip()
    if cleaned:
        target.add(cleaned)
