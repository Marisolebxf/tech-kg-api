import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-24 10:25:00',
  structuredResult: {
    panoramaName: '人工智能产业链全景',
    upstreamCount: 12,
    midstreamCount: 28,
    downstreamCount: 45,
    keyEnterprises: ['华为', '百度', '商汤科技'],
    valueFlowSummary: '算力 → 算法 → 应用场景',
  },
  apiExample: {
    status: 'success',
    industry: 'artificial_intelligence',
    segments: { upstream: 12, midstream: 28, downstream: 45 },
    keyEnterprises: ['ENT-HW', 'ENT-BD', 'ENT-ST'],
  },
  apiPath: '/api/v1/kg-construction/industry-chain-panorama',
  httpMethod: 'GET',
  requestFields: [
    { name: 'industryCode', type: 'string', required: '是', description: '产业编码' },
    { name: 'depth', type: 'int', required: '否', description: '钻取深度' },
  ],
  responseFields: [
    { name: 'segments', type: 'object', description: '上中下游环节统计' },
    { name: 'keyEnterprises', type: 'array', description: '关键企业' },
  ],
  codeExamples: { python: '', node: '', curl: '' },
}

export default payload
