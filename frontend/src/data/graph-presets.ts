export type GraphNodeType = 'main' | 'expert' | 'org' | 'company' | 'paper' | 'topic' | 'project' | 'event'

export interface GraphNodeData {
  id: string
  label: string
  nodeType: GraphNodeType
  x: number
  y: number
  radius?: number
  entityType: string
  confidence: number
  relations: string
  evidence: string[]
  level?: number
}

export interface GraphEdgeData {
  id: string
  from: string
  to: string
  label: string
  category: string
}

export interface GraphPreset {
  nodes: GraphNodeData[]
  edges: GraphEdgeData[]
}

export interface GraphProvenanceEvidence {
  title: string
  businessTable: string
  technicalTable: string
  recordId: string
  fieldIdentifier: string
  summary: string
}

export interface GraphProvenance {
  sourceDatabase: string
  evidences: GraphProvenanceEvidence[]
  relationEndpoints?: Array<{
    role: '源实体' | '目标实体'
    name: string
    entityType: string
    businessTable: string
    technicalTable: string
    recordId: string
    fieldIdentifier: string
  }>
  task: {
    name: string
    instanceId: string
    executedAt: string
    status: string
    mode: string
    batch: string
  }
  result: {
    ruleName: string
    ruleVersion: string
    graphVersion: string
    generatedAt: string
    status: string
  }
}

const nodeSourceMap: Record<GraphNodeType, { businessTable: string; technicalTable: string; keyField: string; summary: string }> = {
  main: { businessTable: '专家基本信息表', technicalTable: 'expert_profile', keyField: 'expert_id', summary: '专家姓名、任职机构和研究方向等基本信息' },
  expert: { businessTable: '专家基本信息表', technicalTable: 'expert_profile', keyField: 'expert_id', summary: '专家姓名、任职机构和研究方向等基本信息' },
  org: { businessTable: '科技机构信息表', technicalTable: 'organization_base', keyField: 'organization_id', summary: '机构标准名称、简称和统一标识信息' },
  company: { businessTable: '科技企业信息表', technicalTable: 'enterprise_registry', keyField: 'enterprise_id', summary: '企业名称、统一社会信用代码和经营信息' },
  paper: { businessTable: '论文成果表', technicalTable: 'paper_metadata', keyField: 'paper_id', summary: '论文题名、作者、发表时间和主题关键词' },
  topic: { businessTable: '科技主题标签表', technicalTable: 'research_topic', keyField: 'topic_id', summary: '标准主题名称、关键词和所属技术领域' },
  project: { businessTable: '科研项目表', technicalTable: 'research_project', keyField: 'project_id', summary: '项目名称、承担单位、成员和执行时间' },
  event: { businessTable: '产业事件表', technicalTable: 'industry_event', keyField: 'event_id', summary: '事件名称、参与主体、时间和事件类型' },
}

const nodeSourceValue = (node: GraphNodeData) => node.id === 'core'
  ? 'EXPERT-10286'
  : node.id === 'org-1' ? 'ORG-10018' : node.id.toUpperCase()

const nodeFieldIdentifier = (node: GraphNodeData) => `${nodeSourceMap[node.nodeType].keyField} = ${nodeSourceValue(node)}`

const edgeSourceMap: Record<string, { businessTable: string; technicalTable: string; summary: string }> = {
  论文合作: { businessTable: '论文作者关联表', technicalTable: 'paper_author_relation', summary: '两端实体共同出现在同一论文作者列表中' },
  同事: { businessTable: '专家任职经历表', technicalTable: 'expert_employment', summary: '两端专家在同一机构或部门存在任职时间重叠' },
  校友: { businessTable: '专家教育经历表', technicalTable: 'expert_education', summary: '两端专家的院校、院系或导师信息存在匹配' },
  企业关联: { businessTable: '专家企业角色表', technicalTable: 'expert_enterprise_role', summary: '工商角色、项目合作或成果转化记录关联两端实体' },
  产业事件: { businessTable: '事件主体关联表', technicalTable: 'event_subject_relation', summary: '两端实体共同参与同一产业事件' },
  直接关系: { businessTable: '业务关系记录表', technicalTable: 'direct_relation', summary: '结构化业务记录直接关联两端实体' },
}

export function getNodeProvenance(node: GraphNodeData): GraphProvenance {
  const source = nodeSourceMap[node.nodeType]
  return {
    sourceDatabase: '科技要素数据库',
    evidences: [{
      title: '原始业务记录',
      businessTable: source.businessTable,
      technicalTable: source.technicalTable,
      recordId: `${node.id.toUpperCase()}-SRC`,
      fieldIdentifier: nodeFieldIdentifier(node),
      summary: source.summary,
    }],
    task: {
      name: `${node.entityType}标准化与实体融合`,
      instanceId: node.id === 'core' ? 'PI-20260714-0001' : node.id === 'org-1' ? 'PI-20260714-0002' : `PI-20260714-NODE-${node.id.toUpperCase()}`,
      executedAt: '2026-07-13 02:12:36',
      status: '成功',
      mode: '清洗规则 + 实体对齐',
      batch: 'UPD-20260714',
    },
    result: {
      ruleName: `${node.entityType}实体融合规则`,
      ruleVersion: 'ENTITY-MERGE-1.6',
      graphVersion: 'v1.8',
      generatedAt: '2026-07-13 02:14:08',
      status: '已入图',
    },
  }
}

export function getEdgeProvenance(edge: GraphEdgeData, from?: GraphNodeData, to?: GraphNodeData): GraphProvenance {
  const relationName = from && to ? `${from.label} → ${to.label}` : edge.id
  const isInferred = edge.category === '间接关系'
  const source = edgeSourceMap[edge.category] ?? edgeSourceMap.直接关系
  const evidences: GraphProvenanceEvidence[] = isInferred
    ? [
        {
          title: `${from?.label ?? '源实体'}关联记录`,
          businessTable: '实体主题关联表',
          technicalTable: 'entity_topic_relation',
          recordId: `${(from?.id ?? edge.from).toUpperCase()}-TOPIC`,
          fieldIdentifier: `entity_id = ${(from?.id ?? edge.from).toUpperCase()}`,
          summary: `记录${from?.label ?? '源实体'}关联的论文、项目或主题标签`,
        },
        {
          title: `${to?.label ?? '目标实体'}关联记录`,
          businessTable: '实体主题关联表',
          technicalTable: 'entity_topic_relation',
          recordId: `${(to?.id ?? edge.to).toUpperCase()}-TOPIC`,
          fieldIdentifier: `entity_id = ${(to?.id ?? edge.to).toUpperCase()}`,
          summary: `记录${to?.label ?? '目标实体'}关联的论文、项目或主题标签`,
        },
        {
          title: '推理路径证据',
          businessTable: '实体关系记录表',
          technicalTable: 'entity_relation',
          recordId: `${edge.id.toUpperCase()}-PATH`,
          fieldIdentifier: `relation_id = ${edge.id}`,
          summary: `${relationName}通过共同论文、项目或主题节点形成两跳路径`,
        },
      ]
    : [{
        title: '原始业务记录',
        businessTable: source.businessTable,
        technicalTable: source.technicalTable,
        recordId: `${edge.id.toUpperCase()}-SRC`,
        fieldIdentifier: `relation_id = ${edge.id}`,
        summary: source.summary,
      }]
  return {
    sourceDatabase: '科技要素数据库',
    evidences,
    relationEndpoints: from && to ? [
      {
        role: '源实体', name: from.label, entityType: from.entityType,
        businessTable: nodeSourceMap[from.nodeType].businessTable,
        technicalTable: nodeSourceMap[from.nodeType].technicalTable,
        recordId: `${from.id.toUpperCase()}-SRC`,
        fieldIdentifier: nodeFieldIdentifier(from),
      },
      {
        role: '目标实体', name: to.label, entityType: to.entityType,
        businessTable: nodeSourceMap[to.nodeType].businessTable,
        technicalTable: nodeSourceMap[to.nodeType].technicalTable,
        recordId: `${to.id.toUpperCase()}-SRC`,
        fieldIdentifier: nodeFieldIdentifier(to),
      },
    ] : undefined,
    task: {
      name: isInferred ? '图谱关系推理' : `${edge.label}关系识别`,
      instanceId: edge.id === 'e40' ? 'PI-20260714-0003' : `PI-20260714-EDGE-${edge.id.toUpperCase()}`,
      executedAt: '2026-07-13 02:12:36',
      status: '成功',
      mode: isInferred ? '两跳路径 + 共现规则' : '业务规则识别',
      batch: 'UPD-20260714',
    },
    result: {
      ruleName: isInferred ? '两跳路径与主题共现规则' : `${edge.label}关系映射规则`,
      ruleVersion: isInferred ? 'REL-INFER-1.3' : 'REL-MAP-2.1',
      graphVersion: 'v1.8',
      generatedAt: '2026-07-13 02:14:08',
      status: '已入图',
    },
  }
}

const expertEvidence = [
  '共同发表论文 4 篇，作者列表和单位信息一致。',
  '任职时间存在重叠，机构层级匹配到同一实验室。',
  '企业合作关系来自项目公告和工商角色数据。',
]

export const queryGraphPreset: GraphPreset = {
  nodes: [
    {
      id: 'core',
      label: '张明远',
      nodeType: 'main',
      x: 382,
      y: 214,
      radius: 34,
      entityType: '科技专家',
      confidence: 0.94,
      relations: '论文合作 4、同事 3、企业关联 2',
      evidence: expertEvidence,
    },
    {
      id: 'expert-1',
      label: '李佳宁',
      nodeType: 'expert',
      x: 188,
      y: 112,
      radius: 28,
      entityType: '科技专家',
      confidence: 0.94,
      relations: '论文合作 4',
      evidence: ['共同发表论文 4 篇，作者列表和单位信息一致。'],
    },
    {
      id: 'org-1',
      label: '清华大学',
      nodeType: 'org',
      x: 570,
      y: 102,
      radius: 28,
      entityType: '机构团队',
      confidence: 0.88,
      relations: '同事 3',
      evidence: ['任职时间存在重叠，机构层级匹配到同一实验室。'],
    },
    {
      id: 'company-1',
      label: '华南智能芯片',
      nodeType: 'company',
      x: 182,
      y: 318,
      radius: 30,
      entityType: '科技企业',
      confidence: 0.82,
      relations: '企业关联 2',
      evidence: ['企业合作关系来自项目公告和工商角色数据。'],
    },
    {
      id: 'paper-1',
      label: '先进计算论文',
      nodeType: 'paper',
      x: 592,
      y: 316,
      radius: 30,
      entityType: '论文成果',
      confidence: 0.91,
      relations: '成果证据 1',
      evidence: ['论文主题与专家研究方向一致，被引次数持续更新。'],
    },
    {
      id: 'topic-1',
      label: '生物医药',
      nodeType: 'topic',
      x: 116,
      y: 192,
      entityType: '研究方向',
      confidence: 0.76,
      relations: '关联主题 1',
      evidence: ['来自论文关键词与项目标签聚合。'],
    },
    {
      id: 'project-1',
      label: '项目18',
      nodeType: 'project',
      x: 284,
      y: 92,
      entityType: '科研项目',
      confidence: 0.85,
      relations: '项目参与 1',
      evidence: ['项目成员名单与单位信息一致。'],
    },
    {
      id: 'topic-2',
      label: '人工智能',
      nodeType: 'topic',
      x: 650,
      y: 178,
      entityType: '研究方向',
      confidence: 0.79,
      relations: '关联主题 1',
      evidence: ['来自论文关键词聚合。'],
    },
    {
      id: 'paper-2',
      label: '论文006',
      nodeType: 'paper',
      x: 458,
      y: 74,
      entityType: '论文成果',
      confidence: 0.9,
      relations: '论文合作 1',
      evidence: ['作者列表包含核心专家节点。'],
    },
    {
      id: 'project-2',
      label: '技术31',
      nodeType: 'project',
      x: 104,
      y: 258,
      entityType: '科研项目',
      confidence: 0.83,
      relations: '项目参与 1',
      evidence: ['项目公告与专家履历交叉验证。'],
    },
    {
      id: 'company-2',
      label: '腾讯',
      nodeType: 'company',
      x: 302,
      y: 326,
      entityType: '科技企业',
      confidence: 0.8,
      relations: '企业关联 1',
      evidence: ['合作公告与专利转让记录一致。'],
    },
    {
      id: 'topic-3',
      label: '新能源',
      nodeType: 'topic',
      x: 686,
      y: 254,
      entityType: '研究方向',
      confidence: 0.74,
      relations: '关联主题 1',
      evidence: ['产业链事件共现分析得到。'],
    },
    {
      id: 'project-3',
      label: '项目03',
      nodeType: 'project',
      x: 498,
      y: 342,
      entityType: '科研项目',
      confidence: 0.81,
      relations: '项目参与 1',
      evidence: ['项目阶段成果已结构化入库。'],
    },
    {
      id: 'event-1',
      label: '湾区产业论坛',
      nodeType: 'event',
      x: 382,
      y: 360,
      entityType: '产业事件',
      confidence: 0.84,
      relations: '事件共现 2',
      evidence: ['产业链事件与专家、企业、项目存在共现关系。'],
    },
    {
      id: 'event-2',
      label: '芯片投融资',
      nodeType: 'event',
      x: 704,
      y: 330,
      entityType: '产业事件',
      confidence: 0.78,
      relations: '风险事件 1',
      evidence: ['投融资事件与企业、产业方向和项目阶段关联。'],
    },
    { id: 'expert-2', label: '王青', nodeType: 'expert', x: 248, y: 172, entityType: '科技专家', confidence: 0.89, relations: '同事 2、论文合作 3', evidence: ['同一项目组成员，论文作者单位一致。'] },
    { id: 'expert-3', label: '陈卓', nodeType: 'expert', x: 332, y: 138, entityType: '科技专家', confidence: 0.86, relations: '项目参与 2', evidence: ['项目成员名单与成果署名匹配。'] },
    { id: 'expert-4', label: '刘洋', nodeType: 'expert', x: 438, y: 140, entityType: '科技专家', confidence: 0.84, relations: '校友 1、合作 2', evidence: ['教育经历与合作论文交叉验证。'] },
    { id: 'expert-5', label: '赵珊', nodeType: 'expert', x: 522, y: 180, entityType: '科技专家', confidence: 0.82, relations: '产业事件 1', evidence: ['会议报道与项目公告共同出现。'] },
    { id: 'org-2', label: '中科院自动化所', nodeType: 'org', x: 612, y: 238, entityType: '机构团队', confidence: 0.9, relations: '任职 4', evidence: ['机构别名已归一到标准机构。'] },
    { id: 'org-3', label: '深圳先进院', nodeType: 'org', x: 286, y: 252, entityType: '机构团队', confidence: 0.86, relations: '合作机构 2', evidence: ['项目单位与成果单位匹配。'] },
    { id: 'company-3', label: '深算科技', nodeType: 'company', x: 92, y: 340, entityType: '科技企业', confidence: 0.79, relations: '企业合作 1', evidence: ['工商数据与项目公告交叉验证。'] },
    { id: 'company-4', label: '湾区智造', nodeType: 'company', x: 248, y: 380, entityType: '科技企业', confidence: 0.77, relations: '产业链节点 2', evidence: ['产业链事件共现。'] },
    { id: 'paper-3', label: '论文128', nodeType: 'paper', x: 382, y: 292, entityType: '论文成果', confidence: 0.92, relations: '成果证据 2', evidence: ['引用关系与关键词一致。'] },
    { id: 'paper-4', label: '论文215', nodeType: 'paper', x: 526, y: 278, entityType: '论文成果', confidence: 0.88, relations: '论文合作 2', evidence: ['作者列表与机构归属匹配。'] },
    { id: 'topic-4', label: '数字抽象', nodeType: 'topic', x: 54, y: 206, entityType: '研究方向', confidence: 0.72, relations: '主题关联 3', evidence: ['由关键词聚类得到。'] },
    { id: 'topic-5', label: '矩阵分析', nodeType: 'topic', x: 716, y: 136, entityType: '研究方向', confidence: 0.75, relations: '主题关联 2', evidence: ['论文摘要与项目标签共现。'] },
    { id: 'project-4', label: '项目42', nodeType: 'project', x: 156, y: 82, entityType: '科研项目', confidence: 0.83, relations: '项目参与 3', evidence: ['项目成员名单结构化入库。'] },
    { id: 'project-5', label: '模型平台', nodeType: 'project', x: 620, y: 380, entityType: '科研项目', confidence: 0.81, relations: '成果转化 1', evidence: ['项目验收材料与论文成果一致。'] },
    { id: 'event-3', label: 'AI 论坛', nodeType: 'event', x: 386, y: 404, entityType: '产业事件', confidence: 0.8, relations: '事件共现 3', evidence: ['论坛议程、参会企业、专家节点共现。'] },
    { id: 'event-4', label: '成果发布', nodeType: 'event', x: 686, y: 292, entityType: '产业事件', confidence: 0.78, relations: '发布事件 1', evidence: ['新闻报道与项目成果匹配。'] },
  ],
  edges: [
    { id: 'e1', from: 'core', to: 'expert-1', label: '论文合作', category: '论文合作' },
    { id: 'e2', from: 'core', to: 'org-1', label: '同事关系', category: '同事' },
    { id: 'e3', from: 'core', to: 'company-1', label: '企业关联', category: '企业关联' },
    { id: 'e4', from: 'core', to: 'paper-1', label: '成果证据', category: '直接关系' },
    { id: 'e5', from: 'expert-1', to: 'topic-1', label: '研究方向', category: '间接关系' },
    { id: 'e6', from: 'expert-1', to: 'project-1', label: '项目参与', category: '间接关系' },
    { id: 'e7', from: 'org-1', to: 'topic-2', label: '研究方向', category: '间接关系' },
    { id: 'e8', from: 'org-1', to: 'paper-2', label: '论文合作', category: '论文合作' },
    { id: 'e9', from: 'company-1', to: 'project-2', label: '项目参与', category: '间接关系' },
    { id: 'e10', from: 'company-1', to: 'company-2', label: '产业协同', category: '企业关联' },
    { id: 'e11', from: 'paper-1', to: 'topic-3', label: '主题关联', category: '间接关系' },
    { id: 'e12', from: 'paper-1', to: 'project-3', label: '项目成果', category: '间接关系' },
    { id: 'e13', from: 'project-1', to: 'paper-2', label: '成果引用', category: '间接关系' },
    { id: 'e14', from: 'company-1', to: 'event-1', label: '事件参与', category: '产业事件' },
    { id: 'e15', from: 'event-1', to: 'topic-3', label: '产业影响', category: '产业事件' },
    { id: 'e16', from: 'company-2', to: 'event-2', label: '投融资事件', category: '产业事件' },
    { id: 'e17', from: 'core', to: 'expert-2', label: '论文合作', category: '论文合作' },
    { id: 'e18', from: 'core', to: 'expert-3', label: '项目合作', category: '直接关系' },
    { id: 'e19', from: 'core', to: 'expert-4', label: '校友关系', category: '校友' },
    { id: 'e20', from: 'expert-2', to: 'org-3', label: '任职', category: '同事' },
    { id: 'e21', from: 'expert-3', to: 'paper-3', label: '论文成果', category: '论文合作' },
    { id: 'e22', from: 'expert-4', to: 'paper-4', label: '论文合作', category: '论文合作' },
    { id: 'e23', from: 'expert-5', to: 'org-2', label: '任职', category: '同事' },
    { id: 'e24', from: 'org-2', to: 'paper-4', label: '作者单位', category: '间接关系' },
    { id: 'e25', from: 'org-3', to: 'company-4', label: '成果转化', category: '企业关联' },
    { id: 'e26', from: 'company-3', to: 'project-2', label: '项目合作', category: '企业关联' },
    { id: 'e27', from: 'company-4', to: 'event-3', label: '事件参与', category: '产业事件' },
    { id: 'e28', from: 'paper-3', to: 'topic-4', label: '主题关联', category: '间接关系' },
    { id: 'e29', from: 'paper-4', to: 'topic-5', label: '主题关联', category: '间接关系' },
    { id: 'e30', from: 'project-4', to: 'expert-2', label: '项目参与', category: '间接关系' },
    { id: 'e31', from: 'project-4', to: 'topic-1', label: '研究方向', category: '间接关系' },
    { id: 'e32', from: 'project-5', to: 'company-2', label: '成果转化', category: '企业关联' },
    { id: 'e33', from: 'project-5', to: 'event-4', label: '成果发布', category: '产业事件' },
    { id: 'e34', from: 'event-3', to: 'topic-2', label: '主题共现', category: '产业事件' },
    { id: 'e35', from: 'event-4', to: 'topic-5', label: '产业影响', category: '产业事件' },
    { id: 'e36', from: 'company-1', to: 'company-3', label: '供应链协同', category: '企业关联' },
    { id: 'e37', from: 'expert-1', to: 'expert-4', label: '同事关系', category: '同事' },
    { id: 'e38', from: 'expert-2', to: 'paper-2', label: '论文合作', category: '论文合作' },
    { id: 'e39', from: 'org-1', to: 'org-2', label: '机构合作', category: '间接关系' },
    { id: 'e40', from: 'topic-4', to: 'topic-5', label: '主题相近', category: '间接关系' },
  ],
}

const serviceNode = (
  id: string,
  label: string,
  nodeType: GraphNodeType,
  x: number,
  y: number,
  entityType: string,
  relations: string,
  evidence: string,
  confidence = 0.9,
  level = 1,
): GraphNodeData => ({
  id,
  label,
  nodeType,
  x,
  y,
  radius: nodeType === 'main' ? 30 : 24,
  entityType,
  confidence,
  relations,
  evidence: [evidence],
  level,
})

export const serviceGraphPresets: Record<string, GraphPreset> = {
  'expert-direct': {
    nodes: [
      serviceNode('core', '张明远', 'main', 230, 105, '科技专家', '直接关系 12', '专家身份与研究方向已完成实体对齐。', 0.94),
      serviceNode('expert-1', '李佳宁', 'expert', 530, 105, '科技专家', '直接关系 12', '双方存在可验证的直接交互记录。', 0.93),
      serviceNode('scene-1', '科研合作', 'topic', 380, 220, '交互场景', '场景 3', '交互场景来自项目与成果记录。', 0.91),
      serviceNode('paper-1', '共同论文8篇', 'paper', 150, 340, '论文成果', '成果 8', '作者列表同时命中双方专家。', 0.92),
      serviceNode('project-1', '联合项目3项', 'project', 380, 350, '科研项目', '成果 3', '项目成员与承担角色存在协作。', 0.89),
      serviceNode('patent-1', '授权专利2件', 'paper', 610, 340, '专利成果', '成果 2', '发明人信息同时命中双方专家。', 0.87),
    ],
    edges: [
      { id: 'd1', from: 'core', to: 'expert-1', label: '直接关系', category: '直接关系' },
      { id: 'd2', from: 'core', to: 'scene-1', label: '参与场景', category: '直接关系' },
      { id: 'd3', from: 'expert-1', to: 'scene-1', label: '参与场景', category: '直接关系' },
      { id: 'd4', from: 'scene-1', to: 'paper-1', label: '论文合作', category: '论文合作' },
      { id: 'd5', from: 'scene-1', to: 'project-1', label: '项目合作', category: '直接关系' },
      { id: 'd6', from: 'scene-1', to: 'patent-1', label: '成果转化', category: '直接关系' },
    ],
  },
  'node-indirect': {
    nodes: [
      serviceNode('core', '张明远', 'main', 90, 215, '核心专家', '间接节点 36', '以该专家作为多跳路径分析起点。', 0.94),
      serviceNode('expert-1', '李佳宁', 'expert', 285, 105, '直接关联专家', '直接关系 1', '双方存在直接学术合作。', 0.92),
      serviceNode('expert-2', '陈思远', 'expert', 530, 70, '间接关联专家', '强度 0.89', '通过共同合作者形成两跳关系。', 0.89),
      serviceNode('project-1', '协同平台项目', 'project', 285, 325, '科研项目', '项目路径 1', '核心专家参与该项目。', 0.9),
      serviceNode('company-1', '华南智能芯片', 'company', 535, 355, '间接关联企业', '强度 0.76', '企业为项目合作与成果转化方。', 0.86),
      serviceNode('org-1', '知识工程实验室', 'org', 650, 210, '机构团队', '机构路径 1', '专家与项目均关联该机构。', 0.88),
    ],
    edges: [
      { id: 'i1', from: 'core', to: 'expert-1', label: '直接合作', category: '直接关系' },
      { id: 'i2', from: 'expert-1', to: 'expert-2', label: '学术传递', category: '间接关系' },
      { id: 'i3', from: 'core', to: 'project-1', label: '参与项目', category: '直接关系' },
      { id: 'i4', from: 'project-1', to: 'company-1', label: '项目合作', category: '间接关系' },
      { id: 'i5', from: 'expert-2', to: 'org-1', label: '任职', category: '间接关系' },
      { id: 'i6', from: 'company-1', to: 'org-1', label: '机构合作', category: '间接关系' },
    ],
  },
  'two-point-achievement': {
    nodes: [
      serviceNode('core', '陈建国', 'main', 220, 90, '科技专家', '合作成果 17', '专家身份已完成标准化。', 0.95),
      serviceNode('expert-1', '刘芳', 'expert', 540, 90, '科技专家', '合作成果 17', '专家身份与单位信息已核验。', 0.94),
      serviceNode('topic-1', '共同研究领域', 'topic', 380, 205, '技术领域', '领域 4', '成果关键词聚合为共同研究领域。', 0.9),
      serviceNode('paper-1', '合作论文10篇', 'paper', 140, 345, '论文成果', 'Q1 论文 5', '共同作者信息已匹配。', 0.93),
      serviceNode('project-1', '联合项目4项', 'project', 380, 350, '科研项目', '国家级 2', '项目成员和承担单位同时命中。', 0.91),
      serviceNode('patent-1', '合作专利3件', 'paper', 620, 345, '专利成果', '授权 3', '专利发明人和权利人已核验。', 0.9),
    ],
    edges: [
      { id: 't1', from: 'core', to: 'expert-1', label: '长期合作', category: '直接关系' },
      { id: 't2', from: 'core', to: 'topic-1', label: '研究方向', category: '间接关系' },
      { id: 't3', from: 'expert-1', to: 'topic-1', label: '研究方向', category: '间接关系' },
      { id: 't4', from: 'topic-1', to: 'paper-1', label: '论文成果', category: '论文合作' },
      { id: 't5', from: 'topic-1', to: 'project-1', label: '项目成果', category: '直接关系' },
      { id: 't6', from: 'topic-1', to: 'patent-1', label: '专利成果', category: '直接关系' },
    ],
  },
  'expert-colleague': {
    nodes: [
      serviceNode('core', '张明远', 'main', 220, 95, '科技专家', '同事 18', '任职履历已完成实体对齐。', 0.93),
      serviceNode('expert-1', '李佳宁', 'expert', 540, 95, '科技专家', '同事关系 1', '双方任职时间存在有效重叠。', 0.91),
      serviceNode('org-1', '自动化研究所', 'org', 380, 205, '共同机构', '任职重叠 4 年', '机构与部门层级已标准化。', 0.95),
      serviceNode('team-1', '知识工程项目组', 'org', 150, 345, '共同团队', '团队协作 1', '项目组成员名单同时命中双方。', 0.9),
      serviceNode('project-1', '联合项目2项', 'project', 380, 350, '科研项目', '期间成果 2', '项目执行时间位于同事关系时段内。', 0.88),
      serviceNode('paper-1', '合作成果6项', 'paper', 610, 345, '合作成果', '论文/报告 6', '成果时间位于同事关系时段内。', 0.89),
    ],
    edges: [
      { id: 'c1', from: 'core', to: 'expert-1', label: '同事关系', category: '同事' },
      { id: 'c2', from: 'core', to: 'org-1', label: '任职', category: '直接关系' },
      { id: 'c3', from: 'expert-1', to: 'org-1', label: '任职', category: '直接关系' },
      { id: 'c4', from: 'org-1', to: 'team-1', label: '团队归属', category: '同事' },
      { id: 'c5', from: 'org-1', to: 'project-1', label: '共同项目', category: '同事' },
      { id: 'c6', from: 'org-1', to: 'paper-1', label: '合作成果', category: '论文合作' },
    ],
  },
  'expert-alumni': {
    nodes: [
      serviceNode('core', '张明远', 'main', 220, 90, '科技专家', '校友 26', '博士阶段教育经历已核验。', 0.92),
      serviceNode('expert-1', '王青', 'expert', 540, 90, '科技专家', '校友关系 1', '双方教育经历存在有效匹配。', 0.89),
      serviceNode('org-1', '北京大学', 'org', 380, 195, '关联院校', '同校', '院校标准名称与统一标识一致。', 0.96),
      serviceNode('topic-1', '信息科学学院', 'topic', 150, 335, '院系专业', '同院系/同专业', '院系和专业信息匹配。', 0.9),
      serviceNode('paper-1', '共同论文4篇', 'paper', 380, 350, '学术互动', '互动 4', '校友后续共同发表论文。', 0.86),
      serviceNode('project-1', '联合项目2项', 'project', 610, 335, '合作互动', '互动 2', '校友后续共同参与科研项目。', 0.84),
    ],
    edges: [
      { id: 'a1', from: 'core', to: 'expert-1', label: '校友关系', category: '校友' },
      { id: 'a2', from: 'core', to: 'org-1', label: '就读', category: '校友' },
      { id: 'a3', from: 'expert-1', to: 'org-1', label: '就读', category: '校友' },
      { id: 'a4', from: 'org-1', to: 'topic-1', label: '院系归属', category: '校友' },
      { id: 'a5', from: 'core', to: 'paper-1', label: '学术互动', category: '论文合作' },
      { id: 'a6', from: 'expert-1', to: 'project-1', label: '项目合作', category: '直接关系' },
    ],
  },
  'paper-cooperation': {
    nodes: [
      serviceNode('core', '张明远', 'main', 215, 90, '科技专家', '合作论文 14', '作者身份与单位已核验。', 0.95),
      serviceNode('expert-1', '李佳宁', 'expert', 545, 90, '合作专家', '合作论文 14', '作者身份与单位已核验。', 0.94),
      serviceNode('paper-1', '合作论文14篇', 'paper', 380, 205, '论文成果', '总被引 1260', '双方共同出现在作者列表。', 0.93),
      serviceNode('org-1', '作者单位', 'org', 125, 340, '科研机构', '单位 2', '作者单位与专家任职信息一致。', 0.91),
      serviceNode('topic-1', '人工智能', 'topic', 310, 355, '论文主题', '方向 5', '论文关键词聚合为研究主题。', 0.9),
      serviceNode('venue-1', 'Q1/A类成果', 'project', 485, 355, '期刊会议级别', '高水平论文 9', '期刊与会议等级已标准化。', 0.88),
      serviceNode('expert-2', '核心合作团队', 'expert', 655, 340, '合作团队', '核心人员 7', '基于合作频次识别稳定团队。', 0.86),
    ],
    edges: [
      { id: 'pc1', from: 'core', to: 'expert-1', label: '论文合作', category: '论文合作' },
      { id: 'pc2', from: 'core', to: 'paper-1', label: '共同作者', category: '论文合作' },
      { id: 'pc3', from: 'expert-1', to: 'paper-1', label: '共同作者', category: '论文合作' },
      { id: 'pc4', from: 'paper-1', to: 'org-1', label: '作者单位', category: '直接关系' },
      { id: 'pc5', from: 'paper-1', to: 'topic-1', label: '研究主题', category: '间接关系' },
      { id: 'pc6', from: 'paper-1', to: 'venue-1', label: '发表级别', category: '直接关系' },
      { id: 'pc7', from: 'paper-1', to: 'expert-2', label: '团队识别', category: '论文合作' },
    ],
  },
  'enterprise-relation': {
    nodes: [
      serviceNode('core', '张明远', 'main', 220, 95, '科技专家', '关联企业 9', '专家身份与技术方向已标准化。', 0.94),
      serviceNode('company-1', '华南智能芯片', 'company', 540, 95, '重点科技企业', '关联专家 1', '企业主体和经营状态已核验。', 0.92),
      serviceNode('role-1', '技术顾问', 'topic', 380, 205, '企业角色', '角色类型 2', '工商与项目记录共同支持角色判断。', 0.89),
      serviceNode('project-1', '联合研发', 'project', 135, 345, '合作模式', '项目 3', '双方存在联合研发项目。', 0.9),
      serviceNode('topic-1', '芯片设计', 'topic', 330, 350, '合作领域', '领域 6', '合作内容与企业技术方向匹配。', 0.91),
      serviceNode('event-1', '经营状态正常', 'event', 520, 350, '经营状况', '风险 2', '企业经营与风险信息已关联。', 0.84),
      serviceNode('paper-1', '成果转化', 'paper', 665, 300, '合作成果', '转化成果 4', '专家成果与企业产品存在转化关系。', 0.87),
    ],
    edges: [
      { id: 'e1', from: 'core', to: 'company-1', label: '企业关联', category: '企业关联' },
      { id: 'e2', from: 'core', to: 'role-1', label: '担任角色', category: '企业关联' },
      { id: 'e3', from: 'company-1', to: 'role-1', label: '角色归属', category: '企业关联' },
      { id: 'e4', from: 'role-1', to: 'project-1', label: '联合研发', category: '直接关系' },
      { id: 'e5', from: 'role-1', to: 'topic-1', label: '合作领域', category: '企业关联' },
      { id: 'e6', from: 'company-1', to: 'event-1', label: '经营状态', category: '产业事件' },
      { id: 'e7', from: 'company-1', to: 'paper-1', label: '成果转化', category: '企业关联' },
    ],
  },
  'industry-chain-event': {
    nodes: [
      serviceNode('core', '芯片设计', 'main', 105, 210, '产业链节点', 'TOP 事件 10', '产业链节点已完成标准化。', 0.95),
      serviceNode('event-1', '材料专利授权', 'event', 330, 90, '重点事件', '影响力第 1', '事件影响力评分为 92.6。', 0.93),
      serviceNode('event-2', '智算中心扩容', 'event', 330, 210, '重点事件', '影响力第 2', '事件影响范围覆盖多个产业环节。', 0.9),
      serviceNode('event-3', '产业扶持政策', 'event', 330, 330, '重点事件', '影响力第 3', '政策事件与产业节点高度相关。', 0.88),
      serviceNode('expert-1', '关联专家18人', 'expert', 575, 80, '科技专家', '事件参与', '事件主体识别命中相关专家。', 0.88),
      serviceNode('company-1', '关联企业24家', 'company', 590, 205, '科技企业', '事件参与', '事件主体识别命中相关企业。', 0.87),
      serviceNode('topic-1', '风险与机遇', 'topic', 575, 340, '趋势研判', '风险等级中', '综合事件序列形成趋势判断。', 0.82),
    ],
    edges: [
      { id: 'ev1', from: 'core', to: 'event-1', label: 'TOP 1', category: '产业事件' },
      { id: 'ev2', from: 'core', to: 'event-2', label: 'TOP 2', category: '产业事件' },
      { id: 'ev3', from: 'core', to: 'event-3', label: 'TOP 3', category: '产业事件' },
      { id: 'ev4', from: 'event-1', to: 'expert-1', label: '关联专家', category: '产业事件' },
      { id: 'ev5', from: 'event-2', to: 'company-1', label: '关联企业', category: '产业事件' },
      { id: 'ev6', from: 'event-3', to: 'topic-1', label: '趋势影响', category: '产业事件' },
      { id: 'ev7', from: 'event-1', to: 'topic-1', label: '风险机会', category: '产业事件' },
    ],
  },
  'industry-chain-panorama': {
    nodes: [
      serviceNode('core', '人工智能计算链', 'main', 380, 65, '产业链', '节点 186/关系 420', '产业链实体与关系已完成汇聚。', 0.95, 1),
      serviceNode('topic-1', '上游基础资源', 'topic', 130, 190, '产业环节', '上游节点', '汇聚数据资源与算力芯片。', 0.92, 1),
      serviceNode('topic-2', '中游核心技术', 'topic', 380, 190, '产业环节', '中游节点', '汇聚知识图谱、机器学习与大模型。', 0.93, 1),
      serviceNode('topic-3', '下游应用场景', 'topic', 630, 190, '产业环节', '下游节点', '汇聚智能制造、医疗与交通场景。', 0.91, 1),
      serviceNode('company-1', '重点企业48家', 'company', 120, 335, '科技企业', '企业布局', '企业与产业环节建立布局关系。', 0.88, 2),
      serviceNode('expert-1', '核心专家群', 'expert', 305, 350, '科技专家', '专家支撑', '专家与关键技术建立研究关系。', 0.87, 2),
      serviceNode('project-1', '关键技术22项', 'project', 480, 350, '关键技术', '技术支撑', '技术节点覆盖产业链核心环节。', 0.9, 2),
      serviceNode('event-1', '产业动态事件', 'event', 660, 335, '产业事件', '动态更新', '事件影响已关联到产业链节点。', 0.84, 3),
    ],
    edges: [
      { id: 'p1', from: 'core', to: 'topic-1', label: '上游环节', category: '产业事件' },
      { id: 'p2', from: 'core', to: 'topic-2', label: '中游环节', category: '产业事件' },
      { id: 'p3', from: 'core', to: 'topic-3', label: '下游环节', category: '产业事件' },
      { id: 'p4', from: 'topic-1', to: 'topic-2', label: '资源供给', category: '间接关系' },
      { id: 'p5', from: 'topic-2', to: 'topic-3', label: '能力输出', category: '间接关系' },
      { id: 'p6', from: 'topic-1', to: 'company-1', label: '企业布局', category: '企业关联' },
      { id: 'p7', from: 'topic-2', to: 'expert-1', label: '专家支撑', category: '直接关系' },
      { id: 'p8', from: 'topic-2', to: 'project-1', label: '技术支撑', category: '直接关系' },
      { id: 'p9', from: 'topic-3', to: 'event-1', label: '事件影响', category: '产业事件' },
    ],
  },
}

const defaultServiceGraph: GraphPreset = {
  nodes: [
    {
      id: 'core',
      label: '张明远',
      nodeType: 'main',
      x: 382,
      y: 214,
      radius: 34,
      entityType: '科技专家',
      confidence: 0.94,
      relations: '命中关系 9',
      evidence: expertEvidence,
    },
    {
      id: 'expert-1',
      label: '李佳宁',
      nodeType: 'expert',
      x: 180,
      y: 118,
      radius: 28,
      entityType: '科技专家',
      confidence: 0.92,
      relations: '直接关系 1',
      evidence: ['路径深度为 2，命中学术关联和机构关联。'],
    },
    {
      id: 'org-1',
      label: '清华大学',
      nodeType: 'org',
      x: 578,
      y: 118,
      radius: 28,
      entityType: '机构团队',
      confidence: 0.88,
      relations: '机构关联 1',
      evidence: ['机构层级与任职信息一致。'],
    },
    {
      id: 'paper-1',
      label: '论文成果',
      nodeType: 'paper',
      x: 194,
      y: 316,
      radius: 30,
      entityType: '论文成果',
      confidence: 0.9,
      relations: '合作成果 1',
      evidence: ['按论文、专利、项目分类统计合作成果。'],
    },
    {
      id: 'topic-1',
      label: '产业事件',
      nodeType: 'topic',
      x: 586,
      y: 316,
      radius: 30,
      entityType: '产业事件',
      confidence: 0.77,
      relations: '事件关联 1',
      evidence: ['事件与专家、企业、人才构建关联。'],
    },
    {
      id: 'company-1',
      label: '科技企业',
      nodeType: 'company',
      x: 96,
      y: 208,
      radius: 20,
      entityType: '科技企业',
      confidence: 0.81,
      relations: '企业关联 1',
      evidence: ['标注专家在企业中的角色与合作领域。'],
    },
  ],
  edges: [
    { id: 's1', from: 'core', to: 'expert-1', label: '直接关系', category: '直接关系' },
    { id: 's2', from: 'core', to: 'org-1', label: '机构关联', category: '间接关系' },
    { id: 's3', from: 'core', to: 'paper-1', label: '合作成果', category: '论文合作' },
    { id: 's4', from: 'core', to: 'topic-1', label: '事件关联', category: '产业事件' },
    { id: 's5', from: 'expert-1', to: 'company-1', label: '企业角色', category: '企业关联' },
  ],
}

export function getServiceGraphPreset(serviceKey: string): GraphPreset {
  return serviceGraphPresets[serviceKey] ?? defaultServiceGraph
}

export const relationCategoryMap: Record<string, string[]> = {
  直接关系: ['直接关系', '论文合作', '同事', '校友', '企业关联'],
  间接关系: ['间接关系', '产业事件'],
  同事: ['同事'],
  校友: ['校友'],
  论文合作: ['论文合作'],
  企业关联: ['企业关联', '企业角色'],
  产业事件: ['产业事件'],
}

export function edgeMatchesFilter(category: string, filter: string): boolean {
  const allowed = relationCategoryMap[filter]
  if (!allowed) return true
  return allowed.includes(category)
}

export const queryTypeLabels: Record<string, string> = {
  科技专家: '科技专家',
  科技企业: '科技企业',
  论文成果: '论文成果',
  机构团队: '机构团队',
  产业链节点: '产业链节点',
}
