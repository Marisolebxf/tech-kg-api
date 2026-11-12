"""Direct-relation time evidence, preserving the precision stored in the graph."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any


def parse_time(value: Any, *, source: str, paper_id: str = "") -> dict[str, str] | None:
    if isinstance(value, (date, datetime)):
        text = value.strftime("%Y-%m-%d")
    elif isinstance(value, (str, int)) and not isinstance(value, bool):
        text = str(value).strip()
    else:
        return None
    match = re.fullmatch(
        r"((?:19|20)\d{2})(?:[-/.年](\d{1,2})(?:[-/.月](\d{1,2})日?)?)?"
        r"(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        text,
    )
    if not match:
        return None
    year, month, day = (int(part) if part else None for part in match.groups())
    try:
        if month is None:
            lower, upper, display, precision = (
                f"{year}-01-01",
                f"{year}-12-31",
                str(year),
                "year",
            )
        elif day is None:
            last = calendar.monthrange(year, month)[1]
            lower, upper = f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"
            display, precision = f"{year}-{month:02d}", "month"
        else:
            display = date(year, month, day).isoformat()
            lower = upper = display
            precision = "day"
    except (ValueError, TypeError, calendar.IllegalMonthError):
        return None
    return dict(
        lower=lower,
        upper=upper,
        display=display,
        precision=precision,
        source=source,
        paper_id=paper_id,
    )


def paper_time(paper: dict[str, Any]) -> dict[str, str] | None:
    props = paper.get("properties") or {}
    for field in ("publish_date", "publication_date", "publication_year", "year"):
        evidence = parse_time(
            props.get(field),
            source=f"shared_paper.{field}",
            paper_id=str(paper.get("id") or ""),
        )
        if evidence is not None:
            return evidence
    return None


def select_time(
    evidence: list[dict[str, str]], start: str | None = None, end: str | None = None
) -> dict[str, str] | None:
    lower = parse_time(start, source="request") if start else None
    upper = parse_time(end, source="request") if end else None
    if (start and lower is None) or (end and upper is None):
        return None
    # A year/month is accepted only when its entire possible interval fits the
    # requested range; never manufacture a month/day to make it pass a boundary.
    matches = [
        item
        for item in evidence
        if (lower is None or item["lower"] >= lower["lower"])
        and (upper is None or item["upper"] <= upper["upper"])
    ]
    return (
        max(matches, key=lambda item: (item["upper"], item["lower"]))
        if matches
        else None
    )


def apply_time(row: dict[str, Any], evidence: dict[str, str] | None) -> None:
    row["relation_time"] = evidence["display"] if evidence else None
    row["relation_time_source"] = evidence["source"] if evidence else None
    row["relation_time_precision"] = evidence["precision"] if evidence else None
    row["relation_time_paper_ids"] = (
        [evidence["paper_id"]] if evidence and evidence["paper_id"] else []
    )
