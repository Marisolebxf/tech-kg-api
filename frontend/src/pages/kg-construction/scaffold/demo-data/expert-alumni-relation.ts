import type { ScaffoldDemoPayload } from '../../../../types/kg-module'

const payload: ScaffoldDemoPayload = {
  lastTestTime: '2026-06-12 10:16:32',
  structuredResult: {
    专家A: '周子谦（研究员）',
    专家B: '吴若彤（副研究员）',
    关系类型: '校友关系',
    共同院校: '中国科学院大学',
    共同院系: '计算机科学与技术学院',
    共同专业: '人工智能',
    共同学习时段: '2015.09 - 2019.06',
    后续合作: '论文 3 / 专利 1 / 项目 2',
  },
  apiExample: {
    from: '周子谦',
    to: '吴若彤',
    organization: '中国科学院大学',
    relationType: '校友关系',
    alumniType: '同校同院系同专业校友',
    degreeLevel: '博士',
    confidence: 0.92,
    evidence: [
      { field: '共同院校', value: '中国科学院大学', weight: 0.35 },
      { field: '共同院系', value: '计算机科学与技术学院', weight: 0.25 },
      { field: '共同专业', value: '人工智能', weight: 0.2 },
      { field: '共同学习时段', value: '2015.09 - 2019.06', weight: 0.22 },
    ],
  },
  apiPath: '/api/v1/kg-construction/expert-alumni-relations',
  httpMethod: 'GET',
  requestFields: [
    { name: 'dataSource', type: 'string', required: '是', description: '数据来源' },
    { name: 'expertAId', type: 'string', required: '是', description: '专家 A ID' },
    { name: 'expertBId', type: 'string', required: '是', description: '专家 B ID' },
    { name: 'relationType', type: 'string', required: '是', description: '校友类型' },
    { name: 'degreeLevel', type: 'string', required: '是', description: '学历层次' },
    { name: 'timeRange', type: 'string', required: '否', description: '时间范围' },
  ],
  responseFields: [
    { name: 'from', type: 'string', description: '专家 A' },
    { name: 'to', type: 'string', description: '专家 B' },
    { name: 'organization', type: 'string', description: '共同院校' },
    { name: 'relationType', type: 'string', description: '关系类型' },
    { name: 'confidence', type: 'number', description: '置信度' },
    { name: 'evidence', type: 'array', description: '判定依据' },
  ],
  codeExamples: { python: '', node: '', curl: '' },
  graphLayout: {
    relationPill: { text: '校友关系', x: 50, y: 22 },
    edges: [
      { path: 'M 22 18 C 35 18, 38 22, 46 24', className: 'purple' },
      { path: 'M 78 18 C 65 18, 62 22, 54 24', className: 'purple' },
      { path: 'M 18 28 C 22 38, 28 42, 34 48', className: 'blue' },
      { path: 'M 82 28 C 78 38, 72 42, 66 48', className: 'blue' },
      { path: 'M 34 58 C 42 62, 46 66, 50 70', className: 'green' },
      { path: 'M 66 58 C 58 62, 54 66, 50 70', className: 'green' },
      { path: 'M 50 78 C 50 82, 50 86, 50 88', className: 'dashed' },
    ],
    nodes: [
      { id: 'expertA', kind: 'expertA', title: '专家A：周子谦', subtitle: '研究员', x: 4, y: 8, w: 28, h: 14 },
      { id: 'expertB', kind: 'expertB', title: '专家B：吴若彤', subtitle: '副研究员', x: 68, y: 8, w: 28, h: 14 },
      { id: 'institution', kind: 'institution', title: '共同院校', subtitle: '中国科学院大学', x: 30, y: 38, w: 40, h: 12 },
      { id: 'department', kind: 'department', title: '共同院系', subtitle: '计算机科学与技术学院', x: 8, y: 56, w: 38, h: 12 },
      { id: 'major', kind: 'major', title: '共同专业', subtitle: '人工智能', x: 54, y: 56, w: 38, h: 12 },
      { id: 'period', kind: 'period', title: '共同学习时段', subtitle: '2015.09 - 2019.06', x: 28, y: 74, w: 44, h: 11 },
      { id: 'cooperation', kind: 'cooperation', title: '后续合作', subtitle: '论文3 / 专利1 / 项目2', x: 62, y: 74, w: 34, h: 11 },
    ],
  },
}

export default payload
