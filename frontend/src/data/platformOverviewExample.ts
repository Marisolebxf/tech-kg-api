import type { PlatformOverviewData } from '../api/platformOverview'

const example: PlatformOverviewData = {
  platformStatus: '平台运行正常',
  pendingBatchCount: 2,
  updatedAt: '2026-08-23 10:30',
  dataMode: 'mock',
  dataSources: { graphAssets: 'example', todayChanges: 'example', managementRisks: 'example' },
  warnings: [],
  assetOverviewGroups: [
    { key: 'entity', title: '实体数据', total: '1.28 亿', totalLabel: '实体总量', added: '+1,183.6 万', addedLabel: '今日新增' },
    { key: 'relation', title: '关系数据', total: '6.42 亿', totalLabel: '关系总量', added: '+2,040 万', addedLabel: '今日新增' },
    { key: 'property', title: '属性值数据', total: '18.76 亿', totalLabel: '属性值总量', added: '+3,264 万', addedLabel: '今日新增及更新' },
  ],
  assetChangeRows: {
    entity: [
      { type: '专家', object: '周启航', change: '新增专家实体', source: 'expert_profile', time: '10:30:18' },
      { type: '机构/企业', object: '华南智能芯片有限公司', change: '新增企业实体', source: 'enterprise_profile', time: '10:30:13' },
    ],
    relation: [
      { type: '任职关系', object: '周启航 → 中国科学院自动化研究所', change: '新增任职关系', source: 'expert_employment', time: '10:30:22' },
      { type: '成果关系', object: '周启航 → 多模态大模型知识推理方法研究', change: '新增发表关系', source: 'paper_author', time: '10:30:25' },
    ],
    property: [
      { type: '企业属性', object: '华南智能芯片·注册资本', change: '新增注册资本', source: 'enterprise_profile', time: '10:30:14' },
      { type: '论文属性', object: 'P202607140018·发表时间', change: '新增发表时间', source: 'paper_record', time: '10:30:23' },
    ],
  },
  latestChanges: [
    { time: '10:30', type: '更新', domain: '机构域', title: '清华大学机构属性更新完成', detail: '机构简称与统一标识已完成标准化更新', impact: '影响 1 条机构记录', to: '/graph-query' },
    { time: '10:18', type: '对齐', domain: '人才域', title: '陈卓候选专家实体完成对齐', detail: '机构别名经确认后，候选实体已合并至标准专家实体', impact: '影响 3 条关系记录', to: '/graph-query' },
    { time: '10:13', type: '新增', domain: '人才域', title: '张明远标准专家实体更新完成', detail: '完成来源读取、实体标准化与图谱更新', impact: '影响 1 个专家实体', to: '/graph-query' },
  ],
  managementRisks: [
    { title: '3 条人工修正等待审核', detail: '专家、机构/企业和专家任职关系各 1 条', detailTo: '/admin/corrections', reviewTo: '/admin/reviews' },
    { title: '1 条修正记录同步失败', detail: '已进入自动重试队列，可在详情中手动重试', detailTo: '/admin/corrections', reviewTo: '/admin/corrections' },
  ],
  entityStructure: [
    { label: '专家/人才', schema: 'Expert', count: '4,286 万', ratio: 34, tone: '#2e90fa' },
    { label: '论文成果', schema: 'Paper', count: '2,931 万', ratio: 23, tone: '#7a5af8' },
    { label: '机构/企业', schema: 'Organization', count: '2,164 万', ratio: 17, tone: '#067647' },
    { label: '项目/专利', schema: 'Project / Patent', count: '1,438 万', ratio: 11, tone: '#f79009' },
    { label: '其他实体', schema: 'Event / Product / Field', count: '1,901 万', ratio: 15, tone: '#59636f' },
  ],
  relationStructure: [
    { label: '发表/引用/成果', schema: 'PUBLISH / CITES / OUTPUT', count: '2.04 亿', ratio: 32, tone: '#004ecc' },
    { label: '任职/就读/作者单位', schema: 'WORKS_AT / STUDY_AT', count: '1.28 亿', ratio: 20, tone: '#2e90fa' },
    { label: '项目/专利参与', schema: 'LEAD_PROJECT / INVENT_PATENT', count: '1.16 亿', ratio: 18, tone: '#06aed4' },
    { label: '企业/产品/事件', schema: 'HAS_PRODUCT / HAS_EVENT', count: '0.92 亿', ratio: 14, tone: '#7a5af8' },
    { label: '其他关系', schema: '产业链 / 推理关系', count: '1.02 亿', ratio: 16, tone: '#59636f' },
  ],
}

export function getExamplePlatformOverview(): PlatformOverviewData {
  return structuredClone(example)
}
