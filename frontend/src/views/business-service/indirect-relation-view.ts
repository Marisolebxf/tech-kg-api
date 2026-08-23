import type {
  ExpertIndirectRelationResult,
  IndirectNode,
} from '../../api/expertIndirectRelation'
import type {
  GraphEdgeData,
  GraphNodeData,
  GraphNodeType,
} from '../../data/graph-presets'

const edgeLabels: Record<string, string> = {
  COAUTHOR_WITH: '论文合作',
  AFFILIATED_WITH: '机构任职',
  EMPLOYED_BY: '企业任职',
  PARTICIPATES_IN: '参与项目',
  HAS_PARTICIPANT: '项目参与方',
  INVENTED_BY: '专利发明',
  AUTHORED_BY: '论文作者',
  PUBLISHED_IN: '期刊发表',
  CITES: '论文引用',
  CITED_BY: '被引用',
}

const graphNodeType = (node: IndirectNode, isCore = false): GraphNodeType => {
  if (isCore) return 'main'
  const label = node.labels[0]
  if (label === 'Person') return 'expert'
  if (label === 'Organization') return 'org'
  if (label === 'Project' || label === 'Patent' || label === 'PatentFamily') return 'project'
  if (label === 'Paper' || label === 'Journal' || label === 'Report') return 'paper'
  if (label === 'Product' || label === 'Keyword') return 'field'
  if (label === 'Event' || label === 'News') return 'event'
  if (label === 'IndustryChain' || label === 'IndustryNode') return 'chain'
  if (label === 'DataSource') return 'source'
  return 'topic'
}

export const parseRelationTypes = (value: string) => value
  .split(/[、,，;；]/)
  .map((item) => item.trim())
  .filter(Boolean)

export function buildIndirectRelationGraph(result: ExpertIndirectRelationResult) {
  const selectedPaths = result.paths.slice(0, 10)
  const nodeMap = new Map<string, IndirectNode>([[result.coreNode.id, result.coreNode]])
  const nodeLevels = new Map<string, number>([[result.coreNode.id, 0]])
  const nodeStrengths = new Map<string, number>([[result.coreNode.id, 0.96]])
  const nodeEvidences = new Map<string, string[]>()

  selectedPaths.forEach((path) => {
    path.nodes.forEach((node, index) => {
      nodeMap.set(node.id, node)
      nodeLevels.set(node.id, Math.min(nodeLevels.get(node.id) ?? index, index))
      nodeStrengths.set(node.id, Math.max(nodeStrengths.get(node.id) ?? 0, path.strength))
      const evidences = nodeEvidences.get(node.id) ?? []
      if (!evidences.includes(path.pathText) && evidences.length < 2) evidences.push(path.pathText)
      nodeEvidences.set(node.id, evidences)
    })
  })

  const maxLevel = Math.max(2, ...nodeLevels.values())
  const grouped = new Map<number, string[]>()
  nodeLevels.forEach((level, id) => {
    grouped.set(level, [...(grouped.get(level) ?? []), id])
  })

  const nodes: GraphNodeData[] = Array.from(nodeMap.values()).map((node) => {
    const level = nodeLevels.get(node.id) ?? maxLevel
    const idsAtLevel = grouped.get(level) ?? [node.id]
    const index = idsAtLevel.indexOf(node.id)
    const y = idsAtLevel.length === 1 ? 215 : 65 + index * (310 / (idsAtLevel.length - 1))
    return {
      id: node.id,
      label: node.name,
      nodeType: graphNodeType(node, node.id === result.coreNode.id),
      x: 85 + level * (550 / maxLevel),
      y,
      entityType: node.id === result.coreNode.id ? '核心专家' : node.entityType,
      confidence: nodeStrengths.get(node.id) ?? 0.8,
      relations: level === 0 ? `间接节点 ${result.indirectNodeCount}` : `${level} 跳关联`,
      evidence: nodeEvidences.get(node.id) ?? ['节点来自知识图谱多跳子图。'],
    }
  })

  const edgeMap = new Map<string, GraphEdgeData>()
  selectedPaths.forEach((path) => {
    path.edges.forEach((edge, index) => {
      const key = `${edge.type}:${[edge.source, edge.target].sort().join(':')}`
      if (edgeMap.has(key)) return
      edgeMap.set(key, {
        id: edge.id || key,
        from: edge.source,
        to: edge.target,
        label: edgeLabels[edge.type] ?? edge.type,
        category: index === 0 ? '直接关系' : '间接关系',
      })
    })
  })
  return { nodes, edges: Array.from(edgeMap.values()) }
}

export function indirectSummaryRows(result: ExpertIndirectRelationResult) {
  const relationTypes = Object.entries(result.relationTypeCount)
    .map(([type, count]) => `${type} ${count} 条`)
    .join('、') || '暂无符合阈值的间接关系'
  const directNames = result.directNodes.slice(0, 5).map((node) => node.name).join('、') || '暂无'
  const indirectNames = result.indirectNodes.slice(0, 5).map((node) => node.name).join('、') || '暂无'
  const representative = result.paths[0]?.pathText || '暂无符合阈值的路径'
  const secondary = result.paths[1]?.pathText || '暂无第二条代表路径'
  return [
    ['核心节点', `${result.coreNode.name}｜${result.coreNode.entityType}`] as const,
    ['路径分析深度', `${result.pathDepth} 跳`] as const,
    ['直接关联节点', `${directNames}（共 ${result.directNodeCount} 个）`] as const,
    ['间接关联节点', `${indirectNames}（共 ${result.indirectNodeCount} 个）`] as const,
    ['间接关系类型', relationTypes] as const,
    ['代表传递路径', representative] as const,
    ['其他代表路径', secondary] as const,
    ['路径数量', `${result.pathCount} 条`] as const,
    ['关联强度', `最高 ${result.maxStrength.toFixed(2)}｜平均 ${result.averageStrength.toFixed(2)}｜阈值 ${result.minStrength.toFixed(2)}`] as const,
  ]
}
