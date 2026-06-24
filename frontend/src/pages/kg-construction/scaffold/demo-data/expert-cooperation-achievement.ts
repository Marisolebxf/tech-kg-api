import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-24 10:05:00',
  structuredResult: {
    expertA: '张明远',
    expertB: '李佳宁',
    paperCount: 6,
    patentCount: 2,
    projectCount: 1,
    representativeAchievements: ['深度学习图像识别', '多模态融合专利'],
    cooperationTimeRange: { displayText: '2019-2024' },
  },
  apiExample: {
    status: 'success',
    expertAId: 'EXP001',
    expertBId: 'EXP002',
    achievements: { papers: 6, patents: 2, projects: 1 },
  },
  apiPath: '/api/v1/kg-construction/expert-cooperation-achievements',
  httpMethod: 'GET',
  requestFields: [
    { name: 'expertAId', type: 'string', required: '是', description: '专家 A ID' },
    { name: 'expertBId', type: 'string', required: '是', description: '专家 B ID' },
  ],
  responseFields: [
    { name: 'achievements', type: 'object', description: '合作成果汇总' },
    { name: 'representativeItems', type: 'array', description: '代表性成果' },
  ],
  codeExamples: { python: '', node: '', curl: '' },
}

export default payload
