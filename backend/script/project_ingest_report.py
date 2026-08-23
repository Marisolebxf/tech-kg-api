"""Runtime reporting for Project graph ETL."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class ProjectIngestReport:
    FILES = {
        "organization_not_found": "unmatched_organizations.jsonl",
        "organization_ambiguous": "ambiguous_organizations.jsonl",
        "person_not_found": "unmatched_persons.jsonl",
        "person_ambiguous": "ambiguous_persons.jsonl",
        "output_not_found": "unmatched_outputs.jsonl",
        "output_ambiguous": "ambiguous_outputs.jsonl",
        "cross_domain": "cross_domain_candidates.jsonl",
    }

    def __init__(self, report_dir: Path, *, ingest_batch: str, dry_run: bool) -> None:
        self.report_dir = report_dir
        self.ingest_batch = ingest_batch
        self.dry_run = dry_run
        self.stats: Counter[str] = Counter()
        self.records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def increment(self, key: str, amount: int = 1) -> None:
        self.stats[key] += amount

    def add(self, category: str, record: dict[str, Any]) -> None:
        self.records[category].append(record)
        self.stats[category] += 1

    def write(self) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        for category, filename in self.FILES.items():
            path = self.report_dir / filename
            with path.open("w", encoding="utf-8") as handle:
                for record in self.records.get(category, []):
                    handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        summary = {
            "ingest_batch": self.ingest_batch,
            "dry_run": self.dry_run,
            "stats": dict(sorted(self.stats.items())),
        }
        (self.report_dir / "etl_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary
