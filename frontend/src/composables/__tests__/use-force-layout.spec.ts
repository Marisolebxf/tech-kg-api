import { describe, expect, it } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import type { GraphEdgeData, GraphNodeData } from '../../data/graph-presets'
import { runForceLayout, useForceLayout } from '../use-force-layout'

const CX = 480
const CY = 270
const MIN_X = 40
const MAX_X = 920
const MIN_Y = 40
const MAX_Y = 500

function makeNode(
  id: string,
  overrides: Partial<GraphNodeData> = {},
): GraphNodeData {
  return {
    id,
    label: id,
    nodeType: 'expert',
    x: 0,
    y: 0,
    entityType: '专家',
    relations: '',
    evidence: [],
    ...overrides,
  }
}

function makeEdge(from: string, to: string, label = '关系'): GraphEdgeData {
  return {
    id: `${from}-${to}`,
    from,
    to,
    label,
    category: '直接关系',
  }
}

function star(centerId = 'center', count = 6): {
  nodes: GraphNodeData[]
  edges: GraphEdgeData[]
} {
  const center = makeNode(centerId, { level: 0, nodeType: 'main' })
  const peripherals = Array.from({ length: count }, (_, i) =>
    makeNode(`p${i}`, { nodeType: 'expert' }),
  )
  const edges = peripherals.map((p) => makeEdge(centerId, p.id))
  return { nodes: [center, ...peripherals], edges }
}

describe('runForceLayout', () => {
  it('空节点返回空映射', () => {
    expect(runForceLayout([], []).size).toBe(0)
  })

  it('单节点（无 level0）收敛到画布中心附近', () => {
    const pos = runForceLayout([makeNode('solo')], [])
    const p = pos.get('solo')!
    expect(Math.hypot(p.x - CX, p.y - CY)).toBeLessThan(2)
  })

  it('level===0 中心节点精确钉在画布中心', () => {
    const { nodes, edges } = star('center', 5)
    const pos = runForceLayout(nodes, edges)
    const p = pos.get('center')!
    expect(p.x).toBeCloseTo(CX, 3)
    expect(p.y).toBeCloseTo(CY, 3)
  })

  it('同输入两次调用结果完全一致（确定性）', () => {
    const { nodes, edges } = star('center', 7)
    const a = runForceLayout(nodes, edges)
    const b = runForceLayout(nodes, edges)
    expect([...a.entries()]).toEqual([...b.entries()])
  })

  it('同 id+拓扑但不同输入坐标，输出一致（输入坐标无关）', () => {
    const base = star('center', 6)
    const shifted: GraphNodeData[] = base.nodes.map((n) => ({
      ...n,
      x: 9999,
      y: -9999,
    }))
    const a = runForceLayout(base.nodes, base.edges)
    const b = runForceLayout(shifted, base.edges)
    expect([...a.entries()]).toEqual([...b.entries()])
  })

  it('所有节点落在边界范围内', () => {
    const { nodes, edges } = star('center', 8)
    const pos = runForceLayout(nodes, edges)
    for (const p of pos.values()) {
      expect(p.x).toBeGreaterThanOrEqual(MIN_X)
      expect(p.x).toBeLessThanOrEqual(MAX_X)
      expect(p.y).toBeGreaterThanOrEqual(MIN_Y)
      expect(p.y).toBeLessThanOrEqual(MAX_Y)
    }
  })

  it('circle 形节点两两不重叠', () => {
    const { nodes, edges } = star('center', 8)
    const pos = runForceLayout(nodes, edges)
    const list = nodes.map((n) => ({
      id: n.id,
      p: pos.get(n.id)!,
      r: (n.radius ?? (n.level === 0 ? 20 : 15)) + 20,
    }))
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const d = Math.hypot(
          list[i].p.x - list[j].p.x,
          list[i].p.y - list[j].p.y,
        )
        expect(d).toBeGreaterThanOrEqual(list[i].r + list[j].r - 1)
      }
    }
  })

  it('两个相连节点的距离收敛到弹簧长度附近', () => {
    const a = makeNode('a')
    const b = makeNode('b')
    const pos = runForceLayout([a, b], [makeEdge('a', 'b')])
    const d = Math.hypot(
      pos.get('a')!.x - pos.get('b')!.x,
      pos.get('a')!.y - pos.get('b')!.y,
    )
    expect(d).toBeGreaterThan(150)
    expect(d).toBeLessThan(260)
  })

  it('边引用未知节点时不抛错且被忽略', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const edges = [makeEdge('a', 'ghost')]
    expect(() => runForceLayout(nodes, edges)).not.toThrow()
    const pos = runForceLayout(nodes, edges)
    expect(pos.has('a')).toBe(true)
    expect(pos.has('ghost')).toBe(false)
  })

  it('重复 id 被去重（保留首个）', () => {
    const first = makeNode('dup', { nodeType: 'main', level: 0 })
    const second = makeNode('dup', { nodeType: 'expert' })
    const pos = runForceLayout([first, second], [])
    expect(pos.size).toBe(1)
    // level0 的首个被保留 → 钉中心
    expect(pos.get('dup')!.x).toBeCloseTo(CX, 3)
  })

  it('无连接的孤立节点仍不重叠且在边界内', () => {
    const nodes = Array.from({ length: 5 }, (_, i) => makeNode(`iso${i}`))
    const pos = runForceLayout(nodes, [])
    const list = nodes.map((n) => ({
      p: pos.get(n.id)!,
      r: 15 + 20,
    }))
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const d = Math.hypot(
          list[i].p.x - list[j].p.x,
          list[i].p.y - list[j].p.y,
        )
        expect(d).toBeGreaterThanOrEqual(list[i].r + list[j].r - 1)
      }
      expect(list[i].p.x).toBeGreaterThanOrEqual(MIN_X)
      expect(list[i].p.x).toBeLessThanOrEqual(MAX_X)
    }
  })
})

describe('useForceLayout', () => {
  it('首次即产出已布局节点', () => {
    const scope = effectScope(true)
    const result = scope.run(() => {
      const nodes = ref([makeNode('a'), makeNode('b')])
      const edges = ref([makeEdge('a', 'b')])
      return useForceLayout(nodes, edges)
    })!
    expect(result.laidOutNodes.value.length).toBe(2)
    expect(result.laidOutNodes.value[0]).toHaveProperty('x')
    expect(result.laidOutNodes.value[0]).toHaveProperty('y')
    scope.stop()
  })

  it('仅改节点 x/y 不触发重布局', async () => {
    const scope = effectScope(true)
    const initial = ref<GraphNodeData[]>([makeNode('a'), makeNode('b')])
    const edges = ref([makeEdge('a', 'b')])
    const result = scope.run(() =>
      useForceLayout(initial, edges),
    )!
    const beforeX = result.laidOutNodes.value[0].x
    // 改坐标但保持 id/拓扑不变
    initial.value = initial.value.map((n) => ({ ...n, x: 9999, y: 9999 }))
    await nextTick()
    expect(result.laidOutNodes.value[0].x).toBe(beforeX)
    scope.stop()
  })

  it('改节点 id 集合触发重布局', async () => {
    const scope = effectScope(true)
    const nodes = ref<GraphNodeData[]>([makeNode('a'), makeNode('b')])
    const edges = ref<GraphEdgeData[]>([makeEdge('a', 'b')])
    const result = scope.run(() => useForceLayout(nodes, edges))!
    expect(result.laidOutNodes.value.map((n) => n.id).join(',')).toBe('a,b')
    nodes.value = [makeNode('a'), makeNode('c')]
    edges.value = [makeEdge('a', 'c')]
    await nextTick()
    expect(result.laidOutNodes.value.map((n) => n.id).join(',')).toBe('a,c')
    scope.stop()
  })
})
