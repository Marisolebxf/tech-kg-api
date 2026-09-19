/**
 * 图谱查询可视化页的纯转换工具。
 *
 * 从老版 PlatformWorkbenchView「图谱查询」页签（commit 19baca5 之前的实现）抽取，
 * 按当前动态 Schema 栈改造：
 * - 节点类型不再走固定英文标签映射（mapApiNodeType），由调用方通过
 *   `toneForLabel` 注入「动态标签 → 画布色调」的分配（见 assignLabelTones）；
 * - 边的 category 直接使用边类型原文（动态中文类型）；
 * - 去掉老页的分扇区静态布局，力导向布局会自行收敛，这里只按 id 哈希
 *   播一个确定性初始位置（首节点中心钉扎由画布/布局负责）。
 */

import type { GraphData, GraphEdge, GraphNode } from '../api/graphSearch'
import type { GraphEdgeData, GraphNodeData, GraphNodeType } from '../data/graph-presets'

/** 画布可用的 10 个节点色调（不含 'main'，与 graph-presets 演示主节点重复）。 */
export const LABEL_TONES: readonly GraphNodeType[] = [
  'expert', 'org', 'company', 'paper', 'topic', 'project', 'event', 'chain', 'field', 'source',
]

/** FNV-1a 字符串哈希（与 use-force-layout 同实现，返回 uint32）。 */
function hashStr(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.codePointAt(i) ?? 0
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h >>> 0
}

/**
 * 为本次结果里出现的实体标签分配画布色调。
 *
 * 按 FNV-1a 哈希排序后贪心取空闲色调：≤10 个标签时无撞色（图例不会
 * 出现两行同色）、跨查询/刷新稳定（不依赖出现顺序）、无状态（切换
 * 图空间无需重置）。>10 个标签时轮转共享色调。
 */
export function assignLabelTones(labels: readonly string[]): Map<string, GraphNodeType> {
  const unique = [...new Set(labels)]
  const sorted = [...unique].sort((a, b) => hashStr(a) - hashStr(b) || (a < b ? -1 : 1))
  const assignment = new Map<string, GraphNodeType>()
  for (const label of sorted) {
    const start = hashStr(label) % LABEL_TONES.length
    let tone = LABEL_TONES[start]
    const used = new Set(assignment.values())
    for (let i = 0; i < LABEL_TONES.length && used.has(tone); i++) {
      tone = LABEL_TONES[(start + i + 1) % LABEL_TONES.length]
    }
    assignment.set(label, tone)
  }
  return assignment
}

/** 从节点/边属性中读取字符串型溯源字段（空值视为缺失）。 */
export function readStringProperty(
  properties: Record<string, unknown>,
  field: string,
): string | undefined {
  const value = properties[field]
  if (value === null || value === undefined || value === '') {
    return undefined
  }
  return String(value)
}

/** 从属性中读取已有置信度（只读，不重算；非 0～1 数值忽略）。 */
export function readConfidence(
  properties: Record<string, unknown>,
  fields: readonly string[] = ['confidence'],
): number | undefined {
  for (const field of fields) {
    const raw = properties[field]
    if (raw === null || raw === undefined || raw === '') continue
    const value = Number(raw)
    if (Number.isFinite(value) && value >= 0 && value <= 1) return value
  }
  return undefined
}

/** 节点显示名：按属性优先级取（人员/机构 → 论文/专利 → 产业链 → 业务 ID → 节点 ID）。 */
export function getApiNodeDisplayName(node: GraphNode): string {
  const properties = node.properties
  return String(
    properties.name_cn
      ?? properties.name_zh
      ?? properties.name
      ?? properties.title_zh
      ?? properties.title_cn
      ?? properties.title_original
      ?? properties.title
      ?? properties.chain_name
      ?? properties.node_name
      ?? properties.keyword
      ?? properties.name_en
      ?? properties.name_abbr
      ?? properties.project_number
      ?? properties.patent_id
      ?? properties.family_number
      ?? properties.org_id
      ?? node.id,
  )
}

function formatPropertyValue(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/** 属性摘要（最多 6 条），无属性时退化为节点 ID。 */
export function buildApiNodeEvidence(node: GraphNode): string[] {
  const result = Object.entries(node.properties)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 6)
    .map(([key, value]) => `${key}: ${formatPropertyValue(value)}`)
  return result.length > 0 ? result : [`节点 ID: ${node.id}`]
}

/** 节点度数（关联边数）。 */
export function countApiNodeRelations(nodeId: string, edges: GraphEdge[]): number {
  return edges.filter((edge) => edge.source === nodeId || edge.target === nodeId).length
}

/**
 * 清理后端返回的子图：丢掉端点缺失的边，再从中心节点无向 BFS，
 * 只保留可达节点与其间的边（去掉截断产生的孤儿节点）。
 */
export function normalizeReturnedSubgraph(data: GraphData, centerNodeId: string): GraphData {
  const nodeById = new Map(data.nodes.map((node) => [node.id, node]))
  const validEdges = data.edges.filter(
    (edge) => nodeById.has(edge.source) && nodeById.has(edge.target),
  )

  const adjacency = new Map<string, string[]>()
  for (const edge of validEdges) {
    for (const [from, to] of [[edge.source, edge.target], [edge.target, edge.source]] as const) {
      const neighbours = adjacency.get(from) ?? []
      neighbours.push(to)
      adjacency.set(from, neighbours)
    }
  }

  const reachable = new Set<string>([centerNodeId])
  const queue = [centerNodeId]
  while (queue.length > 0) {
    for (const next of adjacency.get(queue.shift()!) ?? []) {
      if (!reachable.has(next)) {
        reachable.add(next)
        queue.push(next)
      }
    }
  }

  const nodes = data.nodes.filter((node) => reachable.has(node.id))
  const retained = new Set(nodes.map((node) => node.id))
  return {
    nodes,
    edges: validEdges.filter((edge) => retained.has(edge.source) && retained.has(edge.target)),
  }
}

/** 按 id 去重节点。 */
export function deduplicateGraphNodes(nodes: GraphNode[]): GraphNode[] {
  return Array.from(new Map(nodes.map((node) => [node.id, node])).values())
}

/** 按 id 去重边。 */
export function deduplicateGraphEdges(edges: GraphEdge[]): GraphEdge[] {
  return Array.from(new Map(edges.map((edge) => [edge.id, edge])).values())
}

/**
 * 合并多次子图查询结果（slash-VID 回退逐边类型查询时使用）。
 * 以第一份结果为主，节点/边按 id 去重。
 */
export function mergeGraphData(parts: GraphData[]): GraphData {
  return {
    nodes: deduplicateGraphNodes(parts.flatMap((part) => part.nodes)),
    edges: deduplicateGraphEdges(parts.flatMap((part) => part.edges)),
  }
}

/** 按 id 哈希在画布中心圆环上撒一个确定性初始位置（力导向会自行收敛）。 */
function seedPosition(id: string, index: number): { x: number; y: number } {
  const angle = ((hashStr(id) % 3600) / 3600) * Math.PI * 2 + index * 0.001
  const radius = 120 + (hashStr(`${id}#r`) % 160)
  return { x: 480 + Math.cos(angle) * radius, y: 270 + Math.sin(angle) * radius }
}

/**
 * 后端 GraphData → 画布 GraphNodeData。
 * toneForLabel 由调用方传入（通常来自 assignLabelTones 的当前分配）。
 */
export function convertApiGraphNodes(
  data: GraphData,
  centerNodeId: string,
  toneForLabel: (label: string) => GraphNodeType,
): GraphNodeData[] {
  const sorted = [...data.nodes].sort((left, right) => {
    if (left.id === centerNodeId) return -1
    if (right.id === centerNodeId) return 1
    return 0
  })

  return sorted.map((node, index) => {
    const isCenter = node.id === centerNodeId
    const label = node.labels[0] ?? ''
    const position = seedPosition(node.id, index)
    return {
      id: node.id,
      label: getApiNodeDisplayName(node),
      nodeType: toneForLabel(label),
      x: position.x,
      y: position.y,
      radius: isCenter ? 16 : 12,
      entityType: label || '未知类型',
      confidence: readConfidence(node.properties),
      sourceTable: readStringProperty(node.properties, 'source_table'),
      sourceRecordId: readStringProperty(node.properties, 'source_record_id'),
      sourceSystem: readStringProperty(node.properties, 'source_system'),
      ingestBatch: readStringProperty(node.properties, 'ingest_batch'),
      ingestTime: readStringProperty(node.properties, 'ingest_time'),
      relations: `${countApiNodeRelations(node.id, data.edges)} 条关联关系`,
      evidence: buildApiNodeEvidence(node),
      level: isCenter ? 0 : 1,
    }
  })
}

/** 后端边 → 画布 GraphEdgeData（category 直接用边类型原文，配合动态类型图例）。 */
export function convertApiGraphEdges(edges: GraphEdge[]): GraphEdgeData[] {
  return edges.map((edge) => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
    label: edge.type,
    category: edge.type,
    confidence: readConfidence(edge.properties),
    sourceTable: readStringProperty(edge.properties, 'source_table'),
    sourceRecordId: readStringProperty(edge.properties, 'source_record_id'),
    ingestBatch: readStringProperty(edge.properties, 'ingest_batch'),
    ingestTime: readStringProperty(edge.properties, 'ingest_time'),
    matchEvidence: readStringProperty(edge.properties, 'match_evidence'),
    matchMethod: readStringProperty(edge.properties, 'match_method'),
  }))
}

/** 节点主标签（画布数据上 entityType 即转换时的 labels[0]）。 */
export function primaryLabelOfNode(node: GraphNodeData): string {
  return node.entityType
}

/**
 * 节点数上限保护：中心节点永远保留，其余按度数降序（同度按 id 稳定排序）
 * 取前 cap 个，最后裁掉因此悬空的边。
 */
export function applyNodeCap(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  cap: number,
  centerNodeId: string,
): { nodes: GraphNodeData[]; edges: GraphEdgeData[]; hiddenCount: number } {
  if (nodes.length <= cap) {
    return { nodes, edges, hiddenCount: 0 }
  }

  const degrees = new Map<string, number>()
  for (const edge of edges) {
    degrees.set(edge.from, (degrees.get(edge.from) ?? 0) + 1)
    degrees.set(edge.to, (degrees.get(edge.to) ?? 0) + 1)
  }

  const center = nodes.filter((node) => node.id === centerNodeId)
  const others = nodes
    .filter((node) => node.id !== centerNodeId)
    .sort(
      (a, b) =>
        (degrees.get(b.id) ?? 0) - (degrees.get(a.id) ?? 0) || (a.id < b.id ? -1 : 1),
    )

  const kept = [...center, ...others.slice(0, Math.max(0, cap - center.length))]
  const keptIds = new Set(kept.map((node) => node.id))
  return {
    nodes: kept,
    edges: edges.filter((edge) => keptIds.has(edge.from) && keptIds.has(edge.to)),
    hiddenCount: nodes.length - kept.length,
  }
}
