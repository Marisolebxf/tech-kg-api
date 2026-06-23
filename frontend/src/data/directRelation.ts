import type { RelationModeOption, RelationScenario, SidebarItem } from '../types/directRelation'

export const sidebarItems: SidebarItem[] = [
  { label: '流程编排' },
  { label: '图谱服务' },
  { label: '知识推理服务', active: true },
  { label: '科技专家直接关系', active: true },
  { label: '科技热点连接关系' },
  { label: '科技两点合作成果' },
  { label: '科技专家校友关系' },
  { label: '科技专家论文合作关系' },
  { label: '专家论文合作关系' },
  { label: '重点科技企业关系' },
  { label: '产业链点事件关系' },
  { label: '科技产业链全景图' },
]

export const relationModes: RelationModeOption[] = [
  {
    key: 'two_hop',
    label: '专家直接关系推理（两跳）',
    subtitle: '直接关系为主，优先展示低复杂度场景',
    path: '/api/v1/binding/expert-direct-two-hop',
  },
  {
    key: 'three_hop',
    label: '专家直接关系推理（三跳）',
    subtitle: '覆盖更完整的关系证据链与组合场景',
    path: '/api/v1/binding/expert-direct-three-hop',
  },
]

export const apiRequestRows: Array<[string, string, string, string]> = [
  ['dataSource', 'string', '否', '数据来源：all / graph / fallback'],
  ['expertAId', 'string', '否', '专家A姓名或ID'],
  ['expertBId', 'string', '否', '专家B姓名或ID'],
  ['institution', 'string', '否', '机构名称关键词'],
  ['relationType', 'string', '否', 'two_hop / three_hop'],
  ['startTime', 'string', '否', '开始日期，格式 YYYY-MM-DD'],
  ['endTime', 'string', '否', '结束日期，格式 YYYY-MM-DD'],
]

export const apiResponseRows: Array<[string, string, string]> = [
  ['scenarios', 'array', '结构化人物关系列表'],
  ['scenarios[].key', 'string', '关系结果唯一标识'],
  ['scenarios[].label', 'string', '人物关系展示标题'],
  ['scenarios[].last_test_time', 'string', '最近测试时间'],
  ['scenarios[].detail_rows', 'array', '结构化人物关系详情行'],
  ['detail_rows[].0', 'string', '字段名，如专家A、专家B、关系类型'],
  ['detail_rows[].1', 'string / array', '字段值或判定依据标签'],
]

export const fallbackRelationPreview: RelationScenario[] = [
  {
    key: 'expert-fallback-01',
    label: '科技专家关系（张明远 / 李佳宁）',
    last_test_time: '2026-07-23 11:00:00',
    graph: {
      width: 860,
      height: 640,
      nodes: [
        { id: 'fallback_zhangmingyuan', kind: 'expertA', x: 90, y: 140, icon: '👤', title: '专家A：张明远', subtitle: '研究员', chips: ['知识图谱', '机器学习'] },
        { id: 'fallback_lijianing', kind: 'expertB', x: 550, y: 140, icon: '👤', title: '专家B：李佳宁', subtitle: '副研究员', chips: ['智能决策', '知识工程'] },
        { id: 'institution-中国科学院自动化研究所', kind: 'institution', x: 270, y: 340, icon: '🏛', title: '直接关系', subtitle: '中国科学院自动化研究所' },
      ],
      edges: [
        { type: 'curve', from_: [276, 196], to: [550, 196], stroke: '#a355ec', marker: '#a355ec', width: 4, label: '直接关系', label_x: 398, label_y: 178, label_color: '#8f52db' },
        { type: 'curve', from_: [220, 240], c1: [250, 290], c2: [330, 335], to: [402, 392], stroke: '#6ca2ff', marker: '#6ca2ff', width: 4, label: '直连', label_x: 275, label_y: 320, label_color: '#6b8fd6' },
        { type: 'curve', from_: [640, 240], c1: [620, 290], c2: [540, 335], to: [458, 392], stroke: '#6ca2ff', marker: '#6ca2ff', width: 4, label: '直连', label_x: 555, label_y: 320, label_color: '#6b8fd6' },
      ],
    },
    detail_rows: [
      ['专家 A', '张明远'],
      ['专家 A 职称', '研究员'],
      ['专家 B', '李佳宁'],
      ['专家 B 职称', '副研究员'],
      ['关系类型', '科技专家直接关系 / 直接关系'],
      ['直接关系', '中国科学院自动化研究所'],
      ['判定依据', ['同机构', '共论文']],
      ['关系强度', 82],
      ['关系摘要', '同机构 + 共论文'],
    ],
    api_example: {
      relation_type: 'expert_direct_relation',
      relation_subtype: 'direct',
      expert_a: { name: '张明远', title: '研究员' },
      expert_b: { name: '李佳宁', title: '副研究员' },
      institution: '中国科学院自动化研究所',
      reasons: ['同机构', '共论文'],
      relation_strength: 82,
      relation_summary: '同机构 + 共论文',
      request_example: {
        dataSource: 'all',
        expertAId: '张明远',
        expertBId: '李佳宁',
        institution: '中国科学院自动化研究所',
        relationType: 'two_hop',
        startTime: '2026-01-01',
        endTime: '2026-12-31',
      },
      response_example: {
        data: {
          scenarios: [],
        },
      },
    },
  },
]
