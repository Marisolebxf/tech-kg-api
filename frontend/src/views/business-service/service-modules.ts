import { actualServiceRules } from './actual-service-rules'

export type ServiceField = {
  name: string
  /** 表单展示名；缺省时用 name。用于消除接口字段名在界面上的歧义。 */
  label?: string
  type: string
  /** 表单控件类型；缺省时按 type 渲染。'month-calendar' = 日历式年月下拉。 */
  ui?: 'month-calendar'
  required?: string
  /** 输入框占位提示：用中文解释这个字段是什么，并给一个可直接使用的测试值。缺省时退回 description。 */
  placeholder?: string
  description: string
  options?: readonly string[]
  maxLength?: number
  /** 表单初始值；缺省时为空字符串。用于固定值（dataSource="all"）或带默认值的字段（limit=10）。 */
  defaultValue?: string
}

export type ServiceResultRow = {
  label: string
  value: string
  tone?: 'blue' | 'green' | 'orange' | 'purple' | 'red'
}

export type ServiceSummaryRow = {
  label: string
  value: string
}

export type ServiceRule = {
  name: string
  type: string
  target: string
  trigger: string
  logic: string
  output: string
  threshold: string
  audit: string
}

export type ServiceModule = {
  key: string
  title: string
  subtitle: string
  endpoint: string
  method: 'POST'
  moduleRequirement: string
  requestFields: ServiceField[]
  responseFields: ServiceField[]
  requestExample: Record<string, string | number | boolean | string[]>
  /** 为 false 时参数表单初始为空，requestExample 只作为接口文档示例，不回填表单。 */
  prefillFormFromExample?: boolean
  responseExample: Record<string, unknown>
  resultRows: ServiceResultRow[]
  summaryRows: ServiceSummaryRow[]
  evidence: string[]
  rules: ServiceRule[]
}

const commonResponseFields: ServiceField[] = [
  { name: 'code', type: 'number', description: '服务状态码' },
  { name: 'message', type: 'string', description: '服务返回信息' },
  { name: 'data', type: 'object', description: '结构化业务结果、图谱节点关系和证据链' },
  { name: 'confidence', type: 'number', description: '综合置信度' },
  { name: 'evidence', type: 'array', description: '支撑本次结果的数据来源和证据' },
]

const expertColleagueResponseFields: ServiceField[] = [
  { name: 'code', type: 'number', description: '服务状态码，成功时为 200/0' },
  { name: 'success', type: 'boolean', description: '服务是否成功' },
  { name: 'msg', type: 'string', description: '服务返回信息' },
  { name: 'data.expert', type: 'object', description: '核心专家实体详情，含 confidence、details、provenance' },
  { name: 'data.colleagues', type: 'array', description: '同事关系列表，含生效时段、团队、共同工作内容、成果、confidence、evidence' },
  { name: 'data.graph.nodes', type: 'array', description: '图谱展示节点，node.data 为真实实体详情和溯源字段' },
  { name: 'data.graph.edges', type: 'array', description: '图谱展示关系边，edge.data 含关系 confidence、evidence、ruleName' },
  { name: 'data.rules', type: 'array', description: '本接口实际使用的任职时间、团队归属、成果关联规则' },
  { name: 'data.apiCalls', type: 'array', description: '后端组合调用查图 API 的路径、参数和结果摘要' },
]

export const serviceModules: ServiceModule[] = [
  {
    key: 'expert-direct',
    title: '科技专家/人才直接关系',
    subtitle: '识别专家之间的直接关联类型、时间、场景和成果。',
    endpoint: '/api/v1/kg-construction/expert-direct-relations/query',
    method: 'POST',
    moduleRequirement: '科技专家 / 人才直接关系服务通过收集科技专家或人才在各类场景中的直接交互数据，结合知识图谱中已有的实体属性与关系信息，运用语义匹配与关系验证算法，识别并构建专家或人才之间的直接关联。该服务会对直接关系的类型进行精准分类，同时记录关系发生的时间、场景及相关成果，形成结构化的直接关系数据，为后续的关系分析与网络构建提供基础。',
    requestFields: [
      { name: 'dataSource', type: 'select', options: ['all'], defaultValue: 'all', required: '否', description: '数据来源，固定为 all' },
      { name: 'expertAId', type: 'string', required: '是', placeholder: '请输入专家A，如 person_4G7t0B0t', description: '起点专家 scholar_id / VID / 姓名，必填，最多 64 个字符，不能包含空格或 !@#￥%& 等异常字符' },
      { name: 'expertBId', type: 'string', required: '否', placeholder: '选填，专家B，如 person_CE4825106', description: '另一位专家 scholar_id / VID / 姓名，最多 64 个字符；留空则返回专家A的全部直接关系' },
      { name: 'institution', type: 'string', required: '否', placeholder: '选填，机构关键词，如 新加坡国立大学', description: '机构关键词，任一端命中即保留，最多 64 个字符，不能包含 !@#￥%& 等异常字符' },
      { name: 'startTime', type: 'month', ui: 'month-calendar', required: '否', placeholder: '选填，选择年月，如 2020-01', description: '筛选条件：只保留关系建立时间不早于该年月的直接关系，不能晚于当前月份；留空表示不限时间' },
      { name: 'endTime', type: 'month', ui: 'month-calendar', required: '否', placeholder: '选填，选择年月，如 2020-12', description: '筛选条件：只保留关系建立时间不晚于该年月的直接关系，不能晚于当前月份；留空表示不限时间' },
      { name: 'limit', type: 'number', defaultValue: '10', required: '否', placeholder: '选填，1-100，默认 10', description: '返回结果数，1-100，默认 10；超出 100 会被后端 clamp 到 100' },
    ],
    responseFields: commonResponseFields,
    requestExample: { dataSource: 'all', expertAId: '007Rb117', expertBId: '00867K10', institution: '', startTime: '', endTime: '', limit: 3 },
    prefillFormFromExample: false,
    responseExample: { code: 0, message: 'success', data: { relation_type: '论文合作', relation_count: 12, scenario: '科研合作', confidence: 0.94 } },
    resultRows: [
      { label: '直接关系', value: '12', tone: 'blue' },
      { label: '关系类型', value: '4', tone: 'green' },
      { label: '相关成果', value: '18', tone: 'orange' },
      { label: '最高置信度', value: '0.94', tone: 'purple' },
    ],
    summaryRows: [
      { label: '专家 A', value: '张明远｜研究员｜清华大学' },
      { label: '专家 B', value: '李佳宁｜副研究员｜清华大学' },
      { label: '直接关系类型', value: '论文合作、项目合作、同事协作、成果转化' },
      { label: '关系发生时间', value: '2020-01 至今' },
      { label: '交互场景', value: '科研合作、联合项目、学术交流' },
      { label: '关系数量', value: '12 条' },
      { label: '相关成果', value: '共同论文 8 篇、联合项目 3 项、授权专利 2 件' },
      { label: '代表成果', value: '科技知识图谱关系推理方法、科研合作网络分析系统' },
      { label: '关系置信度', value: '0.94' },
    ],
    evidence: ['共同发表论文 4 篇，作者列表和单位信息一致。', '共同参与项目 3 项，项目角色存在协作链路。', '关系发生时间、场景和成果均已结构化记录。'],
    rules: actualServiceRules['expert-direct'],
  },
  {
    key: 'node-indirect',
    title: '科技单节点间接关系',
    subtitle: '从直接关系和多跳路径中推理潜在关联。',
    endpoint: '/api/v1/kg-construction/expert-indirect-relations/demo/structured-result',
    method: 'POST',
    moduleRequirement: '科技单节点间接关系服务以单个科技专家或人才作为核心节点，通过挖掘知识图谱中与该节点存在间接关联的其他节点，运用路径分析与关系传递算法，推理出核心节点与间接节点之间的潜在关联。服务会梳理间接关系的传递路径，计算间接关系的关联强度，并对不同类型的间接关系进行标注，帮助用户全面了解单个科技专家或人才的间接社交网络与资源关联。',
    requestFields: [
      { name: 'core_node_id', type: 'string', required: '是', maxLength: 64, description: '核心专家或人才节点 ID，最多 64 个字符' },
      {
        name: 'relation_types',
        type: 'select',
        required: '是',
        description: '间接关系类型（单选）',
        options: ['学术关联', '机构关联', '项目关联'],
      },
      { name: 'path_depth', type: 'number', required: '否', placeholder: '默认 2，可选 2 或 3', description: '路径分析深度，默认 2 跳，可选 2 或 3 跳' },
      { name: 'min_strength', type: 'number', required: '否', description: '最小关联强度阈值（0-1）' },
    ],
    responseFields: commonResponseFields,
    requestExample: { core_node_id: '4G7t0B0t', min_strength: 0.65, path_depth: 2, relation_types: ['学术关联'] },
    responseExample: { structuredResult: { indirectNodeCount: 0, pathCount: 0, relationTypeCount: {}, averageStrength: 0 } },
    resultRows: [
      { label: '间接节点', value: '36', tone: 'blue' },
      { label: '路径数量', value: '58', tone: 'green' },
      { label: '关系类型', value: '4', tone: 'orange' },
      { label: '关联强度', value: '0.76', tone: 'purple' },
    ],
    summaryRows: [
      { label: '核心节点', value: '张明远｜科技专家' },
      { label: '路径分析深度', value: '2 跳' },
      { label: '直接关联节点', value: '李佳宁、清华大学、智能科研协同平台项目' },
      { label: '间接关联节点', value: '专家陈思远、华南智能芯片、知识工程实验室等 36 个' },
      { label: '间接关系类型', value: '学术关联、项目关联、专利关联、机构关联' },
      { label: '代表传递路径', value: '张明远 → 李佳宁 → 陈思远' },
      { label: '项目关联路径', value: '张明远 → 智能科研协同平台项目 → 华南智能芯片' },
      { label: '路径数量', value: '58 条' },
      { label: '关联强度', value: '最高 0.89｜平均 0.76｜阈值 0.65' },
    ],
    evidence: ['路径：张明远 -> 李佳宁 -> 专家C。', '路径深度为 2，命中学术关联和机构关联。', '每条间接关系均返回传递路径和强度。'],
    rules: actualServiceRules['node-indirect'],
  },
  {
    key: 'two-point-achievement',
    title: '科技两点合作成果',
    subtitle: '汇总两个专家之间的论文、项目、专利和奖项成果。',
    endpoint: '/api/v1/kg-construction/expert-cooperation-achievements/query',
    method: 'POST',
    moduleRequirement: '科技两点合作成果服务针对两个科技专家或人才节点，通过整合知识图谱中与这两个节点相关的合作数据，运用成果关联与归因算法，提取并汇总两者的合作成果信息。服务会对合作成果进行分类统计，标注成果的发表或完成时间、所属领域、获得的奖项或评价，同时分析合作成果的核心贡献与合作模式，为评估两点之间的合作深度与合作价值提供数据支持。',
    requestFields: [
      { name: 'sourceExpertId', type: 'string', required: '是', description: '请输入第一个专家，如 person_9F9A0001' },
      { name: 'targetExpertId', type: 'string', required: '是', description: '请输入第二个专家，如 person_9F9A0002' },
      { name: 'achievementTypes', type: 'multi-select', required: '否', description: '成果类型多选：全部 / 论文 / 专利 / 项目，留空返回全部' },
      { name: 'timeRangeStart', type: 'month', required: '否', description: '成果开始月份 YYYY-MM，留空不限' },
      { name: 'timeRangeEnd', type: 'month', required: '否', description: '成果结束月份 YYYY-MM，留空不限' },
      { name: 'limitPerType', type: 'number', defaultValue: '20', required: '否', placeholder: '选填，1-50，默认 20', description: '每类成果返回数上限，1-50，默认 20' },
    ],
    responseFields: commonResponseFields,
    requestExample: {
      sourceExpertId: 'person_9F9A0001',
      targetExpertId: 'person_9F9A0004',
      achievementTypes: ['paper', 'patent', 'project'],
      timeRangeStart: '2020-01-01',
      timeRangeEnd: '2024-12-31',
      limitPerType: 20,
    },
    responseExample: {
      code: 200,
      success: true,
      msg: 'success',
      data: {
        summary: { papers: 1, patents: 0, projects: 0, awards: 0 },
        coreContribution: '共同论文产出',
        cooperationMode: '单类型合作（论文）',
        sourceMeta: { space: 'dev' },
      },
    },
    resultRows: [
      { label: '合作论文', value: '', tone: 'blue' },
      { label: '合作专利', value: '', tone: 'green' },
      { label: '共同项目', value: '', tone: 'orange' },
      { label: '获奖成果', value: '', tone: 'red' },
    ],
    summaryRows: [
      { label: '专家 A', value: '' },
      { label: '专家 B', value: '' },
      { label: '合作成果类型', value: '' },
      { label: '成果总量', value: '' },
      { label: '成果分布', value: '' },
      { label: '成果1', value: '论文/专利/项目名称' },
      { label: '完成时间', value: '' },
      { label: '所属领域', value: '' },
      { label: '奖项/评价', value: '' },
      { label: '核心贡献', value: '' },
      { label: '合作模式', value: '' },
      { label: '图空间', value: '' },
    ],
    evidence: [
      '按论文、专利、项目邻居求交汇总共同成果。',
      '摘要按成果序号展示名称，并标注完成时间、所属领域、奖项/评价。',
      '所属领域取自成果 HAS_KEYWORD 关键词（专利可回退节点 keywords）。',
      '规则归因核心贡献与合作模式。',
    ],
    rules: actualServiceRules['two-point-achievement'],
  },
  {
    key: 'expert-colleague',
    title: '科技专家同事关系',
    subtitle: '根据工作经历、机构架构和任职时间推理同事关系。',
    endpoint: '/api/v1/kg-service/expert-colleague-relation',
    method: 'POST',
    moduleRequirement: '科技专家同事关系服务通过提取科技专家在不同时期的工作单位、所属部门、参与团队等机构信息，结合知识图谱中的机构架构与人员任职数据，运用任职时间匹配与团队归属算法，推理并构建专家之间的同事关系。服务会判断同事关系的生效时段、所属团队或项目组，标注同事关系期间的共同工作内容与协作场景，同时关联两者在同事期间产生的合作成果，帮助用户了解科技专家的职业社交圈与工作协作历史。',
    requestFields: [
      { name: 'expert_a_id', type: 'string', required: '是', maxLength: 64, description: '请输入专家 A，最多 64 个字符' },
      { name: 'expert_b_id', type: 'string', required: '是', maxLength: 64, description: '请输入专家 B，最多 64 个字符' },
      { name: 'start_time', type: 'month', required: '否', description: '可选；留空则使用数据库任职开始时间' },
      { name: 'end_time', type: 'month', required: '否', description: '可选；留空则使用数据库任职结束时间' },
    ],
    responseFields: expertColleagueResponseFields,
    // 测试数据不再作为表单默认值，避免用户误提交样例专家。
    requestExample: { expert_a_id: 'person_0512632S', expert_b_id: 'person_2406B66w', start_time: '2020-01', end_time: '2024-12' },
    responseExample: { code: 200, success: true, msg: 'success', data: { total: 1, summary: { commonOrganization: '中国科学院自动化研究所', commonDepartment: '智能系统实验室', effectivePeriod: '2018-01 至 2022-12', overlapDuration: '4 年', periodAchievements: 6 } } },
    resultRows: [
      { label: '同事关系', value: '18', tone: 'blue' },
      { label: '所属团队', value: '4', tone: 'green' },
      { label: '重叠年限', value: '4', tone: 'orange' },
      { label: '期间成果', value: '6', tone: 'purple' },
    ],
    summaryRows: [
      { label: '核心专家', value: '张明远｜研究员' },
      { label: '核心专家机构', value: '中国科学院自动化研究所｜智能系统实验室' },
      { label: '同事专家', value: '李佳宁｜副研究员' },
      { label: '共同机构', value: '中国科学院自动化研究所' },
      { label: '所属部门/团队', value: '智能系统实验室｜知识工程项目组' },
      { label: '关系生效时段', value: '2018-01 至 2022-12' },
      { label: '任职重叠时间', value: '4 年' },
      { label: '共同工作内容', value: '科技知识图谱构建、关系推理与系统研发' },
      { label: '协作场景', value: '同一实验室科研协作、联合项目攻关' },
      { label: '同事期间成果', value: '论文 3 篇、项目 2 项、技术报告 1 份' },
      { label: '关系判定', value: '存在同事关系' },
    ],
    evidence: ['任职时间存在重叠，机构层级匹配到同一实验室。', '标注共同工作内容和协作场景。', '关联同事期间产生的合作成果。'],
    rules: actualServiceRules['expert-colleague'],
  },
  {
    key: 'expert-alumni',
    title: '科技专家校友关系',
    subtitle: '基于教育经历匹配同校校友，归因同校/同学历/同期，并附互动摘要。',
    endpoint: '/api/v1/kg-construction/expert-alumni-relations/query',
    method: 'POST',
    moduleRequirement: '科技专家校友关系服务基于科技专家的教育背景数据，结合知识图谱中的院校信息与校友网络数据，运用教育经历匹配算法，识别并构建专家之间的校友关系。服务会对校友关系进行细分，记录校友关系的关联维度，同时关联校友之间的后续学术交流、合作互动等信息，为挖掘科技专家的教育背景关联与校友资源网络提供支持。',
    requestFields: [
      { name: 'expertId', type: 'string', required: '是', description: '请输入专家，如 person_9F9A0001' },
      { name: 'targetExpertId', type: 'string', required: '否', description: '请输入目标专家，如 person_9F9A0004' },
      { name: 'school', type: 'string', required: '否', description: '请输入院校，如清华大学' },
      { name: 'educationStage', type: 'string', required: '否', description: '教育阶段，可多选（如 博士、硕士），多选时以逗号拼接提交' },
      { name: 'limit', type: 'number', defaultValue: '20', required: '否', placeholder: '选填，1-50，默认 20', description: '返回校友关系数上限，1-50，默认 20' },
    ],
    responseFields: commonResponseFields,
    requestExample: {
      expertId: 'person_9F9A0001',
      targetExpertId: 'person_9F9A0004',
      school: '清华大学',
      educationStage: '博士',
      limit: 20,
    },
    responseExample: {
      code: 200,
      success: true,
      msg: 'success',
      data: {
        mode: 'pair',
        total: 1,
        dimensionsCatalog: ['同校', '同学历', '同期'],
        sourceMeta: { space: 'dev', truncated: false },
      },
    },
    resultRows: [
      { label: '校友数量', value: '', tone: 'blue' },
      { label: '查询模式', value: '', tone: 'green' },
      { label: '关联维度', value: '', tone: 'orange' },
      { label: '截断标记', value: '', tone: 'purple' },
    ],
    summaryRows: [
      { label: '专家', value: '' },
      { label: '模式', value: '' },
      { label: '校友数', value: '' },
      { label: '关联维度', value: '' },
      { label: '截断', value: '' },
      { label: '图空间', value: '' },
    ],
    evidence: [
      '同校为成立校友的必要条件（院校字段 NFKC 归一后比较）。',
      '同学历/同期仅在学位、教育日期可支撑时输出；不输出同院系/同导师。',
      '互动摘要汇总 COAUTHOR_WITH 与共同论文/专利/项目计数。',
    ],
    rules: actualServiceRules['expert-alumni'],
  },
  {
    key: 'paper-cooperation',
    title: '科技专家论文合作关系',
    subtitle: '围绕论文作者、主题和被引数据分析合作网络。',
    endpoint: '/api/v1/kg-construction/expert-paper-cooperation-relations/structured-result',
    method: 'POST',
    moduleRequirement: '科技专家论文合作关系服务通过分析知识图谱中科技专家发表的学术论文数据，提取论文的作者列表、作者单位、合作发表时间、论文主题等信息，运用作者关联与合作频次算法，构建专家之间的论文合作关系。服务会统计专家之间的合作论文数量、合作发表的期刊或会议级别、论文被引情况，分析合作论文的研究方向与共同贡献，同时识别长期稳定的论文合作团队与核心合作人员，为研究学术合作网络与专家学术影响力提供依据。',
    requestFields: [
      { name: 'expertAId', type: 'string', required: '是', maxLength: 64, description: '专家 A 唯一标识，最多 64 个字符' },
      { name: 'expertBId', type: 'string', required: '是', maxLength: 64, description: '专家 B 唯一标识，最多 64 个字符' },
      { name: 'startTime', type: 'date', required: '否', placeholder: '选填，格式 YYYY-MM-DD，如 2021-01-01', description: '统计开始时间，格式 YYYY-MM-DD，不能晚于当前日期' },
      { name: 'endTime', type: 'date', required: '否', placeholder: '选填，格式 YYYY-MM-DD，如 2026-08-31', description: '统计结束时间，格式 YYYY-MM-DD，不能晚于当前日期' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expertAId: 'person_121d48631f434f4d323ba521d33032ad', expertBId: 'person_42914016fe8d6e0e1d01dad5845c47e6', startTime: '2021-01-01', endTime: '2026-08-31' },
    responseExample: { structuredResult: { cooperationPaperCount: 0, citation: { total: 0, max: 0 }, stableTeamMembers: [], paperTopics: [] } },
    resultRows: [
      { label: '合作论文', value: '14', tone: 'blue' },
      { label: '论文被引', value: '1260', tone: 'green' },
      { label: '研究方向', value: '5', tone: 'orange' },
      { label: '核心合作人员', value: '7', tone: 'purple' },
    ],
    summaryRows: [
      { label: '核心专家', value: '张明远｜清华大学' },
      { label: '合作专家', value: '李佳宁｜中国科学院自动化研究所' },
      { label: '作者单位', value: '清华大学、中国科学院自动化研究所' },
      { label: '合作发表时间', value: '2019—2025' },
      { label: '论文主题', value: '人工智能、知识图谱、先进计算、关系推理' },
      { label: '合作论文数量', value: '14 篇' },
      { label: '期刊/会议级别', value: 'JCR Q1 论文 5 篇、A 类会议论文 4 篇' },
      { label: '论文被引情况', value: '总被引 1260 次｜篇均被引 90 次' },
      { label: '研究方向', value: '知识图谱、图神经网络、智能计算等 5 个方向' },
      { label: '共同贡献', value: '关系推理模型、图谱构建方法、开源数据集' },
      { label: '核心合作人员', value: '李佳宁、陈思远、王青等 7 人' },
      { label: '合作团队特征', value: '长期稳定合作团队' },
    ],
    evidence: ['提取作者列表、作者单位、发表时间和论文主题。', '统计期刊会议级别和被引情况。', '识别长期稳定合作团队和核心合作人员。'],
    rules: actualServiceRules['paper-cooperation'],
  },
  {
    key: 'enterprise-relation',
    title: '重点关注科技企业关系',
    subtitle: '连接专家、企业角色、合作领域与经营状况。',
    endpoint: '/api/v1/kg-service/key-enterprise-relation',
    method: 'POST',
    moduleRequirement: '重点关注科技企业关系服务围绕科技专家或人才，通过挖掘知识图谱中与专家相关的企业关联数据，运用企业关联与角色定位算法，构建专家与重点关注科技企业之间的关系。服务会标注专家在企业中的角色、合作领域、合作时间与合作模式，同时关联企业的行业地位、技术方向与经营状况，帮助用户了解科技专家与产业界的合作关联及资源对接情况。',
    requestFields: [
      { name: 'expert_id', type: 'string', required: '是', maxLength: 64, description: '请输入专家唯一标识，最多 64 个字符' },
      { name: 'enterprise_name', type: 'string', required: '否', maxLength: 64, description: '请输入企业名称（模糊筛选，可留空，最多 64 个字符，不能包含 !@#￥%& 等异常字符）' },
      { name: 'role_type', type: 'string', required: '否', maxLength: 64, description: '请输入角色筛选（如 总经理，可留空，最多 64 个字符）' },
      { name: 'industry', type: 'string', required: '否', maxLength: 64, description: '请输入行业方向筛选（可留空，最多 64 个字符，不能包含 !@#￥%& 等异常字符）' },
      { name: 'key_tech_enterprise_only', type: 'boolean', defaultValue: 'true', required: '否', description: '只保留重点科技企业（默认 true）；提交布尔 true/false', options: ['true', 'false'] },
    ],
    responseFields: [
      { name: 'code', type: 'number', description: '服务状态码（200 成功）' },
      { name: 'success', type: 'boolean', description: '是否成功' },
      { name: 'msg', type: 'string', description: '提示消息' },
      { name: 'data.expert_id', type: 'string', description: '专家标识' },
      { name: 'data.expert_name', type: 'string', description: '专家姓名' },
      { name: 'data.enterprises', type: 'number', description: '关联重点科技企业数' },
      { name: 'data.roles', type: 'number', description: '角色类型数' },
      { name: 'data.cooperation_fields', type: 'array', description: '合作领域列表' },
      { name: 'data.relations', type: 'array', description: '专家-企业关系列表' },
      { name: 'data.relations[].enterprise_id', type: 'string', description: '企业 VID' },
      { name: 'data.relations[].enterprise_name', type: 'string', description: '企业名称' },
      { name: 'data.relations[].cooperation_type', type: 'string', description: '关系类型：governance/project_cooperation/patent_cooperation' },
      { name: 'data.relations[].cooperation_mode', type: 'string', description: '合作模式：高管任职/法人代表/项目合作/专利合作…' },
      { name: 'data.relations[].role_label', type: 'string', description: '专家企业角色' },
      { name: 'data.relations[].role_level', type: 'string', description: '角色层级 L1/L2/L3' },
      { name: 'data.relations[].tech_field', type: 'string', description: '合作领域' },
      { name: 'data.relations[].period', type: 'object', description: '合作时间 {start, end}' },
      { name: 'data.relations[].enterprise_background', type: 'object', description: '企业背景（行业地位/技术方向/经营状况，从 org 节点 extra_json 摊平）' },
      { name: 'data.relations[].risk_summary', type: 'string', description: '首要企业风险事件摘要（best-effort 探测）' },
      { name: 'data.evidence', type: 'array', description: '证据链' },
    ],
    // 测试数据不再预填到表单，避免误提交样例；测试用例见 backend/docs/enterprise_relation_test_parameters.md
    requestExample: { expert_id: 'person_8A636L1c' },
    responseExample: { code: 0, message: 'success', data: { enterprises: 9, roles: 4, cooperation_fields: ['芯片设计', '智能制造'] } },
    resultRows: [
      { label: '关联企业', value: '9', tone: 'blue' },
      { label: '角色类型', value: '4', tone: 'green' },
      { label: '合作领域', value: '6', tone: 'orange' },
      { label: '经营风险', value: '2', tone: 'purple' },
    ],
    summaryRows: [
      { label: '科技专家', value: '张明远｜研究员' },
      { label: '重点关注企业', value: '华南智能芯片有限公司' },
      { label: '专家企业角色', value: '技术顾问、联合项目负责人' },
      { label: '合作时间', value: '2021-03 至今' },
      { label: '合作领域', value: '芯片设计、智能制造、知识图谱' },
      { label: '合作模式', value: '技术咨询、联合研发、成果转化' },
      { label: '行业地位', value: '集成电路设计领域重点科技企业' },
      { label: '技术方向', value: '智能计算芯片、工业智能化解决方案' },
      { label: '经营状况', value: '正常经营｜近三年研发投入持续增长' },
      { label: '关联企业数量', value: '9 家' },
      { label: '风险提示', value: '2 项待持续关注的经营与供应链风险' },
      { label: '资源对接价值', value: '专家技术能力与企业研发方向高度匹配' },
    ],
    evidence: ['标注专家在企业中的角色、合作领域、合作时间和模式。', '关联企业行业地位、技术方向与经营状况。', '支持产业界资源对接分析。'],
    rules: actualServiceRules['enterprise-relation'],
  },
  {
    key: 'industry-chain-event',
    title: '科技产业链点TOP-N事件关系',
    subtitle: '围绕产业节点筛选事件并关联专家、企业和影响。',
    endpoint: '/api/v1/kg-service/industry-node-top-events',
    method: 'POST',
    moduleRequirement: '科技产业链点 TOP-N 事件关系服务针对科技产业链中的特定环节或节点，通过收集知识图谱中与该节点相关的事件数据，运用事件影响力评估算法，筛选出影响力排名前 N 的核心事件。服务会构建这些 TOP-N 事件与相关科技专家或人才的关联关系，分析事件对产业链节点的影响及后续发展趋势，为产业链节点的风险预警与机遇挖掘提供支持。',
    requestFields: [
      { name: 'chain_node_id', type: 'string', required: '是', maxLength: 64, description: '请输入产业链节点标识（如 IC0007007），最多 64 个字符' },
      { name: 'top_n', type: 'number', required: '否', description: '返回事件数量，请输入 1-50 的整数，默认 10' },
      { name: 'event_type', type: 'string', required: '否', maxLength: 64, description: '事件类型筛选（financing/bankruptcy/bid/news/…，可留空，最多 64 个字符）' },
      { name: 'time_range_start', type: 'month', required: '否', description: '起始年月（留空不筛）；与 time_range_end 合并为接口参数 time_range，格式 YYYY-MM~YYYY-MM（保留月份，后端按月筛）' },
      { name: 'time_range_end', type: 'month', required: '否', description: '结束年月（留空不筛）；与 time_range_start 合并为接口参数 time_range，格式 YYYY-MM~YYYY-MM（保留月份，后端按月筛）' },
      { name: 'max_orgs', type: 'number', required: '否', maxLength: 64, placeholder: '选填，1-50，默认 20', description: '最多扫描企业数，取值 1-50 的整数，默认 20' },
    ],
    responseFields: [
      { name: 'code', type: 'number', description: '服务状态码（200 成功）' },
      { name: 'success', type: 'boolean', description: '是否成功' },
      { name: 'msg', type: 'string', description: '提示消息' },
      { name: 'data.chain_node_id', type: 'string', description: '产业链节点标识' },
      { name: 'data.chain_node_name', type: 'string', description: '节点名称' },
      { name: 'data.chain_name', type: 'string', description: '产业链名称' },
      { name: 'data.events', type: 'number', description: 'TOP-N 事件数' },
      { name: 'data.experts', type: 'number', description: '关联专家数' },
      { name: 'data.enterprises', type: 'number', description: '关联企业数' },
      { name: 'data.risk_level', type: 'string', description: '风险等级：高/中/低' },
      { name: 'data.top_events', type: 'array', description: 'TOP 事件列表（按影响力降序）' },
      { name: 'data.top_events[].event_type', type: 'string', description: '事件类型' },
      { name: 'data.top_events[].occur_date', type: 'string', description: '发生时间' },
      { name: 'data.top_events[].title', type: 'string', description: '事件标题' },
      { name: 'data.top_events[].impact_score', type: 'number', description: '影响力评分' },
      { name: 'data.top_events[].rank', type: 'number', description: '影响力排名' },
      { name: 'data.top_events[].org_name', type: 'string', description: '关联企业名称' },
      { name: 'data.relations', type: 'array', description: '事件-专家关系列表（event→org→expert）' },
      { name: 'data.node_impact', type: 'string', description: '节点影响分析（标书维度）' },
      { name: 'data.trend', type: 'string', description: '发展趋势分析（标书维度）' },
      { name: 'data.opportunity', type: 'string', description: '机遇挖掘分析（标书维度）' },
      { name: 'data.evidence', type: 'array', description: '证据链' },
    ],
    // 测试数据不再预填到表单，避免误提交样例；测试用例见 backend/docs/industry_chain_topn_test_parameters.md
    requestExample: { chain_node_id: 'IC0007007', top_n: 10 },
    responseExample: { code: 0, message: 'success', data: { events: 10, experts: 18, enterprises: 24, risk_level: '中' } },
    resultRows: [
      { label: 'TOP事件', value: '10', tone: 'blue' },
      { label: '关联专家', value: '18', tone: 'green' },
      { label: '关联企业', value: '24', tone: 'orange' },
      { label: '风险等级', value: '中', tone: 'purple' },
    ],
    summaryRows: [
      { label: '产业链', value: '集成电路产业链' },
      { label: '产业链节点', value: '芯片设计' },
      { label: '筛选范围', value: 'TOP 10｜投融资、政策、技术突破、风险事件' },
      { label: '核心事件', value: '高性能半导体材料制备关键技术专利授权' },
      { label: '事件类型/时间', value: '技术突破｜2026-06' },
      { label: '影响力排名', value: '第 1 名｜影响力评分 92.6' },
      { label: '关联专家', value: '陈建国、李佳宁等 18 人' },
      { label: '关联企业', value: '华南智能芯片等 24 家' },
      { label: '节点影响', value: '推动上游材料工艺升级，并向中游芯片制造环节传导' },
      { label: '发展趋势', value: '短期热度上升，中期产业化合作持续增长' },
      { label: '风险预警', value: '供应集中度较高，存在关键材料供应稳定性风险' },
      { label: '机遇挖掘', value: '关键材料制备技术具备成果转化和产业合作机会' },
    ],
    evidence: ['按影响力评估筛选产业链节点 TOP-N 事件。', '构建事件与专家、企业、人才的关联关系。', '分析产业链影响和后续发展趋势。'],
    rules: actualServiceRules['industry-chain-event'],
  },
  {
    key: 'industry-chain-panorama',
    title: '科技产业链全景图',
    subtitle: '整合产业节点、关键技术、企业和事件形成链路全景。',
    endpoint: '/api/v1/kg-construction/industry-chain-panorama/query',
    method: 'POST',
    moduleRequirement: '科技产业链全景图服务通过整合知识图谱中科技产业链各环节的实体、关系、事件等数据，运用产业链架构建模与可视化算法，构建覆盖全产业链的结构化全景图。服务会清晰展示产业链各环节的核心节点、关联关系与数据流向，标注各环节的关键技术、重点企业与核心专家，同时支持根据用户需求进行层级展开、关系筛选与动态更新，为用户全面掌握科技产业链的整体结构、运行态势与发展机遇提供直观的可视化工具。',
    requestFields: [
      { name: 'industry', type: 'string', required: '否', description: '产业关键词，如 人工智能 / 集成电路，最多 64 个字符，不能包含 !@#￥%& 等异常字符' },
      { name: 'anchorId', type: 'string', required: '否', description: '核心节点 VID，用于生成扩展子图，最多 64 个字符，不能包含空格或 !@#￥%& 等异常字符' },
      { name: 'depth', type: 'select', options: ['1', '2', '3'], defaultValue: '2', required: '否', description: '从核心节点向外展开的层级（跳数），可选 1-3，默认 2；层级越大子图越完整但越慢' },
      { name: 'relationTypes', type: 'multi-select', required: '否', description: '只保留选中的关系类型：产业链归属 / 论文合作 / 机构任职，留空表示不筛选' },
      { name: 'topK', type: 'number', defaultValue: '5', required: '否', placeholder: '选填，1-20，默认 5', description: '每类关键实体返回数上限，1-20，默认 5' },
    ],
    // 后端还接受 dataSource（固定 "all"，前端自动填充）和 refresh（bool，由「刷新图谱」按钮触发），
    // 二者均非用户输入项，故不在 requestFields 表单中展示。
    responseFields: [
      { name: 'taskName', type: 'string', description: '服务名称' },
      { name: 'input', type: 'object', description: '回填的查询入参' },
      { name: 'summary', type: 'object', description: '规模统计与产业关键词' },
      { name: 'layers', type: 'array', description: '四个分层：核心技术、领军企业、领军专家、代表成果' },
      { name: 'graph', type: 'object', description: '以核心节点扩展的子图（nodes/edges）' },
      { name: 'source', type: 'object', description: '数据来源，标记是否降级到样例数据' },
      { name: 'apiResultExample', type: 'object', description: '接口调用示例' },
    ],
    requestExample: { dataSource: 'all', industry: '人工智能', anchorId: '', depth: 2, topK: 3, relationTypes: ['COAUTHOR_WITH'] },
    responseExample: {
      taskName: '科技产业链全景图',
      input: { dataSource: 'all', industry: '人工智能', anchorId: '', depth: 2, topK: 5 },
      summary: {
        industry: '人工智能',
        totalNodes: 186,
        totalEdges: 420,
        nodesByLabel: { Person: 42, Organization: 48, Paper: 60, Keyword: 36 },
        edgesByType: { AFFILIATED_WITH: 120, AUTHORED_BY: 180, HAS_KEYWORD: 120 },
      },
      layers: [
        { key: 'core_technology', title: '核心技术', total: 22, items: [] },
        { key: 'leading_enterprise', title: '领军企业', total: 48, items: [] },
        { key: 'leading_expert', title: '领军专家', total: 36, items: [] },
        { key: 'flagship_achievement', title: '代表成果', total: 60, items: [] },
      ],
      graph: { nodes: [], edges: [] },
      source: { requested: 'all', actual: 'graph-api', fallback: false },
      apiResultExample: {
        url: '/api/v1/kg-construction/industry-chain-panorama/query',
        method: 'POST',
        query: { dataSource: 'all', industry: '人工智能', anchorId: '', depth: 2, topK: 5 },
      },
    },
    resultRows: [
      { label: '产业节点', value: '186', tone: 'blue' },
      { label: '关联关系', value: '420', tone: 'green' },
      { label: '关键技术', value: '22', tone: 'orange' },
      { label: '重点企业', value: '48', tone: 'purple' },
    ],
    summaryRows: [
      { label: '产业链名称', value: '人工智能计算产业链' },
      { label: '产业链标识', value: 'AI-COMPUTING' },
      { label: '展开层级', value: '3 级' },
      { label: '核心环节', value: '上游基础资源、中游核心技术、下游应用场景' },
      { label: '核心节点', value: '算力芯片、数据资源、知识图谱、大模型、行业应用' },
      { label: '关联关系', value: '上下游、技术支撑、企业布局、专家支撑、事件影响' },
      { label: '数据流向', value: '基础资源 → 核心技术 → 行业应用' },
      { label: '关键技术', value: '算力芯片、向量数据库、知识图谱、大模型等 22 项' },
      { label: '重点企业', value: '华为昇腾、寒武纪、百度智能云等 48 家' },
      { label: '核心专家', value: '张明远、李佳宁、陈思远等' },
      { label: '产业动态事件', value: '智算中心扩容、国产算力适配、多模态模型升级' },
      { label: '图谱规模', value: '186 个节点｜420 条关系' },
      { label: '动态更新', value: '尚未更新，点击"刷新数据"或开启自动更新' },
    ],
    evidence: ['整合产业链实体、关系、事件数据。', '展示核心节点、关联关系和数据流向。', '支持层级展开、关系筛选和动态更新。'],
    rules: actualServiceRules['industry-chain-panorama'],
  },
]


export function getServiceModule(key: string): ServiceModule {
  return serviceModules.find((item) => item.key === key) ?? serviceModules[0]
}
