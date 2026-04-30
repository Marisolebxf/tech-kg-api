"""Fluent Cypher query builder.

Provides a Pythonic way to construct Cypher queries without string
concatenation, reducing the risk of injection and improving readability.

Example::

    query = (
        QueryBuilder()
        .match("n", labels=["Person"])
        .where("n.age > $min_age")
        .with_("n")
        .match("n", var="n", rel_type="KNOWS", target="m")
        .return_("n.name", "m.name")
        .order_by("n.name")
        .limit(10)
        .build()
    )
    # MATCH (n:Person) WHERE n.age > $min_age
    # WITH n
    # MATCH (n)-[:KNOWS]->(m)
    # RETURN n.name, m.name
    # ORDER BY n.name
    # LIMIT 10
"""

from __future__ import annotations

from typing import Any


class QueryBuilder:
    """Builder for Cypher queries using a fluent API.

    Each method returns ``self`` so calls can be chained.
    """

    def __init__(self) -> None:
        self._clauses: list[str] = []
        self._params: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # MATCH
    # ------------------------------------------------------------------

    def match(
        self,
        var: str,
        *,
        labels: list[str] | None = None,
        rel_type: str | None = None,
        target: str | None = None,
        direction: str = "right",
    ) -> QueryBuilder:
        """Add a MATCH clause.

        Args:
            var: Variable name for the node.
            labels: Optional labels for the node.
            rel_type: If given, match a relationship pattern instead.
            target: Target variable for the relationship.
            direction: "right" (->), "left" (<-), or "both" (—).

        Examples::

            .match("n", labels=["Person"])                    # MATCH (n:Person)
            .match("n", rel_type="KNOWS", target="m")        # MATCH (n)-[:KNOWS]->(m)
            .match("n", rel_type="KNOWS", target="m",
                   direction="left")                          # MATCH (n)<-[:KNOWS]-(m)
        """
        label_str = ":" + ":".join(labels) if labels else ""
        node_pattern = f"({var}{label_str})"

        if rel_type and target:
            if direction == "right":
                pattern = f"{node_pattern}-[:{rel_type}]->({target})"
            elif direction == "left":
                pattern = f"{node_pattern}<-[:{rel_type}]-({target})"
            else:
                pattern = f"{node_pattern}-[:{rel_type}]-({target})"
        else:
            pattern = node_pattern

        self._clauses.append(f"MATCH {pattern}")
        return self

    def optional_match(
        self,
        var: str,
        *,
        labels: list[str] | None = None,
        rel_type: str | None = None,
        target: str | None = None,
        direction: str = "right",
    ) -> QueryBuilder:
        """Add an OPTIONAL MATCH clause (same args as ``match``)."""
        label_str = ":" + ":".join(labels) if labels else ""
        node_pattern = f"({var}{label_str})"

        if rel_type and target:
            if direction == "right":
                pattern = f"{node_pattern}-[:{rel_type}]->({target})"
            elif direction == "left":
                pattern = f"{node_pattern}<-[:{rel_type}]-({target})"
            else:
                pattern = f"{node_pattern}-[:{rel_type}]-({target})"
        else:
            pattern = node_pattern

        self._clauses.append(f"OPTIONAL MATCH {pattern}")
        return self

    # ------------------------------------------------------------------
    # WHERE
    # ------------------------------------------------------------------

    def where(self, condition: str) -> QueryBuilder:
        """Add a WHERE clause.

        Use ``$param`` placeholders for parameterized values.
        """
        self._clauses.append(f"WHERE {condition}")
        return self

    def and_where(self, condition: str) -> QueryBuilder:
        """Append an AND condition."""
        self._clauses.append(f"AND {condition}")
        return self

    def or_where(self, condition: str) -> QueryBuilder:
        """Append an OR condition."""
        self._clauses.append(f"OR {condition}")
        return self

    # ------------------------------------------------------------------
    # WITH
    # ------------------------------------------------------------------

    def with_(self, *items: str) -> QueryBuilder:
        """Add a WITH clause.

        Args:
            items: Variable names or expressions to carry forward.
        """
        self._clauses.append(f"WITH {', '.join(items)}")
        return self

    # ------------------------------------------------------------------
    # RETURN
    # ------------------------------------------------------------------

    def return_(self, *items: str, distinct: bool = False) -> QueryBuilder:
        """Add a RETURN clause.

        Args:
            items: Expressions to return.
            distinct: Wrap with RETURN DISTINCT.
        """
        keyword = "RETURN DISTINCT" if distinct else "RETURN"
        self._clauses.append(f"{keyword} {', '.join(items)}")
        return self

    # ------------------------------------------------------------------
    # ORDER BY / SKIP / LIMIT
    # ------------------------------------------------------------------

    def order_by(self, *fields: str) -> QueryBuilder:
        self._clauses.append(f"ORDER BY {', '.join(fields)}")
        return self

    def skip(self, n: int) -> QueryBuilder:
        self._clauses.append(f"SKIP {n}")
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._clauses.append(f"LIMIT {n}")
        return self

    # ------------------------------------------------------------------
    # CREATE / MERGE / SET / DELETE
    # ------------------------------------------------------------------

    def create(self, pattern: str) -> QueryBuilder:
        """Add a CREATE clause with a raw pattern string."""
        self._clauses.append(f"CREATE {pattern}")
        return self

    def merge(self, pattern: str) -> QueryBuilder:
        """Add a MERGE clause with a raw pattern string."""
        self._clauses.append(f"MERGE {pattern}")
        return self

    def set(self, *assignments: str) -> QueryBuilder:
        """Add a SET clause."""
        self._clauses.append(f"SET {', '.join(assignments)}")
        return self

    def on_create_set(self, *assignments: str) -> QueryBuilder:
        """Add ON CREATE SET clause (must follow a MERGE)."""
        self._clauses.append(f"ON CREATE SET {', '.join(assignments)}")
        return self

    def on_match_set(self, *assignments: str) -> QueryBuilder:
        """Add ON MATCH SET clause (must follow a MERGE)."""
        self._clauses.append(f"ON MATCH SET {', '.join(assignments)}")
        return self

    def delete(self, *vars: str, detach: bool = False) -> QueryBuilder:
        """Add a DELETE (or DETACH DELETE) clause."""
        keyword = "DETACH DELETE" if detach else "DELETE"
        self._clauses.append(f"{keyword} {', '.join(vars)}")
        return self

    # ------------------------------------------------------------------
    # UNWIND
    # ------------------------------------------------------------------

    def unwind(self, list_expr: str, var: str) -> QueryBuilder:
        """Add an UNWIND clause."""
        self._clauses.append(f"UNWIND {list_expr} AS {var}")
        return self

    # ------------------------------------------------------------------
    # WITH / CALL (subqueries)
    # ------------------------------------------------------------------

    def call(self, subquery: str) -> QueryBuilder:
        """Add a CALL subquery clause."""
        self._clauses.append(f"CALL {{ {subquery} }}")
        return self

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def params(self, **kwargs: Any) -> QueryBuilder:
        """Bind query parameters.

        Merges into the existing parameter map; later values win.
        """
        self._params.update(kwargs)
        return self

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> str:
        """Build and return the Cypher query string."""
        return "\n".join(self._clauses)

    def build_with_params(self) -> tuple[str, dict[str, Any]]:
        """Build the query and return (cypher, params) tuple."""
        return self.build(), dict(self._params)

    def reset(self) -> QueryBuilder:
        """Clear all clauses and parameters."""
        self._clauses.clear()
        self._params.clear()
        return self

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return self.build()

    def __repr__(self) -> str:
        return f"QueryBuilder(clauses={len(self._clauses)}, params={list(self._params.keys())})"
