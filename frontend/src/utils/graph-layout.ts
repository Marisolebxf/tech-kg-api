import { inferEdgeNodeIds, refreshGraphEdges } from './graph-edges'

export interface LayoutBox {
  key: string
  x: number
  y: number
  width: number
  height: number
}

export interface PercentLayoutBox {
  key: string
  x: number
  y: number
  w: number
  h: number
}

function boxesOverlap(a: LayoutBox, b: LayoutBox, gap: number): boolean {
  return (
    a.x < b.x + b.width + gap &&
    a.x + a.width + gap > b.x &&
    a.y < b.y + b.height + gap &&
    a.y + a.height + gap > b.y
  )
}

/** Iteratively push overlapping boxes apart. */
export function separateLayoutBoxes(
  nodes: LayoutBox[],
  gap = 24,
  iterations = 100,
  fixedKeys: string[] = [],
): void {
  const fixed = new Set(fixedKeys)
  for (let iter = 0; iter < iterations; iter += 1) {
    let moved = false
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i]
        const b = nodes[j]
        if (!boxesOverlap(a, b, gap)) {
          continue
        }
        const acx = a.x + a.width / 2
        const acy = a.y + a.height / 2
        const bcx = b.x + b.width / 2
        const bcy = b.y + b.height / 2
        const dx = acx - bcx
        const dy = acy - bcy
        const dist = Math.hypot(dx, dy) || 1
        const overlapX = a.width / 2 + b.width / 2 + gap - Math.abs(dx)
        const overlapY = a.height / 2 + b.height / 2 + gap - Math.abs(dy)
        const push = Math.max(overlapX, overlapY) / 2 + 0.5
        const px = (dx / dist) * push
        const py = (dy / dist) * push
        if (!fixed.has(a.key)) {
          a.x += px
          a.y += py
          moved = true
        }
        if (!fixed.has(b.key)) {
          b.x -= px
          b.y -= py
          moved = true
        }
      }
    }
    if (!moved) {
      break
    }
  }
}

function boundingBox(nodes: LayoutBox[], padding: number) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const node of nodes) {
    minX = Math.min(minX, node.x)
    minY = Math.min(minY, node.y)
    maxX = Math.max(maxX, node.x + node.width)
    maxY = Math.max(maxY, node.y + node.height)
  }
  if (!Number.isFinite(minX)) {
    return { minX: 0, minY: 0, maxX: padding * 2, maxY: padding * 2 }
  }
  return { minX, minY, maxX, maxY }
}

function shiftIntoCanvas(
  nodes: LayoutBox[],
  width: number,
  height: number,
  padding: number,
): void {
  const box = boundingBox(nodes, padding)
  const contentW = box.maxX - box.minX
  const contentH = box.maxY - box.minY
  const offsetX = padding + (width - contentW - 2 * padding) / 2 - box.minX
  const offsetY = padding + (height - contentH - 2 * padding) / 2 - box.minY
  for (const node of nodes) {
    node.x += offsetX
    node.y += offsetY
  }
}

function computeRadialRadius(
  count: number,
  satelliteWidth: number,
  satelliteHeight: number,
  centerWidth: number,
  centerHeight: number,
  gap: number,
): number {
  if (count <= 0) {
    return 0
  }
  if (count === 1) {
    return centerWidth / 2 + gap + satelliteWidth / 2
  }
  const sinHalf = Math.sin(Math.PI / count)
  const fromArc = (satelliteWidth + gap) / (2 * sinHalf)
  const fromCenter =
    Math.max(centerWidth, centerHeight) / 2 + gap + Math.max(satelliteWidth, satelliteHeight) / 2
  return Math.max(fromArc, fromCenter, 160)
}

export interface RadialStarLayoutInput<T extends object> {
  center: T & { width: number; height: number; key?: string }
  satellites: Array<T & { width: number; height: number; key?: string }>
  gap?: number
  padding?: number
  minWidth?: number
  minHeight?: number
  maxWidth?: number
  maxHeight?: number
  fixedCenter?: boolean
}

/** Place a center node with satellites on a ring; auto radius + collision separation. */
export function buildRadialStarLayout<T extends object>(
  input: RadialStarLayoutInput<T>,
): { nodes: Array<T & LayoutBox>; width: number; height: number } {
  const gap = input.gap ?? 28
  const padding = input.padding ?? 32
  const minWidth = input.minWidth ?? 640
  const minHeight = input.minHeight ?? 440
  const centerW = input.center.width
  const centerH = input.center.height
  const satW = input.satellites[0]?.width ?? 280
  const satH = input.satellites[0]?.height ?? 90
  const count = input.satellites.length
  const radius = computeRadialRadius(count, satW, satH, centerW, centerH, gap)
  const centerKey = input.center.key ?? 'center'

  const nodes: Array<T & LayoutBox> = [
    {
      ...input.center,
      key: centerKey,
      x: -centerW / 2,
      y: -centerH / 2,
      width: centerW,
      height: centerH,
    } as T & LayoutBox,
  ]

  input.satellites.forEach((satellite, index) => {
    const angle = (2 * Math.PI * index) / (count || 1) - Math.PI / 2
    const sx = radius * Math.cos(angle)
    const sy = radius * Math.sin(angle)
    const width = satellite.width ?? satW
    const height = satellite.height ?? satH
    nodes.push({
      ...satellite,
      key: satellite.key ?? `satellite-${index}`,
      x: sx - width / 2,
      y: sy - height / 2,
      width,
      height,
    } as T & LayoutBox)
  })

  const fixedKeys = input.fixedCenter ? [centerKey] : []
  separateLayoutBoxes(nodes, gap, 120, fixedKeys)

  const box = boundingBox(nodes, padding)
  const width = Math.max(minWidth, box.maxX - box.minX + 2 * padding)
  const height = Math.max(minHeight, box.maxY - box.minY + 2 * padding)
  shiftIntoCanvas(nodes, width, height, padding)

  return clampLayoutSize(nodes, width, height, input.maxWidth ?? 720, input.maxHeight ?? 480)
}

export function clampLayoutSize<T extends LayoutBox>(
  nodes: T[],
  width: number,
  height: number,
  maxWidth: number,
  maxHeight: number,
): { nodes: T[]; width: number; height: number } {
  const scale = Math.min(1, maxWidth / width, maxHeight / height)
  if (scale >= 0.999) {
    return { nodes, width, height }
  }
  for (const node of nodes) {
    node.x *= scale
    node.y *= scale
    node.width *= scale
    node.height *= scale
  }
  return { nodes, width: width * scale, height: height * scale }
}

/** Resolve overlaps in percent-based node maps (0–100 coordinate space). */
export function separatePercentNodes(
  nodes: PercentLayoutBox[],
  gap = 1.2,
  iterations = 80,
): void {
  const boxes: LayoutBox[] = nodes.map((node) => ({
    key: node.key,
    x: node.x,
    y: node.y,
    width: node.w,
    height: node.h,
  }))
  separateLayoutBoxes(boxes, gap, iterations)
  boxes.forEach((box, index) => {
    const node = nodes[index]
    node.x = Math.max(0, Math.min(100 - node.w, box.x))
    node.y = Math.max(0, Math.min(100 - node.h, box.y))
  })
}

export interface PixelGraph {
  width: number
  height: number
  nodes: Array<{
    id: string
    x: number
    y: number
    width?: number
    height?: number
    kind?: string
    [key: string]: unknown
  }>
  edges?: Array<Record<string, unknown>>
}

const DEFAULT_NODE_WIDTH = 240
const DEFAULT_NODE_HEIGHT = 80

/** Normalize API pixel graphs: separate nodes, expand canvas, refresh edge anchors. */
export function normalizePixelGraph(graph: PixelGraph, gap = 18, padding = 28): PixelGraph {
  if (!graph.nodes?.length) {
    return graph
  }

  const nodes = graph.nodes.map((node) => ({
    key: node.id,
    x: node.x,
    y: node.y,
    width: node.width ?? DEFAULT_NODE_WIDTH,
    height: node.height ?? DEFAULT_NODE_HEIGHT,
  }))
  separateLayoutBoxes(nodes, gap, 100)

  const box = boundingBox(nodes, padding)
  let width = Math.max(graph.width ?? 720, box.maxX - box.minX + 2 * padding)
  let height = Math.max(graph.height ?? 480, box.maxY - box.minY + 2 * padding)
  shiftIntoCanvas(nodes, width, height, padding)
  const clamped = clampLayoutSize(nodes, width, height, 720, 480)
  width = clamped.width
  height = clamped.height

  const normalizedNodes = graph.nodes.map((node, index) => ({
    ...node,
    x: clamped.nodes[index].x,
    y: clamped.nodes[index].y,
    width: clamped.nodes[index].width,
    height: clamped.nodes[index].height,
  }))

  const inferredPairs = inferEdgeNodeIds(normalizedNodes)
  const taggedEdges = (graph.edges ?? []).map((edge, index) => {
    const next = { ...edge }
    const pair = inferredPairs[index]
    if (pair) {
      next.fromId = pair.fromId
      next.toId = pair.toId
    }
    return next
  })
  const edges = refreshGraphEdges(normalizedNodes, taggedEdges)

  return { ...graph, width, height, nodes: normalizedNodes, edges }
}
