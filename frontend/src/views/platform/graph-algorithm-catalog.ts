// 图算法目录：页面展示三种常用算法（PageRank / Louvain / Degree），供综合查询页「图算法」面板渲染表单。
// 后端 TRSAlgorithmClient 仍支持全部算法，此处仅为页面展示收敛。
// 参数键与后端注册表保持 camelCase 一致（maxIter、resetProb…）。

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

const maxIter = (label = '迭代次数', hint?: string): AlgorithmParamDef => ({
  key: 'maxIter',
  label,
  type: 'int',
  default: 10,
  min: 1,
  hint,
})

export const GRAPH_ALGORITHMS: GraphAlgorithmDefinition[] = [
  {
    id: 'pagerank',
    label: 'PageRank算法',
    description: '迭代计算顶点重要性排名，输出 pagerank 值',
    params: [
      maxIter(),
      { key: 'resetProb', label: '重启概率', type: 'float', default: 0.15, min: 0, max: 1, step: 0.01 },
    ],
  },
  {
    id: 'louvain',
    label: 'Louvain算法',
    description: '基于模块度增益的层次聚合社区划分',
    params: [
      maxIter('最大迭代'),
      { key: 'internalIter', label: '内部迭代', type: 'int', default: 10, min: 1 },
      { key: 'tol', label: '收敛阈值', type: 'float', default: 0.0001, min: 0, step: 0.0001 },
    ],
  },
  {
    id: 'degreestatic',
    label: 'Degree算法',
    description: '统计每个顶点的出度 / 入度 / 总度',
    params: [],
  },
]
