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
  /** 高级参数：折叠进「高级参数」区，主表单只保留必填业务输入（如关系类型） */
  advanced?: boolean
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
    params: [
      {
        key: 'maxIter',
        label: '最大迭代次数',
        type: 'int',
        default: 10,
        min: 1,
        advanced: true,
        hint: '迭代轮数，越大越收敛，默认 10',
      },
      {
        key: 'resetProb',
        label: '重置概率',
        type: 'float',
        default: 0.15,
        min: 0,
        max: 1,
        step: 0.01,
        advanced: true,
        hint: '随机跳转概率，0.15 为经典值',
      },
    ],
  },
  {
    id: 'louvain',
    label: 'Louvain算法',
    description:
      '社区发现：将关系紧密的节点划分到同一社区，例如专家合作群体、机构群体',
    params: [
      {
        key: 'maxIter',
        label: '最大迭代',
        type: 'int',
        default: 20,
        min: 1,
        advanced: true,
        hint: '外部迭代轮数，默认 20（与服务端默认一致）',
      },
      {
        key: 'internalIter',
        label: '内部迭代',
        type: 'int',
        default: 10,
        min: 1,
        advanced: true,
        hint: '每轮社区内局部移动的迭代数，默认 10',
      },
      {
        key: 'tol',
        label: '收敛阈值',
        type: 'float',
        default: 0.5,
        min: 0,
        step: 0.01,
        advanced: true,
        hint: '模块度增益低于该值即收敛，默认 0.5',
      },
    ],
  },
  {
    id: 'degreestatic',
    label: 'Degree算法',
    description: '统计每个顶点的出度 / 入度 / 总度',
    params: [],
  },
]
