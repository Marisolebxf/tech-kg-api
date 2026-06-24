/** Helpers to draw edges from live node positions (updates when nodes are dragged). */

export interface EdgeNode {
  id?: string
  key?: string
  x: number
  y: number
  width?: number
  height?: number
  kind?: string
}

export interface PixelGraphEdge {
  fromId?: string
  toId?: string
  from_?: number[]
  to?: number[]
  c1?: number[]
  c2?: number[]
  stroke?: string
  className?: string
  [key: string]: unknown
}

const DEFAULT_NODE_WIDTH = 280
const DEFAULT_NODE_HEIGHT = 96

function nodeCenter(node: EdgeNode) {
  const w = node.width ?? DEFAULT_NODE_WIDTH
  const h = node.height ?? DEFAULT_NODE_HEIGHT
  return { x: node.x + w / 2, y: node.y + h / 2, w, h }
}

export function attachEdgeEndpoints(
  edge: PixelGraphEdge,
  fromNode: EdgeNode,
  toNode: EdgeNode,
): void {
  const from = nodeCenter(fromNode)
  const to = nodeCenter(toNode)
  edge.from_ = [from.x, from.y + from.h * 0.2]
  edge.to = [to.x, to.y + to.h * 0.2]
  if (edge.c1 && edge.c2) {
    const dx = to.x - from.x
    const dy = to.y - from.y
    edge.c1 = [from.x + dx * 0.35, from.y + dy * 0.45]
    edge.c2 = [from.x + dx * 0.65, from.y + dy * 0.55]
  }
  if (edge.label_x != null && edge.label_y != null) {
    edge.label_x = (from.x + to.x) / 2
    edge.label_y = (from.y + to.y) / 2 - 18
  }
}

export function inferEdgeNodeIds(nodes: EdgeNode[]): Array<{ fromId: string; toId: string }> {
  const expertA = nodes.find((node) => node.kind === 'expertA')
  const expertB = nodes.find((node) => node.kind === 'expertB')
  const institution = nodes.find((node) => node.kind === 'institution')
  const center = nodes.find((node) => node.kind === 'expert' || node.id === 'expert' || node.key === 'expert')
  const satellites = nodes.filter((node) => node.kind === 'company')

  const pairs: Array<{ fromId: string; toId: string }> = []

  if (expertA && expertB) {
    pairs.push({ fromId: expertA.id ?? expertA.key ?? 'expertA', toId: expertB.id ?? expertB.key ?? 'expertB' })
  }
  if (expertA && institution) {
    pairs.push({ fromId: expertA.id ?? expertA.key ?? 'expertA', toId: institution.id ?? institution.key ?? 'institution' })
  }
  if (expertB && institution) {
    pairs.push({ fromId: expertB.id ?? expertB.key ?? 'expertB', toId: institution.id ?? institution.key ?? 'institution' })
  }
  if (center && satellites.length) {
    for (const satellite of satellites) {
      const fromId = center.id ?? center.key ?? 'center'
      const toId = satellite.id ?? satellite.key ?? ''
      if (toId) {
        pairs.push({ fromId, toId })
      }
    }
  }

  if (pairs.length) {
    return pairs
  }

  if (nodes.length === 2) {
    const first = nodes[0]!
    const second = nodes[1]!
    return [{ fromId: first.id ?? first.key ?? '0', toId: second.id ?? second.key ?? '1' }]
  }

  return []
}

export function refreshGraphEdges(
  nodes: EdgeNode[],
  edges: PixelGraphEdge[],
): PixelGraphEdge[] {
  const nodeMap = new Map(
    nodes.map((node) => [node.id ?? node.key ?? '', node]),
  )
  return edges.map((edge, index) => {
    const next = { ...edge }
    const fromId = edge.fromId ?? inferEdgeNodeIds(nodes)[index]?.fromId
    const toId = edge.toId ?? inferEdgeNodeIds(nodes)[index]?.toId
    if (fromId) next.fromId = fromId
    if (toId) next.toId = toId
    const fromNode = fromId ? nodeMap.get(fromId) : undefined
    const toNode = toId ? nodeMap.get(toId) : undefined
    if (fromNode && toNode) {
      attachEdgeEndpoints(next, fromNode, toNode)
    }
    return next
  })
}

export function edgePathPercent(
  from: EdgeNode,
  to: EdgeNode,
  canvasWidth: number,
  canvasHeight: number,
): string {
  const fx = ((from.x + (from.width ?? DEFAULT_NODE_WIDTH) / 2) / canvasWidth) * 100
  const fy = ((from.y + (from.height ?? DEFAULT_NODE_HEIGHT) / 2) / canvasHeight) * 100
  const tx = ((to.x + (to.width ?? DEFAULT_NODE_WIDTH) / 2) / canvasWidth) * 100
  const ty = ((to.y + (to.height ?? DEFAULT_NODE_HEIGHT) / 2) / canvasHeight) * 100
  return `M ${fx} ${fy} L ${tx} ${ty}`
}

export function edgePathFromRecord(
  edge: PixelGraphEdge,
  canvasWidth: number,
  canvasHeight: number,
): string {
  const from = (edge.from_ ?? edge.from) as number[] | undefined
  const to = edge.to as number[] | undefined
  if (!from || !to) {
    return ''
  }
  const fx = (from[0] / canvasWidth) * 100
  const fy = (from[1] / canvasHeight) * 100
  const tx = (to[0] / canvasWidth) * 100
  const ty = (to[1] / canvasHeight) * 100
  if (edge.c1 && edge.c2) {
    const c1 = edge.c1
    const c2 = edge.c2
    return `M ${fx} ${fy} C ${(c1[0] / canvasWidth) * 100} ${(c1[1] / canvasHeight) * 100}, ${(c2[0] / canvasWidth) * 100} ${(c2[1] / canvasHeight) * 100}, ${tx} ${ty}`
  }
  return `M ${fx} ${fy} L ${tx} ${ty}`
}
