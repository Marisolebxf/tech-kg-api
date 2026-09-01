import type { GraphEdgeData, GraphNodeData } from '../data/graph-presets'

/**
 * 溯源三要素（与九大业务功能页统一口径）：
 * 【源数据表】= MySQL 源表名；【英文字段名】= MySQL 英文字段名；【图空间 VID】= 图空间里的 vid。
 */
export interface ProvenanceTriple {
  sourceTable: string
  sourceField: string
  graphVid: string
}

const UNKNOWN = '—'

/**
 * 节点溯源三要素推导（对齐九大业务启发式）：
 * - 源数据表：节点 properties.source_table（机构域 ETL 写 organization_base），缺失显示 —
 * - 英文字段名：organization_base → organization_id；dwd_scholar → scholar_id；
 *   机构/企业节点兜底 organization_id；其余按 source_record_id 主键口径
 * - 图空间 VID：graph-search 返回的节点 id 即真实 vid
 */
export function nodeProvenanceTriple(node: GraphNodeData): ProvenanceTriple {
  const table = node.sourceTable || UNKNOWN
  let field = UNKNOWN
  if (table === 'organization_base') {
    field = 'organization_id'
  } else if (table === 'dwd_scholar') {
    field = 'scholar_id'
  } else if (node.nodeType === 'company') {
    field = 'enterprise_id'
  } else if (node.nodeType === 'org') {
    field = 'organization_id'
  } else if (node.sourceRecordId) {
    field = 'source_record_id'
  }
  return {
    sourceTable: table,
    sourceField: field,
    graphVid: node.id,
  }
}

/** 边溯源三要素：边自身的 source_table / source_record_id 字段口径 + 边 id（图空间内唯一标识）。 */
export function edgeProvenanceTriple(edge: GraphEdgeData): ProvenanceTriple {
  return {
    sourceTable: edge.sourceTable || UNKNOWN,
    sourceField: edge.sourceRecordId ? 'source_record_id' : UNKNOWN,
    graphVid: edge.id,
  }
}
