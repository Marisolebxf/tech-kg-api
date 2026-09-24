"""SDK-only extraction example; match the output properties to your Schema."""

from kg_sdk import current_context, step


@step(id="normalize")
def normalize(payload):
    ctx = current_context()
    entities = []
    for row in payload.get("rows", []):
        if row.get("id") is None:
            continue
        entities.append(
            {
                "id": str(row["id"]),
                "props": {"name": str(row.get("name") or "").strip()},
            }
        )
    # Return records for the platform to write into this task's authorized space.
    # No connection credentials, backend imports or network calls are needed.
    return {
        "entities": entities,
        "stats": {
            "records": len(entities),
            "step": ctx.step_id if ctx else "normalize",
        },
    }
