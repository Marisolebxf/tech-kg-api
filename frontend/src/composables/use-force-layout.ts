import {
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
  type Ref,
} from 'vue'

import type { GraphEdgeData, GraphNodeData } from '../data/graph-presets'

export interface Vec {
  x: number
  y: number
}

export interface ForceLayoutOptions {
  /** 节点形状，决定碰撞半径算法；默认 'circle'，与画布 nodeShape 默认一致。 */
  nodeShape?: 'rect' | 'circle'
  /** 画布宽度，默认 760（与 SVG viewBox 一致）。 */
  width?: number
  /** 画布高度，默认 430。 */
  height?: number
  /** 最大迭代次数，默认 300。 */
  maxTicks?: number
}

/**
 * 力导向布局常量（为 760×430 画布、3–32 节点调校）。
 * 调参优先动 REPULSION（越大越松散）与 SPRING_LENGTH（边视觉长度）。
 */
const CX = 480
const CY = 270
const MIN_X = 40
const MAX_X = 920
const MIN_Y = 40
const MAX_Y = 500
const REPULSION = 6000
const SPRING_STRENGTH = 0.05
const SPRING_LENGTH = 220
const GRAVITY = 0.002
const VELOCITY_DECAY = 0.75
const ALPHA = 1
const ALPHA_DECAY = 0.985
const ALPHA_MIN = 0.001
const MAX_TICKS = 600
const COLLISION_GAP = 20
/** 边避让：节点离非自身连线段的最小距离（基础半径外额外留白）。 */
const EDGE_AVOID_PAD = 12
/** 边避让推力强度，按超出量线性施加。 */
const EDGE_AVOID_STRENGTH = 0.25

/** FNV-1a 字符串哈希，返回 uint32，用作确定性伪随机种子。 */
function hashStr(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h >>> 0
}

/** 节点基础半径（不含避让间距），与画布组件 nodeRadius 对齐。 */
function nodeBaseRadius(node: GraphNodeData): number {
  return node.radius ?? (node.level === 0 ? 20 : 15)
}

/** 节点碰撞半径，复刻画布组件 nodeWidth/nodeHeight 形状逻辑。 */
function nodeCollisionRadius(
  node: GraphNodeData,
  shape: 'rect' | 'circle',
): number {
  if (shape === 'circle') {
    return nodeBaseRadius(node) + COLLISION_GAP
  }
  const w = Math.min(node.level === 0 ? 164 : 144, Math.max(104, node.label.length * 11 + 28))
  const h = node.level === 0 ? 54 : 46
  return Math.hypot(w, h) / 2 + COLLISION_GAP
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min
  if (value > max) return max
  return value
}

/**
 * 纯函数力导向布局：确定性（同输入→同输出，无 Math.random），
 * level===0 的首个中心节点钉在画布中心 (380,215) 不参与迭代，提供稳定锚点。
 * 返回 id→{x,y} 的位置映射。
 */
export function runForceLayout(
  nodes: readonly GraphNodeData[],
  edges: readonly GraphEdgeData[],
  options?: ForceLayoutOptions,
): Map<string, Vec> {
  const result = new Map<string, Vec>()
  const shape = options?.nodeShape ?? 'circle'
  const maxTicks = options?.maxTicks ?? MAX_TICKS

  // 去重 by id（保留首个），固定迭代顺序以保证确定性。
  const seen = new Set<string>()
  const ordered: GraphNodeData[] = []
  for (const node of nodes) {
    if (!node || !node.id || seen.has(node.id)) continue
    seen.add(node.id)
    ordered.push(node)
  }
  if (!ordered.length) return result

  // 单节点无斥力/弹簧作用，gravity 偏弱不足以收敛，直接居中。
  if (ordered.length === 1) {
    result.set(ordered[0].id, { x: CX, y: CY })
    return result
  }

  const n = ordered.length
  const idx = new Map<string, number>()
  ordered.forEach((node, i) => idx.set(node.id, i))

  // 首个 level===0 钉中心；无 level0 时不钉（中心引力 + 边界已足够稳定）。
  const pinned = new Set<number>()
  const centerIdx = ordered.findIndex((node) => node.level === 0)
  if (centerIdx >= 0) pinned.add(centerIdx)

  const x = new Float64Array(n)
  const y = new Float64Array(n)
  const vx = new Float64Array(n)
  const vy = new Float64Array(n)
  const r = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    r[i] = nodeCollisionRadius(ordered[i], shape)
    if (pinned.has(i)) {
      x[i] = CX
      y[i] = CY
    } else {
      const h = hashStr(ordered[i].id)
      const angle = ((h % 2000) / 2000) * Math.PI * 2
      const radius = 70 + (hashStr(`${ordered[i].id}#r`) % 90)
      x[i] = CX + radius * Math.cos(angle)
      y[i] = CY + radius * Math.sin(angle)
    }
  }

  // 邻接表：只保留两端都在 nodes 中的边，跳过自环。
  const adj: Array<[number, number]> = []
  for (const e of edges) {
    if (!e) continue
    const a = idx.get(e.from)
    const b = idx.get(e.to)
    if (a === undefined || b === undefined || a === b) continue
    adj.push([a, b])
  }

  const fx = new Float64Array(n)
  const fy = new Float64Array(n)
  let alpha = ALPHA
  for (let tick = 0; tick < maxTicks; tick++) {
    if (alpha < ALPHA_MIN) break
    fx.fill(0)
    fy.fill(0)

    // 斥力：O(n²)，对每对节点施加反比距离平方的推力。
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = x[i] - x[j]
        let dy = y[i] - y[j]
        let d2 = dx * dx + dy * dy
        if (d2 < 0.01) {
          const h = hashStr(`${ordered[i].id}#${ordered[j].id}`)
          dx = Math.cos(h) * 0.5
          dy = Math.sin(h) * 0.5
          d2 = dx * dx + dy * dy || 0.01
        }
        const dist = Math.sqrt(d2)
        const force = REPULSION / d2
        const ux = dx / dist
        const uy = dy / dist
        fx[i] += ux * force
        fy[i] += uy * force
        fx[j] -= ux * force
        fy[j] -= uy * force
      }
    }

    // 弹簧：每条边朝理想长度 SPRING_LENGTH 收/放。
    for (const [a, b] of adj) {
      const dx = x[b] - x[a]
      const dy = y[b] - y[a]
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
      const diff = dist - SPRING_LENGTH
      const ux = dx / dist
      const uy = dy / dist
      const f = SPRING_STRENGTH * diff
      fx[a] += ux * f
      fy[a] += uy * f
      fx[b] -= ux * f
      fy[b] -= uy * f
    }

    // 边避让：非端点节点若离某条边线段太近，沿垂直方向推开，
    // 使节点与其未参与连线保持距离，避免节点压在连线上。
    for (const [a, b] of adj) {
      const ex = x[b] - x[a]
      const ey = y[b] - y[a]
      const segLen2 = ex * ex + ey * ey
      if (segLen2 < 0.01) continue
      for (let k = 0; k < n; k++) {
        if (k === a || k === b) continue
        const kx = x[k] - x[a]
        const ky = y[k] - y[a]
        let t = (kx * ex + ky * ey) / segLen2
        if (t < 0) t = 0
        else if (t > 1) t = 1
        const cx = x[a] + t * ex
        const cy = y[a] + t * ey
        let ndx = x[k] - cx
        let ndy = y[k] - cy
        let nd2 = ndx * ndx + ndy * ndy
        if (nd2 < 0.0001) {
          // 节点正好落在线段上：用确定性方向强制分开。
          const h = hashStr(`${ordered[k].id}#${ordered[a].id}#${ordered[b].id}`)
          ndx = Math.cos(h) * 0.5
          ndy = Math.sin(h) * 0.5
          nd2 = 0.01
        }
        const ndist = Math.sqrt(nd2)
        const threshold = nodeBaseRadius(ordered[k]) + EDGE_AVOID_PAD
        if (ndist >= threshold) continue
        const overlap = threshold - ndist
        const nux = ndx / ndist
        const nuy = ndy / ndist
        const ef = EDGE_AVOID_STRENGTH * overlap
        fx[k] += nux * ef
        fy[k] += nuy * ef
      }
    }

    // 中心引力：非钉定节点弱拉向画布中心，防止飞散。
    for (let i = 0; i < n; i++) {
      if (pinned.has(i)) continue
      fx[i] += (CX - x[i]) * GRAVITY
      fy[i] += (CY - y[i]) * GRAVITY
    }

    // 积分 + 边界 clamp。
    for (let i = 0; i < n; i++) {
      if (pinned.has(i)) {
        vx[i] = 0
        vy[i] = 0
        continue
      }
      vx[i] = (vx[i] + fx[i] * alpha) * VELOCITY_DECAY
      vy[i] = (vy[i] + fy[i] * alpha) * VELOCITY_DECAY
      x[i] = clamp(x[i] + vx[i], MIN_X, MAX_X)
      y[i] = clamp(y[i] + vy[i], MIN_Y, MAX_Y)
    }

    // 碰撞解决：重叠对沿连线推开到 r_i+r_j，钉定节点不动。
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = x[j] - x[i]
        const dy = y[j] - y[i]
        const d = Math.sqrt(dx * dx + dy * dy)
        const minD = r[i] + r[j]
        if (d >= minD) continue
        if (d > 0.0001) {
          const overlap = (minD - d) / 2
          const ux = dx / d
          const uy = dy / d
          if (pinned.has(i)) {
            x[j] = clamp(x[j] + ux * overlap * 2, MIN_X, MAX_X)
            y[j] = clamp(y[j] + uy * overlap * 2, MIN_Y, MAX_Y)
          } else if (pinned.has(j)) {
            x[i] = clamp(x[i] - ux * overlap * 2, MIN_X, MAX_X)
            y[i] = clamp(y[i] - uy * overlap * 2, MIN_Y, MAX_Y)
          } else {
            x[i] = clamp(x[i] - ux * overlap, MIN_X, MAX_X)
            y[i] = clamp(y[i] - uy * overlap, MIN_Y, MAX_Y)
            x[j] = clamp(x[j] + ux * overlap, MIN_X, MAX_X)
            y[j] = clamp(y[j] + uy * overlap, MIN_Y, MAX_Y)
          }
        } else {
          // 完全重叠：用确定性方向强制分开。
          const h = hashStr(`${ordered[i].id}#${ordered[j].id}`)
          const ang = (h % 2000) / 2000 * Math.PI * 2
          const step = minD
          if (!pinned.has(i)) {
            x[i] = clamp(x[i] - Math.cos(ang) * step, MIN_X, MAX_X)
            y[i] = clamp(y[i] - Math.sin(ang) * step, MIN_Y, MAX_Y)
          }
          if (!pinned.has(j)) {
            x[j] = clamp(x[j] + Math.cos(ang) * step, MIN_X, MAX_X)
            y[j] = clamp(y[j] + Math.sin(ang) * step, MIN_Y, MAX_Y)
          }
        }
      }
    }

    alpha *= ALPHA_DECAY
  }

  for (let i = 0; i < n; i++) {
    result.set(ordered[i].id, { x: x[i], y: y[i] })
  }
  return result
}

/**
 * 响应式力导向布局。仅当节点/边集合签名（id 列表 + 边拓扑 + 形状 + 画布尺寸）变化时重算，
 * 不响应 selectedNodeId / selectedEdgeId / activeCategories / 平移缩放。
 * immediate 首次运行，保证首屏渲染前已布局（无预设坐标闪烁）。
 * laidOutNodes 元素为 {...原节点, x, y}，保留全部非位置字段。
 */
export function useForceLayout(
  nodes: MaybeRefOrGetter<readonly GraphNodeData[]>,
  edges: MaybeRefOrGetter<readonly GraphEdgeData[]>,
  options?: MaybeRefOrGetter<ForceLayoutOptions | undefined>,
): { laidOutNodes: Ref<GraphNodeData[]> } {
  const laidOutNodes = ref<GraphNodeData[]>([]) as Ref<GraphNodeData[]>

  const signature = () => {
    const ns = toValue(nodes) ?? []
    const es = toValue(edges) ?? []
    const o = toValue(options)
    return [
      ns.map((node) => node.id).join('|'),
      es.map((e) => `${e.from}>${e.to}`).join('|'),
      o?.nodeShape ?? 'circle',
      o?.width ?? 760,
      o?.height ?? 430,
    ].join('#')
  }

  watch(
    signature,
    () => {
      const ns = toValue(nodes) ?? []
      const es = toValue(edges) ?? []
      const pos = runForceLayout(ns, es, toValue(options))
      laidOutNodes.value = ns.map((node) => {
        const p = pos.get(node.id) ?? { x: node.x, y: node.y }
        return { ...node, x: p.x, y: p.y }
      })
    },
    { immediate: true },
  )

  return { laidOutNodes }
}
