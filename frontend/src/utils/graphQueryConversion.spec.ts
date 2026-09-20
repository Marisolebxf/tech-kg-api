import { describe, expect, it } from 'vitest'

import type { GraphData } from '../api/graphSearch'
import {
  applyNodeCap,
  assignLabelTones,
  buildApiNodeEvidence,
  convertApiGraphEdges,
  convertApiGraphNodes,
  deduplicateGraphEdges,
  deduplicateGraphNodes,
  getApiNodeDisplayName,
  mergeGraphData,
  normalizeReturnedSubgraph,
  readConfidence,
  readStringProperty,
} from './graphQueryConversion'

const node = (id: string, labels: string[] = ['专家'], properties: Record<string, unknown> = {}) => ({
  id,
  labels,
  properties,
})

const edge = (id: string, source: string, target: string, properties: Record<string, unknown> = {}) => ({
  id,
  type: '撰写',
  source,
  target,
  properties,
})

describe('assignLabelTones（动态标签 → 画布色调）', () => {
  it('≤10 个标签单射（图例无撞色），且跨调用顺序稳定', () => {
    const labels = ['专家', '论文', '机构', '撰写', '专利', '事件', '主题', '产业链', '字段', '来源']
    const a = assignLabelTones(labels)
    const b = assignLabelTones([...labels].reverse())
    expect([...new Set(a.values())]).toHaveLength(labels.length)
    for (const [label, tone] of a) {
      expect(b.get(label)).toBe(tone)
    }
  })

  it('>10 个标签轮转共享色调，去重输入', () => {
    const assignment = assignLabelTones(['a', 'b', 'a', ...Array.from({ length: 12 }, (_, i) => `t${i}`)])
    expect(assignment.size).toBe(14)
    expect([...new Set(assignment.values())].length).toBe(10)
  })
})

describe('属性读取', () => {
  it('readStringProperty 空值视为缺失', () => {
    expect(readStringProperty({ a: '', b: null, c: 'x' }, 'a')).toBeUndefined()
    expect(readStringProperty({ a: '', b: null, c: 'x' }, 'b')).toBeUndefined()
    expect(readStringProperty({ a: '', b: null, c: 'x' }, 'c')).toBe('x')
  })

  it('readConfidence 只接受 0～1 数值', () => {
    expect(readConfidence({ confidence: 0.8 })).toBe(0.8)
    expect(readConfidence({ confidence: '0.9' })).toBe(0.9)
    expect(readConfidence({ confidence: 1.5 })).toBeUndefined()
    expect(readConfidence({ confidence: 'abc' })).toBeUndefined()
    expect(readConfidence({})).toBeUndefined()
  })

  it('显示名按属性优先级，兜底节点 ID', () => {
    expect(getApiNodeDisplayName(node('n1', ['专家'], { name_cn: '张三', name: 'zhang' }))).toBe('张三')
    expect(getApiNodeDisplayName(node('n1', ['论文'], { title: '论文题' }))).toBe('论文题')
    expect(getApiNodeDisplayName(node('n1'))).toBe('n1')
  })

  it('属性摘要最多 6 条，无属性退化为节点 ID', () => {
    expect(buildApiNodeEvidence(node('n1', ['专家'], { a: 1, b: 'x' }))).toEqual(['a: 1', 'b: x'])
    expect(buildApiNodeEvidence(node('n1'))).toEqual(['节点 ID: n1'])
  })
})

describe('normalizeReturnedSubgraph（裁剪）', () => {
  it('丢端点缺失的边，并按中心 BFS 裁掉不可达节点', () => {
    const data: GraphData = {
      nodes: [node('c'), node('a'), node('b'), node('orphan')],
      edges: [
        edge('e1', 'c', 'a'),
        edge('e2', 'a', 'b'),
        edge('e-dangling', 'c', 'ghost'),
        // orphan 无任何与中心连通的边
      ],
    }
    const normalized = normalizeReturnedSubgraph(data, 'c')
    expect(normalized.nodes.map((n) => n.id).sort()).toEqual(['a', 'b', 'c'])
    expect(normalized.edges.map((e) => e.id)).toEqual(['e1', 'e2'])
  })

  it('中心不在结果里也能安全返回空图', () => {
    const normalized = normalizeReturnedSubgraph({ nodes: [node('a')], edges: [] }, 'c')
    expect(normalized.nodes).toEqual([])
  })
})

describe('去重与合并（slash-VID 回退合并用）', () => {
  it('节点/边按 id 去重', () => {
    expect(deduplicateGraphNodes([node('a'), node('a'), node('b')])).toHaveLength(2)
    expect(deduplicateGraphEdges([edge('e1', 'a', 'b'), edge('e1', 'a', 'b')])).toHaveLength(1)
  })

  it('mergeGraphData 合并多份子图', () => {
    const merged = mergeGraphData([
      { nodes: [node('a'), node('b')], edges: [edge('e1', 'a', 'b')] },
      { nodes: [node('b'), node('c')], edges: [edge('e1', 'a', 'b'), edge('e2', 'b', 'c')] },
    ])
    expect(merged.nodes.map((n) => n.id).sort()).toEqual(['a', 'b', 'c'])
    expect(merged.edges.map((e) => e.id).sort()).toEqual(['e1', 'e2'])
  })
})

describe('画布数据转换', () => {
  const data: GraphData = {
    nodes: [
      node('c', ['专家'], { name: '中心', confidence: 0.9, source_table: 'scholar' }),
      node('p', ['论文'], { title: '论文 A' }),
    ],
    edges: [edge('e1', 'c', 'p', { confidence: 0.5, match_evidence: '共作' })],
  }
  const tones = assignLabelTones(['专家', '论文'])

  it('节点转换：中心排前/level 0、色调与类型来自动态标签、溯源透传', () => {
    const nodes = convertApiGraphNodes(data, 'c', (label) => tones.get(label) ?? 'topic')
    expect(nodes[0].id).toBe('c')
    expect(nodes[0].level).toBe(0)
    expect(nodes[0].label).toBe('中心')
    expect(nodes[0].entityType).toBe('专家')
    expect(nodes[0].nodeType).toBe(tones.get('专家'))
    expect(nodes[0].confidence).toBe(0.9)
    expect(nodes[0].sourceTable).toBe('scholar')
    expect(nodes.find((n) => n.id === 'p')?.entityType).toBe('论文')
  })

  it('边转换：category/label 用边类型原文，置信度与匹配证据透传', () => {
    const [converted] = convertApiGraphEdges(data.edges)
    expect(converted.category).toBe('撰写')
    expect(converted.label).toBe('撰写')
    expect(converted.confidence).toBe(0.5)
    expect(converted.matchEvidence).toBe('共作')
  })
})

describe('applyNodeCap（节点数上限保护）', () => {
  const nodes = Array.from({ length: 5 }, (_, i) => ({
    id: `n${i}`,
    label: `节点${i}`,
    nodeType: 'topic' as const,
    x: 0,
    y: 0,
    entityType: '专家',
    relations: '',
    evidence: [],
  }))
  const edges = [
    { id: 'e1', from: 'n0', to: 'n1', label: '撰写', category: '撰写' },
    { id: 'e2', from: 'n0', to: 'n2', label: '撰写', category: '撰写' },
    { id: 'e3', from: 'n1', to: 'n2', label: '撰写', category: '撰写' },
    { id: 'e4', from: 'n3', to: 'n4', label: '撰写', category: '撰写' },
  ]

  it('未超上限原样返回', () => {
    const result = applyNodeCap(nodes, edges, 5, 'n0')
    expect(result.nodes).toHaveLength(5)
    expect(result.hiddenCount).toBe(0)
  })

  it('超上限：中心保留、按度数取前 N、裁悬空边', () => {
    // cap=3：中心 n0 必留；度数 n1=2,n2=2,n3=1,n4=1 → 取 n1,n2；n3/n4 被裁，e4 悬空被裁
    const result = applyNodeCap(nodes, edges, 3, 'n0')
    expect(result.nodes.map((n) => n.id).sort()).toEqual(['n0', 'n1', 'n2'])
    expect(result.hiddenCount).toBe(2)
    expect(result.edges.map((e) => e.id)).toEqual(['e1', 'e2', 'e3'])
  })
})
