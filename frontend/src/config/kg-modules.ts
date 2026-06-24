import type { KgModuleConfig } from '../types/kg-module'

export const KG_MODULES: KgModuleConfig[] = [
  {
    code: 'expert-direct-relation',
    navLabel: '科技专家直接关系',
    routeName: 'ExpertDirectRelation',
    path: '/kg/expert-direct-relation',
    mode: 'live',
    reservedApiPath: '/api/v1/binding/expert-direct-relation',
    subFunctions: ['科技专家直接关系构建', '两跳关系构建', '三跳关系构建'],
    schemeDescription:
      '基于专家论文、专利、项目等事实数据，识别两位科技专家之间的直接关系类型、合作次数、时间范围与判定依据。',
    schemeFlow: ['输入专家参数', '事实归并', '关系判定', '输出 DIRECT_REL 结构化结果'],
  },
  {
    code: 'expert-indirect-relation',
    navLabel: '科技节点间接关系',
    routeName: 'ExpertIndirectRelation',
    path: '/kg/expert-indirect-relation',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/expert-indirect-relations',
    subFunctions: ['科技节点间接关系构建'],
    schemeDescription: '以单个专家为核心节点，推理多跳间接关系路径与关联强度。',
    schemeFlow: ['输入核心节点', '路径搜索', '强度评分', '输出 INDIRECT_REL'],
  },
  {
    code: 'expert-cooperation-achievement',
    navLabel: '科技两点合作成果',
    routeName: 'ExpertCooperationAchievement',
    path: '/kg/expert-cooperation-achievement',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/expert-cooperation-achievements',
    subFunctions: ['科技两点合作成果构建'],
    schemeDescription: '汇总两位专家之间的论文、专利、项目等合作成果清单。',
    schemeFlow: ['输入双节点', '成果聚合', '模式识别', '输出 PAIR_COOP_SUMMARY'],
  },
  {
    code: 'expert-colleague-relation',
    navLabel: '科技专家同事关系',
    routeName: 'ExpertColleagueRelation',
    path: '/kg/expert-colleague-relation',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/expert-colleague-relations',
    subFunctions: ['科技专家同事关系构建'],
    schemeDescription: '基于任职单位与时间重叠识别专家同事关系。',
    schemeFlow: ['任职事实对齐', '时间重叠计算', '同事判定', '输出 COLLEAGUE_REL'],
  },
  {
    code: 'expert-alumni-relation',
    navLabel: '科技专家校友关系',
    routeName: 'ExpertAlumniRelation',
    path: '/kg/expert-alumni-relation',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/expert-alumni-relations',
    subFunctions: ['科技专家校友关系构建'],
    schemeDescription: '基于教育经历识别专家校友、院友关系及培养层次。',
    schemeFlow: ['教育事实抽取', '院校匹配', '校友判定', '输出 ALUMNI_REL'],
  },
  {
    code: 'expert-paper-cooperation',
    navLabel: '专家论文合作关系',
    routeName: 'ExpertPaperCooperation',
    path: '/kg/expert-paper-cooperation',
    mode: 'live',
    reservedApiPath: '/api/v1/scholar-paper-cooperation/demo/structured-result',
    subFunctions: ['专家论文合作关系构建'],
    schemeDescription:
      '基于科技专家发表论文的作者列表、作者单位、合作发表时间、论文主题与被引数据，构建论文合作关系网络。',
    schemeFlow: ['输入双专家', '作者关联', '合作频次统计', '输出 PAPER_COOP_REL'],
  },
  {
    code: 'expert-enterprise-relation',
    navLabel: '重点科技企业关系',
    routeName: 'ExpertEnterpriseRelation',
    path: '/kg/expert-enterprise-relation',
    mode: 'live',
    reservedApiPath: '/api/v1/kg-construction/expert-enterprise-relations/build',
    subFunctions: ['专家-企业关系构建', '角色与合作详情标注', '企业背景关联分析'],
    schemeDescription: '围绕专家构建其与重点科技企业之间的任职、合作与技术关联关系。',
    schemeFlow: ['输入专家与企业', '关系写入 TRSGraph', '企业去重汇总', '输出 EXPERT_ENTERPRISE_REL'],
  },
  {
    code: 'industry-chain-topn-event',
    navLabel: '产业链点事件关系',
    routeName: 'IndustryChainTopnEvent',
    path: '/kg/industry-chain-topn-event',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/industry-chain-topn-event-relations',
    subFunctions: ['产业链点TOP-N事件关系构建'],
    schemeDescription: '针对产业链节点筛选核心事件并关联专家、团队与产业环节。',
    schemeFlow: ['事件筛选', 'TOP-N 排序', '关联推理', '输出 EVENT_EXPERT_REL'],
  },
  {
    code: 'industry-chain-panorama',
    navLabel: '科技产业链全景图',
    routeName: 'IndustryChainPanorama',
    path: '/kg/industry-chain-panorama',
    mode: 'scaffold',
    reservedApiPath: '/api/v1/kg-construction/industry-chain-panorama',
    subFunctions: ['科技产业链全景图构建'],
    schemeDescription: '整合产业链环节、企业、技术与资本要素，支撑全景展示与钻取分析。',
    schemeFlow: ['环节骨架构建', '要素挂载', '价值流向计算', '输出全景图数据'],
  },
]

export function getModuleByRouteName(routeName: string): KgModuleConfig | undefined {
  return KG_MODULES.find((item) => item.routeName === routeName)
}

export function getModuleByCode(code: string): KgModuleConfig | undefined {
  return KG_MODULES.find((item) => item.code === code)
}
