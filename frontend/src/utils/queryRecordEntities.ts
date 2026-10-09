import type { GraphNode } from '../api/graphSearch'

export interface QueryEntityReference {
  vid: string
  embeddedNode?: GraphNode
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function vertexId(value: unknown): string | undefined {
  if (typeof value !== 'string' && typeof value !== 'number') return undefined
  const id = String(value).trim()
  if (!id) return undefined
  if (id.startsWith('"') && id.endsWith('"')) {
    try {
      const decoded: unknown = JSON.parse(id)
      if (typeof decoded === 'string' && decoded) return decoded
    } catch { /* Retain the original VID when it is not JSON-quoted. */ }
  }
  return id
}

/** Only explicit graph identifiers are candidates; names, schema fields and business IDs are not guessed. */
const ID_COLUMN = /^(?:vid|_id|id|node_?id|vertex_?id|src|dst|source|target|source_?id|target_?id|_src|_dst)$/i
const ID_EXPRESSION = /^(?:id|src|dst)\s*\(.+\)$/i
const EDGE_ENDPOINTS = ['source', 'target', 'sourceId', 'targetId', 'source_id', 'target_id', 'src', 'dst']

export function collectQueryEntityReferences(row: Record<string, unknown>): QueryEntityReference[] {
  const references = new Map<string, QueryEntityReference>()
  const add = (value: unknown, embeddedNode?: GraphNode) => {
    const vid = vertexId(value)
    if (vid && (!references.has(vid) || embeddedNode)) references.set(vid, { vid, embeddedNode })
  }
  function visit(value: unknown, depth = 0): void {
    if (depth > 8) return
    if (typeof value === 'string' && /^[\[{]/.test(value.trim())) {
      try { visit(JSON.parse(value), depth + 1) } catch { /* Ordinary text stays a query field. */ }
      return
    }
    if (Array.isArray(value)) {
      value.forEach((entry) => visit(entry, depth + 1))
      return
    }
    if (!isObject(value)) return
    const isEdge = typeof value.type === 'string' && (
      (value.source !== undefined && value.target !== undefined)
      || (value.sourceId !== undefined && value.targetId !== undefined)
      || (value.source_id !== undefined && value.target_id !== undefined)
      || (value.src !== undefined && value.dst !== undefined)
    )
    if (isEdge) EDGE_ENDPOINTS.forEach((key) => add(value[key]))
    // TRS vertex JSON: { id, labels, properties }; do not treat an edge's id as a vertex.
    if (!isEdge && Array.isArray(value.labels) && isObject(value.properties)) {
      const vid = vertexId(value.id)
      if (vid) add(vid, {
        id: vid,
        labels: value.labels.filter((label): label is string => typeof label === 'string'),
        properties: value.properties,
      })
    }
    for (const [key, child] of Object.entries(value)) {
      if (key !== 'properties') visit(child, depth + 1)
    }
  }
  for (const [column, value] of Object.entries(row)) {
    const key = column.replace(/`/g, '').trim()
    if (ID_COLUMN.test(key) || ID_EXPRESSION.test(key) || /\.(?:vid|_id|id)$/i.test(key)) add(value)
    visit(value)
  }
  return [...references.values()]
}

/** Mirrors actual name/title fields used by entity search, with Chinese names first. */
const NAME_FIELDS = [
  'name_zh', 'name_cn', 'name', 'title_zh', 'title_cn', 'title_original', 'title',
  'project_name', 'paper_title', 'patent_name', 'patent_title', 'product_name',
  'chain_name', 'node_name', 'keyword', 'cn_name', 'display_name', 'org_name',
  'name_en', 'title_en', 'name_abbr', 'label',
]

export function queryEntityName(node: GraphNode): string | undefined {
  for (const field of NAME_FIELDS) {
    // Some projections retain the tag-qualified property key.
    const entries = Object.entries(node.properties).filter(([key]) => key === field || key.endsWith(`.${field}`))
    for (const [, value] of entries) {
      if ((typeof value === 'string' || typeof value === 'number') && String(value).trim()) return String(value)
    }
  }
  return undefined
}
