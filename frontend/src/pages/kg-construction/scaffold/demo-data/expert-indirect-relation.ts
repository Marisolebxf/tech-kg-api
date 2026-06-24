import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-24 10:00:00',
  structuredResult: {
    coreNode: '张明远',
    hopCount: 2,
    pathSummary: '张明远 → 李佳宁 → 王子涵',
    relationStrength: 0.82,
    intermediateNodes: ['李佳宁'],
    targetNode: '王子涵',
    relationTypes: ['论文合作', '项目合作'],
  },
  apiExample: {
    status: 'success',
    coreExpertId: 'EXP001',
    hop: 2,
    paths: [{ nodes: ['EXP001', 'EXP002', 'EXP003'], strength: 0.82 }],
  },
  apiPath: '/api/v1/kg-construction/expert-indirect-relations',
  httpMethod: 'GET',
  requestFields: [
    { name: 'coreExpertId', type: 'string', required: '是', description: '核心专家 ID' },
    { name: 'maxHop', type: 'int', required: '否', description: '最大跳数，默认 2' },
    { name: 'dataSource', type: 'string', required: '否', description: '数据来源' },
  ],
  responseFields: [
    { name: 'status', type: 'string', description: '状态' },
    { name: 'paths', type: 'array', description: '间接关系路径列表' },
    { name: 'paths[].strength', type: 'number', description: '路径强度' },
  ],
  codeExamples: {
    python: '',
    node: '',
    curl: '',
  },
}

export default payload
