import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-24 10:10:00',
  structuredResult: {
    expertA: '张明远',
    expertB: '周欣怡',
    sharedInstitution: '中国科学院自动化研究所',
    overlapYears: '2015-2020',
    colleagueType: '同单位同事',
    evidence: ['共同任职', '联合项目 2 项'],
  },
  apiExample: {
    status: 'success',
    relationType: 'colleague',
    institution: '中国科学院自动化研究所',
    overlap: { start: '2015-01-01', end: '2020-12-31' },
  },
  apiPath: '/api/v1/kg-construction/expert-colleague-relations',
  httpMethod: 'GET',
  requestFields: [
    { name: 'expertAId', type: 'string', required: '是', description: '专家 A ID' },
    { name: 'expertBId', type: 'string', required: '是', description: '专家 B ID' },
  ],
  responseFields: [
    { name: 'colleagueType', type: 'string', description: '同事关系类型' },
    { name: 'sharedInstitution', type: 'string', description: '共同机构' },
  ],
  codeExamples: { python: '', node: '', curl: '' },
}

export default payload
