import json
import sqlite3

from service.workflow_repository import WorkflowRepository


def test_legacy_unique_workflow_type_is_migrated(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE workflow_definitions (
                   id TEXT PRIMARY KEY,
                   workflow_type TEXT NOT NULL UNIQUE,
                   category TEXT NOT NULL,
                   active INTEGER NOT NULL,
                   payload TEXT NOT NULL
               )"""
        )
        definition = {
            "id": "legacy-custom",
            "name": "Legacy",
            "workflowType": "kg.custom.configurable",
            "category": "custom",
            "active": True,
        }
        connection.execute(
            "INSERT INTO workflow_definitions VALUES (?, ?, ?, ?, ?)",
            (
                definition["id"],
                definition["workflowType"],
                definition["category"],
                1,
                json.dumps(definition),
            ),
        )

    repository = WorkflowRepository(str(database))
    repository.create_definition(
        {
            "id": "second-custom",
            "name": "Second",
            "workflowType": "kg.custom.configurable",
            "category": "custom",
            "active": True,
        }
    )

    assert repository.get_definition("legacy-custom")["name"] == "Legacy"
    assert repository.get_definition("second-custom")["name"] == "Second"
