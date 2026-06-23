<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'

type MainTab = 'test' | 'developer'
type ResultTab = 'structured' | 'api'
type CodeTab = 'Python' | 'Node.js' | 'cURL'
type GraphNodeKey = string

interface GraphNode {
  key: GraphNodeKey
  title: string
  subtitle: string
  relation?: string
  x: number
  y: number
  width: number
  height: number
  kind: 'expert' | 'company'
}

interface RelationSubFunction {
  featureName: string
  apiPath: string
  nodes: GraphNode[]
}

interface RelationFeature {
  navLabel: string
  subFunctions: RelationSubFunction[]
}

const mainTab = ref<MainTab>('test')
const resultTab = ref<ResultTab>('structured')
const activeCodeTab = ref<CodeTab>('Python')
const showParams = ref(false)
const showTechPlan = ref(false)
const showFeatureMenu = ref(false)
const isReasoningExpanded = ref(true)
const activeFeatureLabel = ref('重点科技企业关系')
const activeSubFunctionName = ref('专家-企业关系构建')
const graphWidth = 1320
const graphHeight = 960
const graphZoom = ref(0.56)

const graphStageRef = ref<HTMLElement | null>(null)
const activeDrag = ref<{ key: GraphNodeKey; offsetX: number; offsetY: number } | null>(null)

function makeRelationGraph(
  centerTitle: string,
  targetPrefix: string,
  targetSubtitle: string,
  relations: string[],
): GraphNode[] {
  return [
    {
      key: 'expert',
      title: centerTitle,
      subtitle: '人工智能专家',
      x: 412,
      y: 292,
      width: 300,
      height: 94,
      kind: 'expert',
    },
    ...relations.map((relation, index) => {
      const positions = [
        { key: 'company1' as GraphNodeKey, x: 35, y: 45 },
        { key: 'company2' as GraphNodeKey, x: 685, y: 45 },
        { key: 'company3' as GraphNodeKey, x: 20, y: 500 },
        { key: 'company4' as GraphNodeKey, x: 700, y: 500 },
        { key: 'company5' as GraphNodeKey, x: 390, y: 610 },
      ]
      const position = positions[index]

      return {
        key: position.key,
        title: `${targetPrefix}${index + 1}：${['李佳宁', '王子涵', '陈思远', '赵明轩', '刘若溪'][index]}`,
        subtitle: targetSubtitle,
        relation,
        x: position.x,
        y: position.y,
        width: 360,
        height: 88,
        kind: 'company' as const,
      }
    }),
  ]
}

const relationFeatures: RelationFeature[] = [
  {
    navLabel: '科技专家直接关系',
    subFunctions: [
      {
        featureName: '科技专家直接关系构建',
        apiPath: '/api/v1/expert/direct-relation/build',
        nodes: makeRelationGraph('专家A：张明远', '专家', '科技专家', ['论文合作', '项目合作', '同事', '校友', '共同专利']),
      },
    ],
  },
  {
    navLabel: '科技节点间接关系',
    subFunctions: [
      {
        featureName: '科技节点间接关系构建',
        apiPath: '/api/v1/tech-node/indirect-relation/build',
        nodes: makeRelationGraph('节点A：人工智能', '节点', '科技节点', ['上位概念', '关联方向', '应用场景', '技术路径', '成果转化']),
      },
    ],
  },
  {
    navLabel: '科技两点合作成果',
    subFunctions: [
      {
        featureName: '科技两点合作成果构建',
        apiPath: '/api/v1/tech-node/collaboration-result/build',
        nodes: makeRelationGraph('节点A：人工智能', '成果', '合作成果', ['论文成果', '专利成果', '项目成果', '标准成果', '奖项成果']),
      },
    ],
  },
  {
    navLabel: '科技专家同事关系',
    subFunctions: [
      {
        featureName: '科技专家同事关系构建',
        apiPath: '/api/v1/expert/colleague-relation/build',
        nodes: makeRelationGraph('专家A：张明远', '专家', '科技专家', ['同单位', '同部门', '联合项目', '共同论文', '共同专利']),
      },
    ],
  },
  {
    navLabel: '科技专家校友关系',
    subFunctions: [
      {
        featureName: '科技专家校友关系构建',
        apiPath: '/api/v1/expert/alumni-relation/build',
        nodes: makeRelationGraph('专家A：张明远', '专家', '科技专家', ['本科校友', '硕士校友', '博士校友', '导师关系', '同实验室']),
      },
    ],
  },
  {
    navLabel: '专家论文合作关系',
    subFunctions: [
      {
        featureName: '专家论文合作关系构建',
        apiPath: '/api/v1/expert/paper-collaboration/build',
        nodes: makeRelationGraph('专家A：张明远', '论文', '合作论文', ['第一作者', '通讯作者', '共同作者', '同主题', '引用关系']),
      },
    ],
  },
  {
    navLabel: '重点科技企业关系',
    subFunctions: [
      {
        featureName: '专家-企业关系构建',
        apiPath: '/api/v1/kg-construction/expert-enterprise-relations/build',
        nodes: [],
      },
      { featureName: '角色与合作详情标注', apiPath: '/api/v1/kg-construction/relation-detail-annotations/annotate', nodes: [] },
      { featureName: '企业背景关联分析', apiPath: '/api/v1/kg-construction/enterprise-background-analyses/analyze', nodes: [] },
    ],
  },
  {
    navLabel: '产业链点事件关系',
    subFunctions: [
      {
        featureName: '产业链点事件关系构建',
        apiPath: '/api/v1/industry-chain/event-relation/build',
        nodes: makeRelationGraph('链点A：核心零部件', '事件', '产业链事件', ['供应中断', '产能扩张', '政策影响', '技术替代', '价格波动']),
      },
    ],
  },
  {
    navLabel: '科技产业链全景图',
    subFunctions: [
      {
        featureName: '科技产业链全景图构建',
        apiPath: '/api/v1/industry-chain/panorama/build',
        nodes: makeRelationGraph('链点A：核心零部件', '链点', '产业链节点', ['上游供应', '中游制造', '下游应用', '关键企业', '风险事件']),
      },
    ],
  },
]

const currentFeature = computed(
  () => relationFeatures.find((feature) => feature.navLabel === activeFeatureLabel.value) ?? relationFeatures[5],
)
const currentSubFunction = computed(
  () =>
    currentFeature.value.subFunctions.find((item) => item.featureName === activeSubFunctionName.value) ??
    currentFeature.value.subFunctions[0],
)
const selectedFeature = computed(() => currentSubFunction.value.featureName)
const featureOptions = computed(() => currentFeature.value.subFunctions.map((feature) => feature.featureName))
const currentApiPath = computed(() => currentSubFunction.value.apiPath)
const subFunctionKey = computed<'build' | 'annotate' | 'analyze'>(() => {
  const n = activeSubFunctionName.value
  if (n === '角色与合作详情标注') return 'annotate'
  if (n === '企业背景关联分析') return 'analyze'
  return 'build'
})
const graphNodes = ref<GraphNode[]>([])

const loading = ref(false)
const apiError = ref('')
const buildResult = ref<any>(null)

const activeError = computed(() => {
  if (subFunctionKey.value === 'annotate') return annotationError.value
  if (subFunctionKey.value === 'analyze') return analysisError.value
  return apiError.value
})
const activeLoading = computed(() => {
  if (subFunctionKey.value === 'annotate') return annotationLoading.value
  if (subFunctionKey.value === 'analyze') return analysisLoading.value
  return loading.value
})

async function loadEnterpriseRelation() {
  if (currentSubFunction.value.featureName !== '专家-企业关系构建') return
  loading.value = true
  apiError.value = ''
  try {
    const resp = await fetch(currentApiPath.value, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scholarId: params.value.scholarId,
        enterpriseId: params.value.enterpriseId,
        relationTypes: params.value.relationTypes,
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    buildResult.value = data
    // 画板：以人才为中心，企业均匀环绕
    const rels: any[] = Array.isArray(data.relations) ? data.relations : []
    const cx = graphWidth / 2
    const cy = graphHeight / 2
    const radius = 380
    const n = rels.length
    graphNodes.value = [
      { key: 'expert', title: `专家：${data.scholarName ?? params.value.scholarId}`, subtitle: '专家', x: cx - 150, y: cy - 47, width: 300, height: 94, kind: 'expert' },
      ...rels.map((r: any, i: number) => {
        const ang = (2 * Math.PI * i) / (n || 1) - Math.PI / 2
        const ccx = cx + radius * Math.cos(ang)
        const ccy = cy + radius * Math.sin(ang)
        return {
          key: `company${i + 1}` as GraphNodeKey,
          title: `企业：${r.enterpriseName ?? r.enterpriseId}`,
          subtitle: '企业',
          relation: r.relationType || '-',
          x: ccx - 180, y: ccy - 55, width: 360, height: 110, kind: 'company' as const,
        }
      }),
    ]
  } catch (e: any) {
    apiError.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

const companyNodes = computed(() => graphNodes.value.filter((node) => node.kind === 'company'))
const centerNode = computed(() => graphNodes.value.find((node) => node.kind === 'expert') ?? graphNodes.value[0])

function splitNodeTitle(title: string) {
  const [label, ...nameParts] = title.split('：')
  return {
    label: label || '节点',
    name: nameParts.join('：') || title,
  }
}

const dimensionChinese: Record<string, string> = {
  industry_status: '行业地位',
  core_tech: '核心技术',
  financial: '经营财务',
}

const detailRows = computed<(string | number)[][]>(() => {
  if (subFunctionKey.value === 'annotate') {
    const resp = annotationResp.value
    if (!resp) return []
    const period = resp.period ?? annotationParams.value.period
    return [
      ['关系ID', resp.relationId ?? annotationParams.value.relationId],
      ['角色', resp.roleLabel ?? '-'],
      ['角色等级', resp.roleLevel ?? '-'],
      ['角色类型', resp.roleType ?? annotationParams.value.roleType],
      ['技术领域', resp.techField ?? annotationParams.value.techField],
      ['周期', `${period?.start ?? ''} ~ ${period?.end ?? ''}`],
      ['标注结果', resp.annotated ? '成功' : '失败'],
    ]
  }
  if (subFunctionKey.value === 'analyze') {
    const resp = analysisResp.value
    if (!resp) return []
    const rows: (string | number)[][] = [['企业名称', resp.enterpriseName ?? '-']]
    const dims = resp.dimensions ?? {}
    Object.keys(dims).forEach((key) => {
      const d = dims[key]
      const label = dimensionChinese[key] ?? key
      const value = d?.available ? d.conclusion ?? '-' : d?.summary ?? '-'
      rows.push([label, value])
    })
    rows.push(['核心技术布局', resp.coreTechLayout ?? '-'])
    const dist = Array.isArray(resp.patentDistribution) ? resp.patentDistribution : []
    dist.forEach((p: any) => {
      rows.push([`CPC:${p.cpcSection ?? '-'}`, p.count ?? 0])
    })
    return rows
  }
  const center = centerNode.value
  if (!center) return []
  const centerInfo = splitNodeTitle(center.title)
  const rows: (string | number)[][] = [
    [centerInfo.label, centerInfo.name],
    [`${centerInfo.label}类型`, center.subtitle],
  ]

  companyNodes.value.forEach((node) => {
    const targetInfo = splitNodeTitle(node.title)
    rows.push([targetInfo.label, targetInfo.name])
    rows.push(['关系类型', node.relation ?? '-'])
  })

  return rows
})

const apiExample = computed(() => {
  if (subFunctionKey.value === 'annotate') {
    return JSON.stringify(
      annotationResp.value ?? {
        status: 'success',
        relationId: annotationParams.value.relationId,
        roleType: annotationParams.value.roleType,
        roleLabel: '',
        roleLevel: '',
        techField: annotationParams.value.techField,
        period: annotationParams.value.period,
        annotated: false,
      },
      null,
      2,
    )
  }
  if (subFunctionKey.value === 'analyze') {
    return JSON.stringify(
      analysisResp.value ?? {
        status: 'success',
        enterpriseId: analysisParams.value.enterpriseId,
        enterpriseName: '',
        dimensions: {},
        patentDistribution: [],
        coreTechLayout: '',
      },
      null,
      2,
    )
  }
  return JSON.stringify(
    buildResult.value ?? {
      status: 'success',
      scholarId: params.value.scholarId,
      scholarName: '',
      builtRelationId: `${params.value.scholarId}->${params.value.enterpriseId}@0`,
      relationTypes: params.value.relationTypes,
      effective: true,
      relations: [],
    },
    null,
    2,
  )
})

const params = ref({
  scholarId: 'E10001',
  enterpriseId: 'ENT001',
  relationTypes: ['employment'] as string[],
})

const relationTypeOptions = [
  { value: 'employment', label: '任职' },
  { value: 'advisor', label: '顾问' },
  { value: 'rd_cooperation', label: '研发合作' },
  { value: 'project_cooperation', label: '项目合作' },
  { value: 'tech_cooperation', label: '技术合作' },
]

const requestRows = computed<(string)[][]>(() => {
  if (subFunctionKey.value === 'annotate') {
    return [
      ['relationId', 'string', '是', '政企关系ID'],
      ['roleType', 'string', '是', '角色类型'],
      ['techField', 'string', '否', '技术领域'],
      ['period.start', 'string', '否', '开始日期'],
      ['period.end', 'string', '否', '结束日期'],
    ]
  }
  if (subFunctionKey.value === 'analyze') {
    return [
      ['enterpriseId', 'string', '是', '企业ID'],
      ['analysisDimensions', 'string[]', '是', '分析维度'],
      ['patentCPC', 'string[]', '否', '专利CPC分类号'],
    ]
  }
  return [
    ['scholarId', 'string', '是', '专家ID'],
    ['enterpriseId', 'string', '是', '企业ID'],
    ['relationTypes', 'string[]', '是', '关联关系类型（多选，英文编码）'],
  ]
})

const responseRows = computed<(string)[][]>(() => {
  if (subFunctionKey.value === 'annotate') {
    return [
      ['status', 'string', '状态'],
      ['relationId', 'string', '政企关系ID'],
      ['roleType', 'string', '角色类型'],
      ['roleLabel', 'string', '角色标签'],
      ['roleLevel', 'string', '角色等级'],
      ['techField', 'string', '技术领域'],
      ['period', 'object', '合作时段'],
      ['annotated', 'boolean', '标注结果'],
    ]
  }
  if (subFunctionKey.value === 'analyze') {
    return [
      ['status', 'string', '状态'],
      ['enterpriseId', 'string', '企业ID'],
      ['enterpriseName', 'string', '企业名称'],
      ['dimensions', 'object', '各维度分析'],
      ['dimensions[].available', 'boolean', '维度是否有数据'],
      ['dimensions[].conclusion', 'string', '维度结论'],
      ['dimensions[].summary', 'string', '降级摘要'],
      ['patentDistribution', 'array', '专利分布'],
      ['patentDistribution[].cpcSection', 'string', 'CPC部类'],
      ['patentDistribution[].count', 'int', '专利数'],
      ['coreTechLayout', 'string', '核心技术布局'],
    ]
  }
  return [
    ['status', 'string', '状态'],
    ['scholarId', 'string', '专家ID'],
    ['scholarName', 'string', '专家姓名'],
    ['builtRelationId', 'string', '构建的关系ID'],
    ['relationType', 'string', '关系类型标签'],
    ['effective', 'boolean', '生效标识'],
    ['relations', 'array', '该人才全部企业关系'],
    ['relations[].relationId', 'string', '关系ID'],
    ['relations[].enterpriseId', 'string', '企业ID'],
    ['relations[].enterpriseName', 'string', '企业名称'],
    ['relations[].relationType', 'string', '关系类型标签'],
  ]
})

// #2 角色与合作详情标注
const annotationParams = ref({
  relationId: 'S001->E001@0',
  roleType: 'chief_scientist',
  techField: '人工智能',
  period: { start: '2021-01-01', end: '2024-12-31' },
})
const roleOptions = [
  { value: 'chief_scientist', label: '首席科学家' },
  { value: 'cto', label: '技术总监' },
  { value: 'technical_advisor', label: '技术顾问' },
  { value: 'rd_lead', label: '研发负责人' },
  { value: 'engineer', label: '工程师' },
]
const annotationResp = ref<any>(null)
const annotationError = ref('')
const annotationLoading = ref(false)

async function loadAnnotation() {
  annotationLoading.value = true
  annotationError.value = ''
  try {
    const { data } = await axios.post(
      '/api/v1/kg-construction/relation-detail-annotations/annotate',
      annotationParams.value,
    )
    annotationResp.value = data
  } catch (e: any) {
    annotationError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    annotationLoading.value = false
  }
}

// #3 企业背景关联分析
const analysisParams = ref({
  enterpriseId: 'E001',
  analysisDimensions: ['industry_status', 'core_tech', 'financial'] as string[],
  patentCPC: 'G06N,G06F',
})
const dimensionOptions = [
  { value: 'industry_status', label: '行业地位' },
  { value: 'core_tech', label: '核心技术' },
  { value: 'financial', label: '经营财务' },
]
const analysisResp = ref<any>(null)
const analysisError = ref('')
const analysisLoading = ref(false)

async function loadAnalysis() {
  analysisLoading.value = true
  analysisError.value = ''
  try {
    const cpc = analysisParams.value.patentCPC
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    const { data } = await axios.post(
      '/api/v1/kg-construction/enterprise-background-analyses/analyze',
      {
        enterpriseId: analysisParams.value.enterpriseId,
        analysisDimensions: analysisParams.value.analysisDimensions,
        patentCPC: cpc,
      },
    )
    analysisResp.value = data
  } catch (e: any) {
    analysisError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    analysisLoading.value = false
  }
}

const pythonCodeExample = computed(() => {
  const url = `http://localhost:3001${currentApiPath.value}`
  if (subFunctionKey.value === 'annotate') {
    return `import requests

url = "${url}"
payload = {
    "relationId": "${annotationParams.value.relationId}",
    "roleType": "${annotationParams.value.roleType}",
    "techField": "${annotationParams.value.techField}",
    "period": {
        "start": "${annotationParams.value.period.start}",
        "end": "${annotationParams.value.period.end}"
    }
}

response = requests.post(url, json=payload)
print(response.json())`
  }
  if (subFunctionKey.value === 'analyze') {
    const cpc = analysisParams.value.patentCPC
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    return `import requests

url = "${url}"
payload = {
    "enterpriseId": "${analysisParams.value.enterpriseId}",
    "analysisDimensions": ${JSON.stringify(analysisParams.value.analysisDimensions)},
    "patentCPC": ${JSON.stringify(cpc)}
}

response = requests.post(url, json=payload)
print(response.json())`
  }
  return `import requests

url = "${url}"
payload = {
    "scholarId": "${params.value.scholarId}",
    "enterpriseId": "${params.value.enterpriseId}",
    "relationTypes": ${JSON.stringify(params.value.relationTypes)}
}

response = requests.post(url, json=payload)
print(response.json())`
})

const nodeCodeExample = computed(() => {
  const url = `http://localhost:3001${currentApiPath.value}`
  if (subFunctionKey.value === 'annotate') {
    return `const response = await fetch("${url}", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    relationId: "${annotationParams.value.relationId}",
    roleType: "${annotationParams.value.roleType}",
    techField: "${annotationParams.value.techField}",
    period: {
      start: "${annotationParams.value.period.start}",
      end: "${annotationParams.value.period.end}"
    }
  })
})

const data = await response.json()
console.log(data)`
  }
  if (subFunctionKey.value === 'analyze') {
    const cpc = analysisParams.value.patentCPC
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    return `const response = await fetch("${url}", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    enterpriseId: "${analysisParams.value.enterpriseId}",
    analysisDimensions: ${JSON.stringify(analysisParams.value.analysisDimensions)},
    patentCPC: ${JSON.stringify(cpc)}
  })
})

const data = await response.json()
console.log(data)`
  }
  return `const response = await fetch("${url}", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    scholarId: "${params.value.scholarId}",
    enterpriseId: "${params.value.enterpriseId}",
    relationTypes: ${JSON.stringify(params.value.relationTypes)}
  })
})

const data = await response.json()
console.log(data)`
})

const curlCodeExample = computed(() => {
  const url = `http://localhost:3001${currentApiPath.value}`
  if (subFunctionKey.value === 'annotate') {
    return `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "relationId": "${annotationParams.value.relationId}",
    "roleType": "${annotationParams.value.roleType}",
    "techField": "${annotationParams.value.techField}",
    "period": {
      "start": "${annotationParams.value.period.start}",
      "end": "${annotationParams.value.period.end}"
    }
  }'`
  }
  if (subFunctionKey.value === 'analyze') {
    const cpc = analysisParams.value.patentCPC
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    return `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "enterpriseId": "${analysisParams.value.enterpriseId}",
    "analysisDimensions": ${JSON.stringify(analysisParams.value.analysisDimensions)},
    "patentCPC": ${JSON.stringify(cpc)}
  }'`
  }
  return `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "scholarId": "${params.value.scholarId}",
    "enterpriseId": "${params.value.enterpriseId}",
    "relationTypes": ${JSON.stringify(params.value.relationTypes)}
  }'`
})

const codeExample = computed(() => {
  if (activeCodeTab.value === 'Node.js') return nodeCodeExample.value
  if (activeCodeTab.value === 'cURL') return curlCodeExample.value
  return pythonCodeExample.value
})

const pythonCodeLines = computed(() => [
  [{ text: 'import requests', tone: 'keyword' }],
  [],
  [
    { text: 'url', tone: 'plain' },
    { text: ' = ', tone: 'muted' },
    { text: `"http://localhost:3001${currentApiPath.value}"`, tone: 'soft' },
  ],
  [
    { text: 'payload', tone: 'plain' },
    { text: ' = ', tone: 'muted' },
    { text: '{', tone: 'plain' },
  ],
  [
    { text: '  "scholarId"', tone: 'string' },
    { text: ': ', tone: 'muted' },
    { text: `"${params.value.scholarId}"`, tone: 'string' },
    { text: ',', tone: 'plain' },
  ],
  [
    { text: '  "enterpriseId"', tone: 'string' },
    { text: ': ', tone: 'muted' },
    { text: `"${params.value.enterpriseId}"`, tone: 'string' },
    { text: ',', tone: 'plain' },
  ],
  [
    { text: '  "relationTypes"', tone: 'string' },
    { text: ': ', tone: 'muted' },
    { text: `${JSON.stringify(params.value.relationTypes)}`, tone: 'string' },
  ],
  [{ text: '}', tone: 'plain' }],
  [],
  [
    { text: 'response', tone: 'keyword' },
    { text: ' = ', tone: 'muted' },
    { text: 'requests.post', tone: 'keyword' },
    { text: '(url, json=payload)', tone: 'plain' },
  ],
  [
    { text: 'print', tone: 'keyword' },
    { text: '(response.json())', tone: 'plain' },
  ],
])

const renderedCodeLines = computed(() =>
  subFunctionKey.value === 'build' && activeCodeTab.value === 'Python' ? pythonCodeLines.value : null,
)

const flowSteps = [
  ['input', '输入数据', '接收专家ID、企业ID、专家企业关系的测试参数'],
  ['standardize', '标准化处理', '汇聚专家画像、企业标签、成果与合作记录等图谱数据'],
  ['reasoning', '关系推理', '基于任职、合作与企业标签规则，推理专家-企业关系'],
  ['output', '结果输出', '输出专家信息、企业关系列表和执行状态等结构化结果'],
]

function dispatchLoader() {
  const key = subFunctionKey.value
  if (key === 'annotate') loadAnnotation()
  else if (key === 'analyze') loadAnalysis()
  else loadEnterpriseRelation()
}

function runTest() {
  dispatchLoader()
  resultTab.value = 'structured'
}

function saveParamsAndRun() {
  showParams.value = false
  dispatchLoader()
}

function cloneNodes(nodes: GraphNode[]) {
  return nodes.map((node) => ({ ...node }))
}

function selectFeatureByNav(navLabel: string) {
  const feature = relationFeatures.find((item) => item.navLabel === navLabel)
  if (!feature) return
  const firstSubFunction = feature.subFunctions[0]

  activeFeatureLabel.value = feature.navLabel
  activeSubFunctionName.value = firstSubFunction.featureName
  graphNodes.value = cloneNodes(firstSubFunction.nodes)
  resultTab.value = 'structured'
  showFeatureMenu.value = false
}

function selectFeatureByName(featureName: string) {
  const subFunction = currentFeature.value.subFunctions.find((item) => item.featureName === featureName)
  if (!subFunction) return

  activeSubFunctionName.value = subFunction.featureName
  graphNodes.value = cloneNodes(subFunction.nodes)
  buildResult.value = null
  annotationResp.value = null
  analysisResp.value = null
  resultTab.value = 'structured'
  showFeatureMenu.value = false
}

function getNode(key: GraphNodeKey) {
  return graphNodes.value.find((node) => node.key === key)
}

function nodeStyle(node: GraphNode) {
  return {
    left: `${node.x}px`,
    top: `${node.y}px`,
    width: `${node.width}px`,
    height: `${node.height}px`,
    zIndex: activeDrag.value?.key === node.key ? 6 : 2,
  }
}

const graphStageStyle = computed(() => ({
  width: `${graphWidth}px`,
  height: `${graphHeight}px`,
  transform: `translate(-50%, -50%) scale(${graphZoom.value})`,
}))

function nodeCenter(node: GraphNode) {
  return {
    x: node.x + node.width / 2,
    y: node.y + node.height / 2,
  }
}

function boundaryPoint(node: GraphNode, toward: { x: number; y: number }) {
  const center = nodeCenter(node)
  const dx = toward.x - center.x
  const dy = toward.y - center.y
  const halfWidth = node.width / 2
  const halfHeight = node.height / 2

  if (dx === 0 && dy === 0) return center

  const scaleX = dx === 0 ? Number.POSITIVE_INFINITY : halfWidth / Math.abs(dx)
  const scaleY = dy === 0 ? Number.POSITIVE_INFINITY : halfHeight / Math.abs(dy)
  const scale = Math.min(scaleX, scaleY)

  return {
    x: center.x + dx * scale,
    y: center.y + dy * scale,
  }
}

function relationPath(node: GraphNode) {
  const expert = getNode('expert')
  if (!expert) return ''

  const from = nodeCenter(expert)
  const to = nodeCenter(node)
  const start = boundaryPoint(expert, to)
  const end = boundaryPoint(node, from)
  const verticalGap = Math.abs(end.y - start.y)
  const control = {
    x: (start.x + end.x) / 2,
    y: (start.y + end.y) / 2 + (end.y < start.y ? -verticalGap * 0.42 : verticalGap * 0.18),
  }

  return `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`
}

function relationLabelStyle(node: GraphNode) {
  const expert = getNode('expert')
  if (!expert) return {}

  const from = nodeCenter(expert)
  const to = nodeCenter(node)
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  const normal = {
    x: (-dy / length) * 28,
    y: (dx / length) * 28,
  }
  const directionOffset = to.y < from.y ? -12 : 12

  return {
    left: `${(from.x + to.x) / 2 + normal.x - 34}px`,
    top: `${(from.y + to.y) / 2 + normal.y + directionOffset - 18}px`,
  }
}

function relationTone(relation = '') {
  if (relation === '任职') return 'relation-blue'
  if (relation === '顾问') return 'relation-purple'
  return 'relation-orange'
}

function relationMarker(relation = '') {
  if (relation === '任职') return 'url(#arrow-blue)'
  if (relation === '顾问') return 'url(#arrow-purple)'
  return 'url(#arrow-orange)'
}

function startDrag(event: PointerEvent, node: GraphNode) {
  const stage = graphStageRef.value
  if (!stage) return

  const rect = stage.getBoundingClientRect()
  const scaleX = graphWidth / rect.width
  const scaleY = graphHeight / rect.height
  activeDrag.value = {
    key: node.key,
    offsetX: (event.clientX - rect.left) * scaleX - node.x,
    offsetY: (event.clientY - rect.top) * scaleY - node.y,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function dragNode(event: PointerEvent) {
  const drag = activeDrag.value
  const stage = graphStageRef.value
  if (!drag || !stage) return

  const node = getNode(drag.key)
  if (!node) return

  const rect = stage.getBoundingClientRect()
  const scaleX = graphWidth / rect.width
  const scaleY = graphHeight / rect.height
  const nextX = (event.clientX - rect.left) * scaleX - drag.offsetX
  const nextY = (event.clientY - rect.top) * scaleY - drag.offsetY

  node.x = Math.max(0, Math.min(graphWidth - node.width, nextX))
  node.y = Math.max(0, Math.min(graphHeight - node.height, nextY))
}

function stopDrag() {
  activeDrag.value = null
}

function zoomGraph(event: WheelEvent) {
  event.preventDefault()
  const nextZoom = graphZoom.value + (event.deltaY > 0 ? -0.06 : 0.06)
  graphZoom.value = Math.max(0.55, Math.min(1.25, Number(nextZoom.toFixed(2))))
}

</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64">
            <defs>
              <path id="logoTextTop" d="M12 31a20 20 0 0 1 40 0" />
              <path id="logoTextBottom" d="M52 35a20 20 0 0 1-40 0" />
            </defs>
            <circle class="logo-ring-outer" cx="32" cy="32" r="29" />
            <circle class="logo-ring-inner" cx="32" cy="32" r="22" />
            <text class="logo-cn">
              <textPath href="#logoTextTop" startOffset="50%" text-anchor="middle">赛知图谱科技馆</textPath>
            </text>
            <text class="logo-en">
              <textPath href="#logoTextBottom" startOffset="50%" text-anchor="middle">ScienceCorpus</textPath>
            </text>
            <path class="logo-brain" d="M25 24c-4 1-7 4-7 8 0 5 4 8 9 8h12c5 0 8-4 8-9 0-5-4-9-9-9-2-4-8-5-13-2" />
            <path class="logo-brain" d="M24 27c4 0 6 2 7 5" />
            <path class="logo-brain" d="M34 23c1 4 0 7-3 9" />
            <path class="logo-brain" d="M39 28c-2 2-5 3-8 2" />
            <path class="logo-line" d="M25 39v8" />
            <path class="logo-line" d="M32 39v13" />
            <path class="logo-line" d="M39 39v8" />
            <circle class="logo-dot" cx="25" cy="48" r="1.8" />
            <circle class="logo-dot" cx="32" cy="53" r="1.8" />
            <circle class="logo-dot" cx="39" cy="48" r="1.8" />
          </svg>
        </span>
        <strong>知识图谱平台</strong>
        <button class="sidebar-toggle" type="button" aria-label="折叠侧边栏">
          <span></span>
          <span></span>
          <span></span>
        </button>
      </div>

      <nav class="nav-list" aria-label="主导航">
        <button class="nav-item" type="button">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <circle cx="7" cy="6" r="3" />
              <circle cx="17" cy="6" r="3" />
              <circle cx="7" cy="18" r="3" />
              <path d="M10 6h4" />
              <path d="M7 9v6" />
              <path d="M10 18h8" />
            </svg>
          </span>
          <span>流程编排</span>
          <span class="nav-caret" aria-hidden="true"></span>
        </button>
        <button class="nav-item" type="button">
          <span class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <rect x="8" y="3" width="8" height="5" rx="1.5" />
              <circle cx="5" cy="19" r="2" />
              <circle cx="12" cy="19" r="2" />
              <circle cx="19" cy="19" r="2" />
              <path d="M12 8v6" />
              <path d="M5 17v-3h14v3" />
            </svg>
          </span>
          <span>图谱服务</span>
        </button>
        <section class="nav-section">
          <button class="nav-item expanded" type="button" @click="isReasoningExpanded = !isReasoningExpanded">
            <span class="nav-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="5" r="2.2" />
                <circle cx="5" cy="12" r="2.2" />
                <circle cx="19" cy="12" r="2.2" />
                <circle cx="12" cy="19" r="2.2" />
                <path d="M10.3 6.5L6.7 10.3" />
                <path d="M13.7 6.5l3.6 3.8" />
                <path d="M6.7 13.7l3.6 3.8" />
                <path d="M17.3 13.7l-3.6 3.8" />
                <path d="M9 12h6" />
              </svg>
            </span>
            <span>知识推理服务</span>
            <span class="nav-caret" :class="{ expanded: isReasoningExpanded }" aria-hidden="true"></span>
          </button>
          <div v-if="isReasoningExpanded" class="nav-children">
            <button
              v-for="feature in relationFeatures"
              :key="feature.navLabel"
              class="nav-child"
              :class="{ active: feature.navLabel === activeFeatureLabel }"
              type="button"
              @click="selectFeatureByNav(feature.navLabel)"
            >
              {{ feature.navLabel }}
            </button>
          </div>
        </section>
      </nav>

      <div class="sidebar-user">
        <span class="user-avatar" aria-hidden="true"></span>
        <strong>Ben</strong>
        <button class="user-message" type="button" aria-label="消息"></button>
      </div>
    </aside>

    <main class="workspace">
      <section class="page-card">
        <div class="module-head">
          <div class="tabbar" role="tablist" aria-label="功能页签">
            <button
              class="main-tab"
              :class="{ active: mainTab === 'test' }"
              type="button"
              @click="mainTab = 'test'"
            >
              算法测试
            </button>
            <button
              class="main-tab"
              :class="{ active: mainTab === 'developer' }"
              type="button"
              @click="mainTab = 'developer'"
            >
              开发者接口
            </button>
          </div>
          <button class="text-action" type="button" @click="showTechPlan = true">
            <span class="info-icon" data-tooltip="查看技术方案">i</span>
            技术方案
          </button>
        </div>

        <div class="control-line" :class="{ 'developer-control-line': mainTab === 'developer' }">
          <div class="feature-line">
            <span>子功能名称:</span>
            <div class="feature-dropdown">
              <button
                class="feature-select"
                :class="{ open: showFeatureMenu }"
                type="button"
                aria-haspopup="listbox"
                :aria-expanded="showFeatureMenu"
                @click="showFeatureMenu = !showFeatureMenu"
              >
                <span>{{ selectedFeature }}</span>
                <span class="select-arrow" aria-hidden="true"></span>
              </button>
              <div v-if="showFeatureMenu" class="feature-menu" role="listbox">
                <button
                  v-for="option in featureOptions"
                  :key="option"
                  class="feature-option"
                  :class="{ active: selectedFeature === option }"
                  type="button"
                  role="option"
                  :aria-selected="selectedFeature === option"
                  @click="selectFeatureByName(option)"
                >
                  {{ option }}
                </button>
              </div>
            </div>
            <span class="info-icon" data-tooltip="当前子功能用于构建专家与重点企业之间的关系图谱">i</span>
          </div>

          <template v-if="mainTab === 'developer'">
            <div class="inline-api-field">
              <span>接口路径：</span>
              <div class="inline-input">{{ currentApiPath }}</div>
            </div>
            <div class="inline-method">
              <span>请求方法：</span>
              <strong>POST</strong>
            </div>
          </template>

          <div v-if="mainTab === 'test'" class="actions">
            <button class="secondary-button" type="button" @click="showParams = true">参数设置</button>
            <button class="primary-button" type="button" @click="runTest">执行测试</button>
          </div>
        </div>

        <template v-if="mainTab === 'test'">
          <div class="test-grid" :class="{ 'single-column': subFunctionKey !== 'build' }">
            <section v-if="subFunctionKey === 'build'" class="graph-panel" aria-label="企业关系图谱">
              <div class="graph-canvas" @wheel="zoomGraph">
                <div
                  ref="graphStageRef"
                  class="graph-stage"
                  :style="graphStageStyle"
                  @pointermove="dragNode"
                  @pointerup="stopDrag"
                  @pointercancel="stopDrag"
                  @pointerleave="stopDrag"
                >
                  <svg class="graph-lines" :viewBox="`0 0 ${graphWidth} ${graphHeight}`" aria-hidden="true">
                    <defs>
                      <marker
                        id="arrow-blue"
                        viewBox="0 0 10 10"
                        refX="9"
                        refY="5"
                        markerWidth="9"
                        markerHeight="9"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2f7cff" />
                      </marker>
                      <marker
                        id="arrow-purple"
                        viewBox="0 0 10 10"
                        refX="9"
                        refY="5"
                        markerWidth="9"
                        markerHeight="9"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b5cf6" />
                      </marker>
                      <marker
                        id="arrow-orange"
                        viewBox="0 0 10 10"
                        refX="9"
                        refY="5"
                        markerWidth="9"
                        markerHeight="9"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
                      </marker>
                    </defs>
                    <path
                      v-for="node in companyNodes"
                      :key="`${node.key}-path`"
                      class="relation-edge"
                      :class="relationTone(node.relation)"
                      :d="relationPath(node)"
                      :marker-end="relationMarker(node.relation)"
                    />
                  </svg>

                  <span
                    v-for="node in companyNodes"
                    :key="`${node.key}-label`"
                    class="relation-label"
                    :class="relationTone(node.relation)"
                    :style="relationLabelStyle(node)"
                  >
                    {{ node.relation }}
                  </span>

                <div
                  v-for="node in graphNodes"
                  :key="node.key"
                  class="graph-node"
                  :class="[{ dragging: activeDrag?.key === node.key }, node.kind === 'expert' ? 'expert-node' : 'company-node']"
                  :style="nodeStyle(node)"
                  @pointerdown="startDrag($event, node)"
                >
                  <strong>{{ node.title }}</strong>
                  <span>{{ node.subtitle }}</span>
                </div>
                </div>
              </div>
            </section>

            <aside class="result-panel">
              <div class="result-tabs">
                <button
                  :class="{ active: resultTab === 'structured' }"
                  type="button"
                  @click="resultTab = 'structured'"
                >
                  结构化结果
                </button>
                <button
                  :class="{ active: resultTab === 'api' }"
                  type="button"
                  @click="resultTab = 'api'"
                >
                  API结果示例
                </button>
              </div>

              <div v-if="resultTab === 'structured'" class="detail-list">
                <div v-if="activeLoading" class="detail-row"><span>状态</span><strong>加载中…</strong></div>
                <div v-else-if="activeError" class="detail-row detail-error"><span>错误</span><strong>{{ activeError }}</strong></div>
                <template v-else>
                  <div v-for="row in detailRows" :key="`${row[0]}-${row[1]}`" class="detail-row">
                    <span>{{ row[0] }}</span>
                    <strong>{{ row[1] }}</strong>
                  </div>
                  <div v-if="detailRows.length === 0" class="detail-row"><span>提示</span><strong>点击「执行测试」查看结果</strong></div>
                </template>
              </div>
              <pre v-else class="api-code">{{ apiExample }}</pre>
            </aside>
          </div>
        </template>

        <template v-else>
          <div class="developer-surface">
            <div class="table-grid">
              <section class="doc-table">
                <h2>请求参数</h2>
                <div class="doc-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>字段名</th>
                      <th>类型</th>
                      <th>必填</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in requestRows" :key="row[0]">
                      <td>{{ row[0] }}</td>
                      <td>{{ row[1] }}</td>
                      <td>{{ row[2] }}</td>
                      <td>{{ row[3] }}</td>
                    </tr>
                  </tbody>
                </table>
                </div>
              </section>

              <section class="doc-table">
                <h2>返回字段</h2>
                <div class="doc-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>字段名</th>
                      <th>类型</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in responseRows" :key="row[0]">
                      <td>{{ row[0] }}</td>
                      <td>{{ row[1] }}</td>
                      <td>{{ row[2] }}</td>
                    </tr>
                  </tbody>
                </table>
                </div>
              </section>
            </div>

            <section class="code-panel">
              <div class="code-head">
                <h2>代码示例</h2>
                <div class="code-tabs">
                  <button
                    :class="{ active: activeCodeTab === 'Python' }"
                    type="button"
                    @click="activeCodeTab = 'Python'"
                  >
                    Python
                  </button>
                  <button
                    :class="{ active: activeCodeTab === 'Node.js' }"
                    type="button"
                    @click="activeCodeTab = 'Node.js'"
                  >
                    Node.js
                  </button>
                  <button
                    :class="{ active: activeCodeTab === 'cURL' }"
                    type="button"
                    @click="activeCodeTab = 'cURL'"
                  >
                    cURL
                  </button>
                </div>
              </div>
              <div v-if="renderedCodeLines" class="highlight-code" aria-label="Python代码示例">
                <div v-for="(line, index) in renderedCodeLines" :key="index" class="code-line">
                  <span class="line-number">{{ index + 1 }}</span>
                  <span class="line-content">
                    <template v-for="(part, partIndex) in line" :key="partIndex">
                      <span :class="`code-${part.tone}`">{{ part.text }}</span>
                    </template>
                  </span>
                </div>
              </div>
              <pre v-else>{{ codeExample }}</pre>
              <button class="copy-button" type="button" aria-label="复制代码">□</button>
            </section>
          </div>
        </template>
      </section>
    </main>

    <div v-if="showParams" class="modal-mask" role="dialog" aria-modal="true" aria-label="测试参数设置">
      <form class="param-modal" @submit.prevent="saveParamsAndRun">
        <header>
          <h2>
            <span class="param-title-icon" aria-hidden="true">
              <svg viewBox="0 0 20 20">
                <circle cx="10" cy="10" r="2.5" />
                <path d="M10 2.5v2" />
                <path d="M10 15.5v2" />
                <path d="M2.5 10h2" />
                <path d="M15.5 10h2" />
                <path d="M4.7 4.7l1.4 1.4" />
                <path d="M13.9 13.9l1.4 1.4" />
                <path d="M15.3 4.7l-1.4 1.4" />
                <path d="M6.1 13.9l-1.4 1.4" />
              </svg>
            </span>
            测试参数设置
          </h2>
          <span class="required-hint"><b>*</b> 为必填项</span>
          <button class="icon-button" type="button" aria-label="关闭" @click="showParams = false">×</button>
        </header>

        <template v-if="subFunctionKey === 'build'">
          <label class="param-field required">
            <span>scholarId</span>
            <input v-model="params.scholarId" placeholder="专家ID" />
          </label>
          <label class="param-field required">
            <span>enterpriseId</span>
            <input v-model="params.enterpriseId" placeholder="企业ID" />
          </label>
          <label class="param-field required">
            <span>relationTypes</span>
            <div class="param-checkbox-group">
              <label v-for="o in relationTypeOptions" :key="o.value" class="param-checkbox">
                <input type="checkbox" :value="o.value" v-model="params.relationTypes" />
                <span>{{ o.label }}</span>
              </label>
            </div>
          </label>
        </template>

        <template v-else-if="subFunctionKey === 'annotate'">
          <label class="param-field required">
            <span>relationId</span>
            <input v-model="annotationParams.relationId" placeholder="政企关系ID" />
          </label>
          <label class="param-field required">
            <span>roleType</span>
            <select v-model="annotationParams.roleType">
              <option v-for="o in roleOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </label>
          <label class="param-field">
            <span>techField</span>
            <input v-model="annotationParams.techField" placeholder="技术领域" />
          </label>
          <label class="param-field">
            <span>period.start</span>
            <input v-model="annotationParams.period.start" placeholder="开始日期" />
          </label>
          <label class="param-field">
            <span>period.end</span>
            <input v-model="annotationParams.period.end" placeholder="结束日期" />
          </label>
        </template>

        <template v-else-if="subFunctionKey === 'analyze'">
          <label class="param-field required">
            <span>enterpriseId</span>
            <input v-model="analysisParams.enterpriseId" placeholder="企业ID" />
          </label>
          <label class="param-field required">
            <span>analysisDimensions</span>
            <div class="param-checkbox-group">
              <label v-for="o in dimensionOptions" :key="o.value" class="param-checkbox">
                <input type="checkbox" :value="o.value" v-model="analysisParams.analysisDimensions" />
                <span>{{ o.label }}</span>
              </label>
            </div>
          </label>
          <label class="param-field">
            <span>patentCPC</span>
            <input v-model="analysisParams.patentCPC" placeholder="专利CPC（逗号分隔）" />
          </label>
        </template>

        <footer>
          <button class="secondary-button" type="button" @click="showParams = false">取消</button>
          <button class="primary-button" type="submit">保存并执行</button>
        </footer>
      </form>
    </div>

    <div v-if="showTechPlan" class="modal-mask" role="dialog" aria-modal="true" aria-label="技术方案">
      <section class="tech-modal">
        <header>
          <h2>技术方案</h2>
          <button class="icon-button" type="button" aria-label="关闭" @click="showTechPlan = false">×</button>
        </header>

        <article>
          <h3>功能描述</h3>
          <p>
            关联科技专家与重点企业主题，构建任职、顾问、研发合作等多类型实体关系，完善产学研关联图谱。
          </p>
        </article>

        <article>
          <h3>推理流程</h3>
          <div class="flow-grid">
            <template v-for="(step, index) in flowSteps" :key="step[1]">
              <div class="flow-card">
                <span class="flow-icon" aria-hidden="true">
                  <svg v-if="step[0] === 'input'" viewBox="0 0 32 32">
                    <rect x="6" y="6" width="20" height="16" rx="2.5" />
                    <path d="M16 10v8" />
                    <path d="M12.5 14.5L16 18l3.5-3.5" />
                    <path d="M12 26h8" />
                    <path d="M16 22v4" />
                  </svg>
                  <svg v-else-if="step[0] === 'standardize'" viewBox="0 0 32 32">
                    <path d="M7 9h7" />
                    <path d="M20 9h5" />
                    <circle cx="17" cy="9" r="3" />
                    <path d="M7 16h14" />
                    <path d="M27 16h-1" />
                    <circle cx="24" cy="16" r="3" />
                    <path d="M7 23h4" />
                    <path d="M17 23h8" />
                    <circle cx="14" cy="23" r="3" />
                  </svg>
                  <svg v-else-if="step[0] === 'reasoning'" viewBox="0 0 32 32">
                    <circle cx="8" cy="9" r="3" />
                    <circle cx="23" cy="8" r="3" />
                    <circle cx="24" cy="23" r="3" />
                    <circle cx="9" cy="22" r="3" />
                    <path d="M11 10l9 10" />
                    <path d="M20 9l-8 11" />
                    <path d="M12 22h9" />
                  </svg>
                  <svg v-else viewBox="0 0 32 32">
                    <path d="M9 6h12l4 4v13H9z" />
                    <path d="M21 6v5h5" />
                    <path d="M13 14h8" />
                    <path d="M13 18h7" />
                    <circle cx="22" cy="23" r="3" />
                    <path d="M24 25l3 3" />
                  </svg>
                </span>
                <strong>{{ step[1] }}</strong>
                <p>{{ step[2] }}</p>
              </div>
              <span v-if="index < flowSteps.length - 1" class="flow-arrow">→</span>
            </template>
          </div>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped>
.test-grid.single-column {
  grid-template-columns: 1fr;
}

.panel {
  margin-top: 24px;
  padding: 20px 24px;
  background: var(--panel);
  border: 1px solid #e6ebf2;
  border-radius: 12px;
}

.panel h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.params {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.params input[type='text'],
.params input:not([type]),
.params select {
  padding: 8px 12px;
  border: 1px solid #d0d7de;
  border-radius: 8px;
  font-size: 14px;
  min-width: 120px;
  background: #fff;
}

.params input[type='checkbox'] {
  margin-right: 4px;
}

.param-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: #334155;
  cursor: pointer;
}

.param-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.result {
  padding: 12px 0;
  font-size: 14px;
  color: #334155;
  line-height: 1.7;
}

.result p {
  margin: 4px 0;
}

.panel-dimension {
  margin: 6px 0;
}

.panel-dimension strong {
  color: #1f2937;
  margin-right: 8px;
}

.panel-error {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #fff1f2;
  border: 1px solid #fecdd3;
  border-radius: 8px;
  color: #be123c;
  font-size: 13px;
}

.detail-error strong {
  color: #be123c;
}
</style>
