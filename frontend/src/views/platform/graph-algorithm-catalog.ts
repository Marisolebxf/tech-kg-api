// 图算法目录：页面展示三种常用算法（PageRank / Louvain / Degree），供综合查询页「图算法」面板渲染表单。
// 后端 TRSAlgorithmClient 仍支持全部算法，此处仅为页面展示收敛。
// 算法调优参数（maxIter、resetProb 等）不在页面暴露，统一使用后端默认值。

export type AlgorithmParamType = 'int' | 'float' | 'bool' | 'enum' | 'text'

export interface AlgorithmParamDef {
  /** 参数键（camelCase，直传后端 params） */
  key: string
  label: string
  type: AlgorithmParamType
  required?: boolean
  default?: number | string | boolean
  min?: number
  max?: number
  step?: number
  options?: Array<{ value: string; label: string }>
  placeholder?: string
  hint?: string
}

export interface GraphAlgorithmDefinition {
  /** 算法标识（小写，直传后端） */
  id: string
  label: string
  description: string
  params: AlgorithmParamDef[]
}

export const GRAPH_ALGORITHMS: GraphAlgorithmDefinition[] = [
  {
    id: 'pagerank',
    label: 'PageRank算法',
    description:
      '节点重要性分析：衡量节点在关系网络中的重要程度，可用于发现重要专家、机构、论文等',
    params: [],
  },
  {
    id: 'louvain',
    label: 'Louvain算法',
    description:
      '社区发现：将关系紧密的节点划分到同一社区，例如专家合作群体、机构群体',
    params: [],
  },
  {
    id: 'degreestatic',
    label: 'Degree算法',
    description: '统计每个顶点的出度 / 入度 / 总度',
    params: [],
  },
]
