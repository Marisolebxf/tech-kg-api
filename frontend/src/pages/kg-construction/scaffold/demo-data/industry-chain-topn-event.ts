import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-24 10:20:00',
  structuredResult: {
    chainNode: '核心零部件',
    topEvents: ['供应中断', '产能扩张', '技术替代'],
    linkedExperts: ['张明远', '李佳宁'],
    eventCount: 3,
    riskLevel: '中',
  },
  apiExample: {
    status: 'success',
    chainNodeId: 'NODE-001',
    events: [
      { name: '供应中断', score: 0.91 },
      { name: '产能扩张', score: 0.76 },
    ],
  },
  apiPath: '/api/v1/kg-construction/industry-chain-topn-event-relations',
  httpMethod: 'GET',
  requestFields: [
    { name: 'chainNodeId', type: 'string', required: '是', description: '产业链节点 ID' },
    { name: 'topN', type: 'int', required: '否', description: 'TOP-N 数量' },
  ],
  responseFields: [
    { name: 'events', type: 'array', description: 'TOP-N 事件列表' },
    { name: 'linkedExperts', type: 'array', description: '关联专家' },
  ],
  codeExamples: { python: '', node: '', curl: '' },
}

export default payload
