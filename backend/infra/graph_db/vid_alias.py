"""Read adapter for graphs whose attributes and edges use different VIDs."""
from __future__ import annotations

import operator
import re

from infra.graph_db.client import TRSGraphClient, _ngql_quote
from infra.graph_db.exceptions import GraphRequestError
from infra.graph_db.models import GraphEdge, GraphNode, GraphPath

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


PREFIXES = {
    "Person": "person_", "Organization": "org_", "Paper": "paper_",
    "Patent": "patent_", "Project": "project_", "Keyword": "keyword_",
    "IndustryChain": "chain_", "IndustryNode": "node_", "Event": "event_",
    "News": "news_", "Product": "product_", "Journal": "journal_",
    "PatentFamily": "patent_family_", "Activity": "activity_", "Report": "report_",
}


def make_graph_client(settings):
    return VidAliasGraphClient(settings, PREFIXES)


class VidAliasGraphClient(TRSGraphClient):
    """Keep prefixed logical IDs; hydrate from typed raw vertices, without writes."""
    vid_alias_enabled = True
    PATH_BUDGET = 20000

    def __init__(self, settings, prefixes):
        super().__init__(settings)
        self.prefixes = dict(prefixes)

    def split_alias(self, vid):
        text = str(vid)
        for label, prefix in sorted(self.prefixes.items(), key=lambda item: -len(item[1])):
            if text.startswith(prefix) and len(text) > len(prefix):
                return label, text[len(prefix):]
        return None, text

    def _identity(self, node):
        label, raw = self.split_alias(node.id)
        if label and label in node.labels:
            return label, raw, str(node.id)
        matches = [tag for tag in node.labels if tag in self.prefixes]
        if len(matches) > 1:
            raise GraphRequestError("VID 对应多个实体类型，请使用带前缀的 VID", status_code=409)
        if matches:
            label = matches[0]
            return label, str(node.id), self.prefixes[label] + str(node.id)
        return None, str(node.id), str(node.id)

    def get_nodes_bulk(self, node_ids):
        requested = list(dict.fromkeys(str(v) for v in node_ids if v is not None))
        candidates = list(requested)
        for vid in requested:
            label, raw = self.split_alias(vid)
            if label:
                candidates.append(raw)
        found = super().get_nodes_bulk(candidates)
        extra = []
        for key, node in found.items():
            if key not in requested or self.split_alias(key)[0]:
                continue
            _, raw, canonical = self._identity(node)
            extra.extend([raw, canonical])
        missing = list(dict.fromkeys(v for v in extra if v not in found))
        if missing:
            found.update(super().get_nodes_bulk(missing))
        resolved = {}
        for vid in requested:
            label, raw = self.split_alias(vid)
            original = found.get(vid)
            if not label:
                if original is None:
                    continue
                label, raw, canonical = self._identity(original)
            else:
                canonical = self.prefixes[label] + raw
            raw_node = found.get(raw)
            prefixed = found.get(canonical)
            # A bare VID may carry another type: never borrow its properties.
            valid = [n for n in [prefixed, raw_node] if n and (not label or label in n.labels)]
            if not valid:
                continue
            # Keep ordinary raw-only graphs on their original IDs. Only collapse
            # onto a prefixed vertex when that typed counterpart actually exists.
            canonical = canonical if prefixed and (not label or label in prefixed.labels) else raw
            props = {}
            for node in valid:  # typed raw nonempty values win; retain 0 and False
                for key, value in node.properties.items():
                    if value is not None and value != "":
                        props[key] = value
                    elif key not in props:
                        props[key] = value
            labels = [label] if label else valid[0].labels
            node = GraphNode(id=canonical, labels=labels, properties=props)
            resolved[vid] = node
            resolved[canonical] = node
        return resolved

    def attribute_vid(self, node_id, label):
        known, raw = self.split_alias(node_id)
        if known and known != label:
            raise GraphRequestError("VID 前缀与实体类型不一致", status_code=409)
        candidate = super().get_nodes_bulk([raw]).get(raw)
        if candidate and label in candidate.labels and any(
                value is not None and value != "" for value in candidate.properties.values()):
            return raw
        return str(node_id)

    def get_node(self, node_id):
        return self.get_nodes_bulk([node_id]).get(str(node_id))

    def _hydrate(self, nodes):
        found = self.get_nodes_bulk([n.id for n in nodes])
        unique = {}
        for node in nodes:
            hydrated = found.get(str(node.id), node)
            unique[str(hydrated.id)] = hydrated
        return list(unique.values())

    def get_nodes_by_label(self, label, *, limit=100, offset=0):
        page = super().get_nodes_by_label(label, limit=limit, offset=offset)
        page.items = self._hydrate(page.items)
        return page

    def paged_nodes_by_label(self, label, *, limit=100, offset=0):
        return self._hydrate(super().paged_nodes_by_label(label, limit=limit, offset=offset))

    def find_nodes(self, labels, properties, *, limit=100, offset=0):
        page = super().find_nodes(labels, properties, limit=limit, offset=offset)
        page.items = self._hydrate(page.items)
        return page

    def keyword_nodes_by_label(self, label, keyword, *, limit=100, offset=0, count_only=False):
        page = super().keyword_nodes_by_label(
            label, keyword, limit=limit, offset=offset, count_only=count_only)
        if not count_only:
            page.items = self._hydrate(page.items)
        return page

    def _aliases(self, node_id):
        node = self.get_node(node_id)
        if node:
            _, raw, canonical = self._identity(node)
            return list(dict.fromkeys([canonical, raw]))
        label, raw = self.split_alias(node_id)
        return list(dict.fromkeys([str(node_id), raw])) if label else [str(node_id)]

    def get_node_edges(self, node_id, *, direction="both", edge_type=None, limit=100, offset=0):
        if direction not in {"out", "in", "both"} or limit < 0 or offset < 0:
            raise GraphRequestError("Invalid traversal arguments", status_code=400)
        if edge_type and not _IDENTIFIER.fullmatch(edge_type):
            raise GraphRequestError("Invalid edge type", status_code=400)
        if limit == 0:
            return []
        roots = self._aliases(node_id)
        over = "*" if not edge_type else "`" + edge_type + "`"
        clause = {"out": "", "in": " REVERSELY", "both": " BIDIRECT"}[direction]
        base = ("GO 1 STEP FROM " + ", ".join(_ngql_quote(v) for v in roots)
                + " OVER " + over + clause
                + " YIELD DISTINCT src(edge) AS src, dst(edge) AS dst, type(edge) AS et, "
                  "rank(edge) AS rk, properties(edge) AS props"
                  " | ORDER BY $-.src, $-.dst, $-.et, $-.rk")
        # Physical aliases can duplicate logical edges. Page physical rows until the
        # requested unique logical window is filled; never truncate before dedup.
        unique = {}
        cursor = 0
        batch = min(max(limit, 100), 1000)
        while True:
            rows = self.execute_read(base + f" | LIMIT {batch} OFFSET {cursor}").records
            endpoints = self.get_nodes_bulk([v for row in rows for v in [row["src"], row["dst"]]])
            for row in rows:
                src = str(endpoints[row["src"]].id) if row["src"] in endpoints else row["src"]
                dst = str(endpoints[row["dst"]].id) if row["dst"] in endpoints else row["dst"]
                key = (src, dst, row["et"], int(row.get("rk") or 0))
                if key not in unique:
                    unique[key] = GraphEdge(id=f"{src}->{dst}@{key[3]}", type=row["et"],
                                            source_id=src, target_id=dst,
                                            properties=row.get("props") or {})
            if len(rows) < batch or len(unique) >= offset + limit:
                break
            cursor += len(rows)
        return list(unique.values())[offset:offset + limit]

    def get_edges_bulk(self, node_ids, edge_types, *, direction="both", row_cap=10000):
        grouped = {}
        truncated = False
        existing = set(self.edge_types())
        for vid in dict.fromkeys(str(v) for v in node_ids):
            for typ in dict.fromkeys(edge_types):
                if typ not in existing:
                    continue
                rows = self.get_node_edges(vid, direction=direction, edge_type=typ, limit=row_cap)
                grouped[(vid, typ)] = rows
                truncated |= len(rows) >= row_cap
        return grouped, truncated

    def get_neighbours(self, node_id, *, direction="both", edge_type=None, limit=100):
        root = self.get_node(node_id)
        canonical = str(root.id) if root else str(node_id)
        edges = self.get_node_edges(node_id, direction=direction, edge_type=edge_type, limit=limit)
        vids = list(dict.fromkeys(str(e.target_id if str(e.source_id) == canonical
                                    else e.source_id) for e in edges))
        found = self.get_nodes_bulk(vids)
        return [found[v] for v in vids if v in found]

    def shortest_path(self, source_id, target_id, *, edge_type=None, max_depth=10):
        paths = []
        for src in self._aliases(source_id):
            for dst in self._aliases(target_id):
                path = super().shortest_path(src, dst, edge_type=edge_type, max_depth=max_depth)
                if path:
                    paths.append(path)
        if not paths:
            return None
        path = min(paths, key=lambda p: len(p.edges))
        found = self.get_nodes_bulk([n.id for n in path.nodes])
        nodes = [found.get(str(n.id), n) for n in path.nodes]
        edges = []
        for e in path.edges:
            src = found[str(e.source_id)].id if str(e.source_id) in found else e.source_id
            dst = found[str(e.target_id)].id if str(e.target_id) in found else e.target_id
            edges.append(e.model_copy(update={"source_id": src, "target_id": dst}))
        return GraphPath(nodes=nodes, edges=edges)

    @staticmethod
    def _matches(node, filters):
        ops = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
               "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
        for item in filters:
            value = node.properties.get(item.property)
            if value is None:
                return False
            try:
                if not ops[item.operator](value, item.value):
                    return False
            except TypeError:
                return False
        return True

    def typed_paths(self, body):
        # Traverse real edge IDs, then filter hydrated attributes. Filtering ghost
        # vertices in MATCH would incorrectly discard every dated paper.
        source = self.get_node(body.sourceId)
        if source is None:
            return None
        target = self.get_node(body.targetId) if body.targetId else None
        if body.targetId and target is None:
            return {"items": [], "total": 0, "limit": body.limit, "offset": body.offset}
        paths = [([source], [])]
        edge_cache = {}
        reads = 0
        for step in body.steps:
            next_paths = []
            for nodes, edges in paths:
                vid = str(nodes[-1].id)
                key = (vid, step.edgeType, step.direction)
                if key not in edge_cache:
                    rows = self.get_node_edges(vid, direction=step.direction,
                                               edge_type=step.edgeType,
                                               limit=self.PATH_BUDGET + 1)
                    reads += len(rows)
                    if reads > self.PATH_BUDGET:
                        raise GraphRequestError("兼容路径查询超过预算，请缩小条件", status_code=503)
                    edge_cache[key] = rows
                rows = edge_cache[key]
                vids = [str(e.target_id if step.direction == "out" else e.source_id) for e in rows]
                found = self.get_nodes_bulk(vids)
                for edge, neighbor in zip(rows, vids, strict=True):
                    node = found.get(neighbor)
                    if not node or step.targetLabel not in node.labels:
                        continue
                    # MATCH does not reuse an edge in the same path.
                    if any(edge.id == previous.id and edge.type == previous.type for previous in edges):
                        continue
                    if not self._matches(node, step.targetFilters):
                        continue
                    next_paths.append((nodes + [node], edges + [edge]))
                    if len(next_paths) > self.PATH_BUDGET:
                        raise GraphRequestError("兼容路径查询超过预算，请缩小条件", status_code=503)
            paths = next_paths
        if target:
            paths = [p for p in paths if p[0][-1].id == target.id]
        paths.sort(key=lambda p: tuple((str(e.source_id), str(e.target_id), e.type, str(e.id))
                                      for e in p[1]))
        items = [{"nodes": [n.model_dump() for n in nodes],
                  "edges": [{"id": e.id, "type": e.type, "source": e.source_id,
                             "target": e.target_id, "properties": e.properties} for e in edges],
                  "found": True} for nodes, edges in paths[body.offset:body.offset + body.limit]]
        return {"items": items, "total": len(paths) if body.countTotal else -1,
                "limit": body.limit, "offset": body.offset}
