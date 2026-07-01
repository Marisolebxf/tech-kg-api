<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { http } from '../../api/http'
import iconClose from '../../assets/icons/icon-close.svg'
import iconCopy from '../../assets/icons/icon-copy.svg'
import iconInfo from '../../assets/icons/icon-info.svg'
import iconModalSetting from '../../assets/icons/icon-modal-setting.svg'
import iconSelectArrow from '../../assets/icons/icon-select-arrow.svg'

type SubKey = 'build' | 'annotate' | 'analyze' | 'mining'

interface GraphNode {
  key: string
  title: string
  subtitle: string
  relation?: string
  roleKey?: string
  x: number
  y: number
  width: number
  height: number
  kind: 'expert' | 'company' | 'role'
}

const GW = 1320
const GH = 960

const mainTab = ref<'test' | 'developer'>('test')
const resultTab = ref<'structured' | 'api'>('structured')
const activeCode = ref<'python' | 'node' | 'curl'>('python')
const showConfig = ref(false)
const showTech = ref(false)
const miningDimsOpen = ref(false)
const copied = ref(false)

const subFunctions = [
  {
    key: 'build' as SubKey,
    name: '专家-企业关系构建',
    endpoint: '/v1/kg-construction/expert-enterprise-relations/build',
  },
  {
    key: 'annotate' as SubKey,
    name: '角色与合作详情标注',
    endpoint: '/v1/kg-construction/relation-detail-annotations/annotate',
  },
  {
    key: 'analyze' as SubKey,
    name: '企业背景关联分析',
    endpoint: '/v1/kg-construction/enterprise-background-analyses/analyze',
  },
  {
    key: 'mining' as SubKey,
    name: '专家企业关系挖掘',
    endpoint: '/v1/kg-construction/expert-enterprise-mining/mine',
  },
]
const activeSub = ref<SubKey>('build')
const currentSub = computed(
  () => subFunctions.find((s) => s.key === activeSub.value) ?? subFunctions[0],
)
// http 客户端 baseURL 为 '/api'，endpoint 用 '/v1/...'；显示与代码示例用完整 '/api/v1/...' 路径
const apiPath = computed(() => '/api' + currentSub.value.endpoint)

interface OptionItem {
  value?: string
  label?: string
  scholarId?: string
  name?: string
  enterpriseId?: string
  relationId?: string
}
interface Options {
  scholars: OptionItem[]
  enterprises: OptionItem[]
  edges: OptionItem[]
  relationTypes: OptionItem[]
  roles: OptionItem[]
  dimensions: OptionItem[]
  techFields: string[]
  cpcCodes: string[]
}
const options = ref<Options>({
  scholars: [],
  enterprises: [],
  edges: [],
  relationTypes: [],
  roles: [],
  dimensions: [],
  techFields: [],
  cpcCodes: [],
})

const buildParams = ref({
  scholarId: '',
  enterpriseId: '',
  relationTypes: ['employment'] as string[],
})
const annotateParams = ref({
  relationId: '',
  roleType: 'chief_scientist',
  techField: '人工智能',
  period: { start: '2021-01-01', end: '2024-12-31' },
})
const analyzeParams = ref({
  enterpriseId: '',
  analysisDimensions: ['industry_status', 'core_tech', 'financial'] as string[],
  patentCPC: ['G06N', 'G06F'] as string[],
})
const miningParams = ref({
  scholarId: '14i45118',
  topN: 5,
  analysisDimensions: ['industry_status', 'core_tech', 'financial'] as string[],
  regenerate: false,
})

const buildResult = ref<any>(null)
const annotationResp = ref<any>(null)
const analysisResp = ref<any>(null)
const miningResult = ref<any>(null)
const loading = ref(false)
const errorMsg = ref('')
const lastTestTime = ref('待执行')
const graphNodes = ref<GraphNode[]>([])

const dimensionChinese: Record<string, string> = {
  industry_status: '行业地位',
  core_tech: '核心技术',
  financial: '经营财务',
}

function buildRadialGraph(
  centerTitle: string,
  centerSubtitle: string,
  items: { title: string; subtitle: string; relation?: string }[],
): GraphNode[] {
  const cx = GW / 2
  const cy = GH / 2
  const radius = 380
  const n = items.length
  return [
    {
      key: 'expert',
      title: centerTitle,
      subtitle: centerSubtitle,
      x: cx - 150,
      y: cy - 47,
      width: 300,
      height: 94,
      kind: 'expert',
    },
    ...items.map((item, i) => {
      const ang = (2 * Math.PI * i) / (n || 1) - Math.PI / 2
      const ccx = cx + radius * Math.cos(ang)
      const ccy = cy + radius * Math.sin(ang)
      return {
        key: `c${i + 1}`,
        title: item.title,
        subtitle: item.subtitle,
        relation: item.relation,
        x: ccx - 180,
        y: ccy - 55,
        width: 360,
        height: 110,
        kind: 'company' as const,
      }
    }),
  ]
}

// 挖掘专用图：专家→企业（关系类型一条边）+ 企业→任职身份方块（角色）
function buildMiningGraph(
  scholarTitle: string,
  rels: {
    enterpriseName?: string
    enterpriseId?: string
    relationLabel?: string
    relationType?: string
    roleLabel?: string
    role?: string
    techField?: string
  }[],
): GraphNode[] {
  const cx = GW / 2
  const cy = GH / 2
  const radius = 300
  const n = rels.length
  const nodes: GraphNode[] = [
    {
      key: 'expert',
      title: scholarTitle,
      subtitle: '专家',
      x: cx - 150,
      y: cy - 47,
      width: 300,
      height: 94,
      kind: 'expert',
    },
  ]
  rels.forEach((r, i) => {
    const ang = (2 * Math.PI * i) / (n || 1) - Math.PI / 2
    const ccx = cx + radius * Math.cos(ang)
    const ccy = cy + radius * Math.sin(ang)
    const ckey = `c${i + 1}`
    const rkey = `r${i + 1}`
    nodes.push({
      key: ckey,
      title: `企业：${r.enterpriseName ?? r.enterpriseId ?? '-'}`,
      subtitle: r.techField ? `技术领域：${r.techField}` : '',
      relation: r.relationLabel || r.relationType || '任职',
      roleKey: rkey,
      x: ccx - 180,
      y: ccy - 55,
      width: 360,
      height: 110,
      kind: 'company',
    })
    // 任职身份方块：沿同一径向再往外
    const rcx = cx + (radius + 230) * Math.cos(ang)
    const rcy = cy + (radius + 230) * Math.sin(ang)
    nodes.push({
      key: rkey,
      title: '任职身份',
      subtitle: r.roleLabel || r.role || '-',
      x: rcx - 90,
      y: rcy - 34,
      width: 180,
      height: 68,
      kind: 'role',
    })
  })
  return nodes
}

const graphZoom = ref(0.56)
const graphStageRef = ref<HTMLElement | null>(null)
const activeDrag = ref<{ key: string; offsetX: number; offsetY: number } | null>(null)

const companyNodes = computed(() => graphNodes.value.filter((n) => n.kind === 'company'))

interface GraphEdge {
  key: string
  fromKey: string
  toKey: string
  text: string
  tone: string
  marker: string
}
// 边：专家→企业（关系类型）+ 企业→任职身份方块（角色）。mining 有角色方块，其余只有前者。
const graphEdges = computed<GraphEdge[]>(() => {
  const edges: GraphEdge[] = []
  for (const node of companyNodes.value) {
    const tone = relationTone(node.relation)
    edges.push({
      key: `${node.key}-rel`,
      fromKey: 'expert',
      toKey: node.key,
      text: node.relation || '',
      tone,
      marker: relationMarker(node.relation),
    })
    if (node.roleKey && getNode(node.roleKey)) {
      edges.push({
        key: `${node.key}-role`,
        fromKey: node.key,
        toKey: node.roleKey,
        text: '任职身份',
        tone: 'relation-purple',
        marker: 'url(#arrow-purple)',
      })
    }
  }
  return edges
})
function edgePath(edge: GraphEdge) {
  const from = getNode(edge.fromKey)
  const to = getNode(edge.toKey)
  if (!from || !to) return ''
  const fc = nodeCenter(from)
  const tc = nodeCenter(to)
  const start = boundaryPoint(from, tc)
  const end = boundaryPoint(to, fc)
  const verticalGap = Math.abs(end.y - start.y)
  const ctrl = {
    x: (start.x + end.x) / 2,
    y: (start.y + end.y) / 2 + (end.y < start.y ? -verticalGap * 0.3 : verticalGap * 0.12),
  }
  return `M ${start.x} ${start.y} Q ${ctrl.x} ${ctrl.y} ${end.x} ${end.y}`
}
function edgeLabelStyle(edge: GraphEdge) {
  const from = getNode(edge.fromKey)
  const to = getNode(edge.toKey)
  if (!from || !to) return {}
  const fc = nodeCenter(from)
  const tc = nodeCenter(to)
  const directionOffset = tc.y < fc.y ? -12 : 12
  return {
    left: `${(fc.x + tc.x) / 2 - 40}px`,
    top: `${(fc.y + tc.y) / 2 + directionOffset - 18}px`,
  }
}

function getNode(key: string) {
  return graphNodes.value.find((n) => n.key === key)
}
function nodeCenter(node: GraphNode) {
  return { x: node.x + node.width / 2, y: node.y + node.height / 2 }
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
  width: `${GW}px`,
  height: `${GH}px`,
  transform: `translate(-50%, -50%) scale(${graphZoom.value})`,
}))
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
  return { x: center.x + dx * scale, y: center.y + dy * scale }
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
  const scaleX = GW / rect.width
  const scaleY = GH / rect.height
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
  const scaleX = GW / rect.width
  const scaleY = GH / rect.height
  const nextX = (event.clientX - rect.left) * scaleX - drag.offsetX
  const nextY = (event.clientY - rect.top) * scaleY - drag.offsetY
  node.x = Math.max(0, Math.min(GW - node.width, nextX))
  node.y = Math.max(0, Math.min(GH - node.height, nextY))
}
function stopDrag() {
  activeDrag.value = null
}
function zoomGraph(event: WheelEvent) {
  event.preventDefault()
  const nextZoom = graphZoom.value + (event.deltaY > 0 ? -0.06 : 0.06)
  graphZoom.value = Math.max(0.55, Math.min(1.25, Number(nextZoom.toFixed(2))))
}

async function loadOptions() {
  try {
    const data = (await http.get('/v1/kg-construction/options')) as any
    options.value = {
      scholars: data.scholars ?? [],
      enterprises: data.enterprises ?? [],
      edges: data.edges ?? [],
      relationTypes: data.relationTypes ?? [],
      roles: data.roles ?? [],
      dimensions: data.dimensions ?? [],
      techFields: data.techFields ?? [],
      cpcCodes: data.cpcCodes ?? [],
    }
    // 默认值取首个真实选项（gkx 学者/企业/关系边）
    const sch = data.scholars?.[0]?.scholarId
    const ent = data.enterprises?.[0]?.enterpriseId
    const edg = data.edges?.[0]?.relationId
    if (sch && !buildParams.value.scholarId) buildParams.value.scholarId = sch
    if (ent && !buildParams.value.enterpriseId) buildParams.value.enterpriseId = ent
    if (ent && !analyzeParams.value.enterpriseId) analyzeParams.value.enterpriseId = ent
    if (edg && !annotateParams.value.relationId) annotateParams.value.relationId = edg
  } catch {
    // 选项拉取失败不阻塞页面
  }
}

type MultiKey = 'relationTypes' | 'analysisDimensions' | 'patentCPC'
function multiArr(key: MultiKey): string[] {
  if (key === 'relationTypes') return buildParams.value.relationTypes
  if (key === 'analysisDimensions')
    return activeSub.value === 'mining'
      ? miningParams.value.analysisDimensions
      : analyzeParams.value.analysisDimensions
  return analyzeParams.value.patentCPC
}
function pushMulti(key: MultiKey, value: string) {
  if (!value) return
  const arr = multiArr(key)
  if (!arr.includes(value)) arr.push(value)
}
function removeMulti(key: MultiKey, value: string) {
  const arr = multiArr(key)
  const i = arr.indexOf(value)
  if (i >= 0) arr.splice(i, 1)
}
function toggleMulti(key: MultiKey, value: string) {
  const arr = multiArr(key)
  const i = arr.indexOf(value)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(value)
}
function selectedItems(selected: string[], opts: OptionItem[]) {
  return opts.filter((o) => selected.includes(o.value ?? ''))
}

async function handleSearch() {
  loading.value = true
  errorMsg.value = ''
  try {
    if (activeSub.value === 'build') {
      const body = (await http.post(currentSub.value.endpoint, buildParams.value)) as any
      if (!body?.success) throw new Error(body?.msg || '构建失败')
      buildResult.value = body.data
      const rels: any[] = Array.isArray(body.data?.relations) ? body.data.relations : []
      graphNodes.value = buildRadialGraph(
        `专家：${body.data?.scholarName ?? buildParams.value.scholarId}`,
        '专家',
        rels.map((r: any) => ({
          title: `企业：${r.enterpriseName ?? r.enterpriseId}`,
          subtitle: '企业',
          relation: r.relationType || '-',
        })),
      )
    } else if (activeSub.value === 'annotate') {
      const body = (await http.post(currentSub.value.endpoint, annotateParams.value)) as any
      if (!body?.success) throw new Error(body?.msg || '标注失败')
      annotationResp.value = body.data
      const parts = String(annotateParams.value.relationId || '').split('->')
      const src = parts[0] || ''
      const dst = (parts[1] || '').split('@')[0] || ''
      graphNodes.value = buildRadialGraph(`专家：${src}`, '专家', [
        {
          title: `企业：${dst}`,
          subtitle: body.data?.techField || '企业',
          relation: body.data?.roleLabel || body.data?.roleType || '标注',
        },
      ])
    } else if (activeSub.value === 'mining') {
      // 挖掘完整流程含 LLM 抽取+建图+标注+背景分析，可能耗时 60-90s，单独放宽超时
      const body = (await http.post(currentSub.value.endpoint, miningParams.value, {
        timeout: 180_000,
      })) as any
      if (!body?.success) throw new Error(body?.msg || '挖掘失败')
      miningResult.value = body.data
      const rels: any[] = Array.isArray(body.data?.minedRelations) ? body.data.minedRelations : []
      // 仅 matched（已匹配到企业表）的关系画进图；unmatched 不画节点
      const matched = rels.filter((r: any) => r.status !== 'unmatched')
      graphNodes.value = buildMiningGraph(
        `专家：${body.data?.scholarName ?? miningParams.value.scholarId}`,
        matched,
      )
    } else {
      const body = (await http.post(currentSub.value.endpoint, analyzeParams.value)) as any
      if (!body?.success) throw new Error(body?.msg || '分析失败')
      analysisResp.value = body.data
      const dims = body.data?.dimensions ?? {}
      graphNodes.value = buildRadialGraph(
        `企业：${body.data?.enterpriseName ?? analyzeParams.value.enterpriseId}`,
        '企业',
        Object.keys(dims).map((k) => ({
          title: dimensionChinese[k] ?? k,
          subtitle: dims[k]?.available ? '有数据' : '无数据',
          relation: dims[k]?.available
            ? (dims[k]?.conclusion ?? '-')
            : (dims[k]?.summary ?? '-'),
        })),
      )
    }
    lastTestTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.msg || e?.message || String(e)
    graphNodes.value = []
  } finally {
    loading.value = false
  }
}

const activeResult = computed(() => {
  if (activeSub.value === 'annotate') return annotationResp.value
  if (activeSub.value === 'analyze') return analysisResp.value
  if (activeSub.value === 'mining') return miningResult.value
  return buildResult.value
})

const detailRows = computed<(string | number)[][]>(() => {
  if (activeSub.value === 'annotate') {
    const r = annotationResp.value
    if (!r) return []
    const p = r.period ?? annotateParams.value.period
    return [
      ['关系ID', r.relationId ?? annotateParams.value.relationId],
      ['角色', r.roleLabel ?? '-'],
      ['角色等级', r.roleLevel ?? '-'],
      ['角色类型', r.roleType ?? annotateParams.value.roleType],
      ['技术领域', r.techField ?? annotateParams.value.techField],
      ['周期', `${p?.start ?? ''} ~ ${p?.end ?? ''}`],
      ['标注结果', r.annotated ? '成功' : '失败'],
    ]
  }
  if (activeSub.value === 'analyze') {
    const r = analysisResp.value
    if (!r) return []
    const rows: (string | number)[][] = [['企业名称', r.enterpriseName ?? '-']]
    const dims = r.dimensions ?? {}
    Object.keys(dims).forEach((k) => {
      const d = dims[k]
      const label = dimensionChinese[k] ?? k
      const value = d?.available ? d.conclusion ?? '-' : d?.summary ?? '-'
      rows.push([label, value])
    })
    rows.push(['核心技术布局', r.coreTechLayout ?? '-'])
    const dist = Array.isArray(r.patentDistribution) ? r.patentDistribution : []
    dist.forEach((p: any) => rows.push([`CPC:${p.cpcSection ?? '-'}`, p.count ?? 0]))
    return rows
  }
  if (activeSub.value === 'mining') {
    const r = miningResult.value
    if (!r) return []
    const rows: (string | number)[][] = [
      ['专家', r.scholarName ?? r.scholarId ?? '-'],
      ['专家ID', r.scholarId ?? '-'],
      ['所属机构', r.scholarOrg ?? '-'],
      ['是否降级', r.degraded ? '是（LLM不可用，正则抽取）' : '否'],
      ['挖掘关系数', r.totalMined ?? 0],
    ]
    if (r.reminder) rows.push(['提醒', r.reminder])
    const rels = Array.isArray(r.minedRelations) ? r.minedRelations : []
    rels.forEach((rel: any, i: number) => {
      if (rel.status === 'unmatched') {
        rows.push([`企业${i + 1}（未匹配）`, `${rel.enterpriseName ?? '-'}：${rel.reminder ?? '未在企业表中找到'}`])
        return
      }
      const period = rel.period ? `${rel.period.start || '?'} ~ ${rel.period.end || '至今'}` : '-'
      rows.push([`企业${i + 1} 名称`, rel.enterpriseName ?? rel.enterpriseId ?? '-'])
      if (rel.extractedName && rel.extractedName !== rel.enterpriseName) {
        rows.push([`  抽取名→匹配`, `${rel.extractedName} → ${rel.enterpriseName}`])
      }
      rows.push([`  关系类型`, rel.relationLabel || rel.relationType || '-'])
      rows.push([`  角色`, rel.roleLabel || rel.role || '-'])
      if (rel.techField) rows.push([`  技术领域`, rel.techField])
      rows.push([`  合作时段`, period])
      rows.push([`  置信度`, rel.matchScore != null ? rel.matchScore : '-'])
      if (rel.confidenceAnalysis) rows.push([`  置信度分析`, rel.confidenceAnalysis])
      if (rel.evidence) rows.push([`  任职/合作依据`, rel.evidence])
    })
    return rows
  }
  const r = buildResult.value
  if (!r) return []
  const rows: (string | number)[][] = [
    ['专家', r.scholarName ?? r.scholarId ?? '-'],
    ['专家ID', r.scholarId ?? '-'],
  ]
  const rels = Array.isArray(r.relations) ? r.relations : []
  rels.forEach((rel: any) =>
    rows.push([rel.enterpriseName ?? rel.enterpriseId, rel.relationType ?? '-']),
  )
  return rows
})

const apiExample = computed(() => {
  const fallback =
    activeSub.value === 'annotate'
      ? {
          status: 'success',
          relationId: annotateParams.value.relationId,
          roleType: annotateParams.value.roleType,
          roleLabel: '',
          roleLevel: '',
          techField: annotateParams.value.techField,
          period: annotateParams.value.period,
          annotated: false,
        }
      : activeSub.value === 'analyze'
        ? {
            status: 'success',
            enterpriseId: analyzeParams.value.enterpriseId,
            enterpriseName: '',
            dimensions: {},
            patentDistribution: [],
            coreTechLayout: '',
          }
        : activeSub.value === 'mining'
          ? {
              status: 'success',
              scholarId: miningParams.value.scholarId,
              scholarName: '',
              scholarOrg: '',
              degraded: false,
              cached: false,
              reminder: '',
              minedRelations: [],
              skipped: [],
              totalMined: 0,
            }
          : {
              status: 'success',
              scholarId: buildParams.value.scholarId,
              scholarName: '',
              builtRelationId: `${buildParams.value.scholarId}->${buildParams.value.enterpriseId}@0`,
              relationType: '',
              effective: false,
              relations: [],
            }
  const data = activeResult.value ?? fallback
  return JSON.stringify({ code: 200, success: true, data, msg: 'success' }, null, 2)
})

const requestRows = computed<string[][]>(() => {
  if (activeSub.value === 'annotate') {
    return [
      ['relationId', 'string', '是', '政企关系ID'],
      ['roleType', 'string', '是', '角色类型'],
      ['techField', 'string', '否', '技术领域'],
      ['period.start', 'string', '否', '开始日期'],
      ['period.end', 'string', '否', '结束日期'],
    ]
  }
  if (activeSub.value === 'analyze') {
    return [
      ['enterpriseId', 'string', '是', '企业ID'],
      ['analysisDimensions', 'string[]', '是', '分析维度'],
      ['patentCPC', 'string[]', '否', '专利CPC分类号'],
    ]
  }
  if (activeSub.value === 'mining') {
    return [
      ['scholarId', 'string', '是', '学者ID（gkx dwd_scholar.scholar_id，如 007Rb117）'],
      ['topN', 'int', '否', 'TOP-N，默认5，上限10'],
      ['analysisDimensions', 'string[]', '否', '分析维度，默认三维度全选'],
      ['regenerate', 'bool', '否', '是否强制重新挖掘；默认false，已构建则直接返回图库关系'],
    ]
  }
  return [
    ['scholarId', 'string', '是', '专家ID'],
    ['enterpriseId', 'string', '是', '企业ID'],
    ['relationTypes', 'string[]', '是', '关联关系类型（多选，英文编码）'],
  ]
})

const responseRows = computed<string[][]>(() => {
  if (activeSub.value === 'annotate') {
    return [
      ['code', 'int', '业务状态码（200 成功）'],
      ['success', 'boolean', '是否成功'],
      ['data', 'object', '结果对象'],
      ['data.relationId', 'string', '政企关系ID'],
      ['data.roleType', 'string', '角色类型'],
      ['data.roleLabel', 'string', '角色标签'],
      ['data.roleLevel', 'string', '角色等级'],
      ['data.techField', 'string', '技术领域'],
      ['data.period', 'object', '合作时段'],
      ['data.annotated', 'boolean', '标注结果'],
      ['msg', 'string', '返回消息'],
    ]
  }
  if (activeSub.value === 'analyze') {
    return [
      ['code', 'int', '业务状态码（200 成功）'],
      ['success', 'boolean', '是否成功'],
      ['data', 'object', '结果对象'],
      ['data.enterpriseId', 'string', '企业ID'],
      ['data.enterpriseName', 'string', '企业名称'],
      ['data.dimensions', 'object', '各维度分析'],
      ['data.dimensions[].available', 'boolean', '维度是否有数据'],
      ['data.dimensions[].conclusion', 'string', '维度结论'],
      ['data.patentDistribution', 'array', '专利分布'],
      ['data.coreTechLayout', 'string', '核心技术布局'],
      ['msg', 'string', '返回消息'],
    ]
  }
  if (activeSub.value === 'mining') {
    return [
      ['code', 'int', '业务状态码（200 成功）'],
      ['success', 'boolean', '是否成功'],
      ['data', 'object', '结果对象'],
      ['data.scholarId', 'string', '学者ID'],
      ['data.scholarName', 'string', '学者姓名'],
      ['data.scholarOrg', 'string', '学者所属机构'],
      ['data.degraded', 'boolean', '是否降级（LLM不可用）'],
      ['data.cached', 'boolean', '是否来自图库已构建关系（未重跑）'],
      ['data.reminder', 'string', '汇总提醒（未匹配/未抽取说明）'],
      ['data.minedRelations', 'array', '挖掘出的企业关系列表（含 matched 与 unmatched）'],
      ['data.minedRelations[].status', 'string', 'matched=已匹配建关系；unmatched=未在企业表找到'],
      ['data.minedRelations[].enterpriseName', 'string', '企业名称'],
      ['data.minedRelations[].relationLabel', 'string', '关系类型中文'],
      ['data.minedRelations[].roleLabel', 'string', '角色中文'],
      ['data.minedRelations[].matchScore', 'float', '消歧置信度'],
      ['data.minedRelations[].reminder', 'string', '未匹配提醒（仅 unmatched）'],
      ['data.minedRelations[].build', 'object', '构建结果'],
      ['data.minedRelations[].annotate', 'object', '标注结果'],
      ['data.minedRelations[].analyze', 'object', '企业背景分析结果'],
      ['data.skipped', 'array', '未匹配企业列表'],
      ['data.totalMined', 'int', '成功构建的关系总数（不含 unmatched）'],
      ['msg', 'string', '返回消息'],
    ]
  }
  return [
    ['code', 'int', '业务状态码（200 成功）'],
    ['success', 'boolean', '是否成功'],
    ['data', 'object', '结果对象'],
    ['data.scholarId', 'string', '专家ID'],
    ['data.scholarName', 'string', '专家姓名'],
    ['data.builtRelationId', 'string', '构建的关系ID'],
    ['data.relationType', 'string', '关系类型标签'],
    ['data.effective', 'boolean', '生效标识'],
    ['data.relations', 'array', '该专家全部企业关系'],
    ['data.relations[].enterpriseName', 'string', '企业名称'],
    ['data.relations[].relationType', 'string', '关系类型标签'],
    ['msg', 'string', '返回消息'],
  ]
})

const techDesc = computed(() => {
  if (activeSub.value === 'annotate')
    return '为已存在的专家-企业关系边（EMPLOYED_BY）标注角色（首席科学家/CTO 等）、技术领域与合作时段，角色按目录映射 L1/L2/L3 等级。'
  if (activeSub.value === 'analyze')
    return '聚合企业行业地位、核心技术、经营财务维度数据，并结合 LLM 合成企业背景分析结论，LLM 不可用时降级返回结构化数据。'
  if (activeSub.value === 'mining')
    return '输入学者ID，从学者履历中抽取关联企业并消歧，自动构建、标注并分析专家-企业关系，LLM 不可用时降级为正则抽取。'
  return '基于专家任职履历与企业信息，构建专家-企业任职/合作关系边（EMPLOYED_BY），支持多种关系类型组合，按企业去重返回该专家全部企业关系。'
})

const codeSamples = computed<Record<string, string>>(() => {
  const url = apiPath.value
  const payload =
    activeSub.value === 'annotate'
      ? JSON.stringify(annotateParams.value, null, 2)
      : activeSub.value === 'analyze'
        ? JSON.stringify(analyzeParams.value, null, 2)
        : activeSub.value === 'mining'
          ? JSON.stringify(miningParams.value, null, 2)
          : JSON.stringify(buildParams.value, null, 2)
  return {
    python: `import requests

url = "http://localhost:8200${url}"
payload = ${payload}
headers = {"Content-Type": "application/json"}
response = requests.post(url, json=payload, headers=headers, timeout=20)
print(response.json())`,
    node: `const res = await fetch("http://localhost:8200${url}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(${payload}),
});
console.log(await res.json());`,
    curl: `curl -X POST "http://localhost:8200${url}" \\
  -H "Content-Type: application/json" \\
  -d '${payload.replace(/\s+/g, ' ')}'`,
  }
})

async function handleCopyCode() {
  try {
    await navigator.clipboard?.writeText(codeSamples.value[activeCode.value])
  } catch {
    // 剪贴板被浏览器拒绝时仍保留视觉反馈
  }
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1200)
}

onMounted(() => {
  loadOptions()
})
</script>

<template>
  <div class="enterprise-relation">
    <header class="er-toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': mainTab === 'test' }"
          type="button"
          @click="mainTab = 'test'"
        >
          算法测试
        </button>
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': mainTab === 'developer' }"
          type="button"
          @click="mainTab = 'developer'"
        >
          开发者接口
        </button>
      </div>
      <button class="kg-button kg-button--text er-tech" type="button" @click="showTech = true">
        <img :src="iconInfo" alt="" aria-hidden="true" />
        技术方案
      </button>
    </header>

    <section v-if="mainTab === 'test'" class="search-panel-inline">
      <label class="search-panel-inline__field">
        <span>子功能名称：</span>
        <select v-model="activeSub" class="select-with-icon">
          <option v-for="s in subFunctions" :key="s.key" :value="s.key">{{ s.name }}</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
        <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
      </label>
      <div class="search-panel-inline__actions">
        <button class="kg-button kg-button--secondary" type="button" @click="showConfig = true">
          参数设置
        </button>
        <button class="kg-button" type="button" @click="handleSearch">
          {{ loading ? '测试中...' : '执行测试' }}
        </button>
      </div>
    </section>

    <div v-if="mainTab === 'test'" class="er-main">
      <section class="kg-panel graph-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">测试结果预览</h2>
          <div class="graph-panel__time">
            <span>最近测试时间：</span>
            <strong>{{ lastTestTime }}</strong>
          </div>
        </div>
        <div class="graph-panel__canvas" @wheel="zoomGraph">
          <div v-if="errorMsg" class="er-error">{{ errorMsg }}</div>
          <div v-else-if="!graphNodes.length" class="er-empty">
            <strong>{{ currentSub.name }}</strong>
            <span>点击「执行测试」查看关系图谱</span>
          </div>
          <div
            v-else
            ref="graphStageRef"
            class="graph-stage"
            :style="graphStageStyle"
            @pointermove="dragNode"
            @pointerup="stopDrag"
            @pointercancel="stopDrag"
            @pointerleave="stopDrag"
          >
            <svg class="graph-lines" :viewBox="`0 0 ${GW} ${GH}`" aria-hidden="true">
              <defs>
                <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#2f7cff" />
                </marker>
                <marker id="arrow-purple" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b5cf6" />
                </marker>
                <marker id="arrow-orange" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
                </marker>
              </defs>
              <path
                v-for="edge in graphEdges"
                :key="`${edge.key}-path`"
                class="relation-edge"
                :class="edge.tone"
                :d="edgePath(edge)"
                :marker-end="edge.marker"
              />
            </svg>
            <span
              v-for="edge in graphEdges"
              :key="`${edge.key}-label`"
              class="relation-label"
              :class="edge.tone"
              :style="edgeLabelStyle(edge)"
            >{{ edge.text }}</span>
            <div
              v-for="node in graphNodes"
              :key="node.key"
              class="graph-node"
              :class="[{ dragging: activeDrag?.key === node.key }, node.kind === 'expert' ? 'expert-node' : node.kind === 'role' ? 'role-node' : 'company-node']"
              :style="nodeStyle(node)"
              @pointerdown="startDrag($event, node)"
            >
              <strong>{{ node.title }}</strong>
              <span>{{ node.subtitle }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="er-side">
        <section class="kg-panel result-panel">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">结果详情</h2>
            <div class="result-panel__tabs">
              <button
                :class="{ 'is-active': resultTab === 'structured' }"
                type="button"
                @click="resultTab = 'structured'"
              >
                结构化结果
              </button>
              <button
                :class="{ 'is-active': resultTab === 'api' }"
                type="button"
                @click="resultTab = 'api'"
              >
                API结果示例
              </button>
            </div>
          </div>
          <dl v-if="resultTab === 'structured' && detailRows.length" class="result-panel__table scroll-on-demand">
            <div v-for="(row, i) in detailRows" :key="i">
              <dt>{{ row[0] }}</dt>
              <dd>{{ row[1] }}</dd>
            </div>
          </dl>
          <div v-else-if="resultTab === 'structured'" class="result-empty">暂无结果，请先执行测试</div>
          <pre v-else class="result-panel__code scroll-on-demand">{{ apiExample }}</pre>
        </section>
      </aside>
    </div>

    <section v-else class="developer-view">
      <div class="developer-view__meta">
        <label>
          <span>子功能名称：</span>
          <select v-model="activeSub" class="select-with-icon">
            <option v-for="s in subFunctions" :key="s.key" :value="s.key">{{ s.name }}</option>
          </select>
          <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
        </label>
        <label>
          <span>接口路径：</span>
          <input :value="apiPath" readonly />
        </label>
        <span>请求方法： POST</span>
      </div>
      <div class="developer-view__cards">
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
          <div class="developer-table-wrap scroll-on-demand">
            <table class="developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="(r, i) in requestRows" :key="i">
                  <td v-for="(c, j) in r" :key="j">{{ c }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">返回字段</h2></div>
          <div class="developer-table-wrap scroll-on-demand">
            <table class="developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="(r, i) in responseRows" :key="i">
                  <td v-for="(c, j) in r" :key="j">{{ c }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <section class="kg-panel developer-code">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">代码示例</h2>
          <div class="profile-card-like-tabs">
            <button :class="{ 'is-active': activeCode === 'python' }" type="button" @click="activeCode = 'python'">Python</button>
            <button :class="{ 'is-active': activeCode === 'node' }" type="button" @click="activeCode = 'node'">Node.js</button>
            <button :class="{ 'is-active': activeCode === 'curl' }" type="button" @click="activeCode = 'curl'">cURL</button>
          </div>
        </div>
        <button
          class="developer-code__copy"
          :class="{ 'is-copied': copied }"
          type="button"
          @click="handleCopyCode"
        >
          <span v-if="copied" aria-hidden="true">✓</span>
          <img v-else :src="iconCopy" alt="" aria-hidden="true" />
        </button>
        <pre class="scroll-on-demand">{{ codeSamples[activeCode] }}</pre>
      </section>
    </section>

    <div v-if="showConfig || showTech" class="modal-mask" @click.self="showConfig = false; showTech = false">
      <section v-if="showConfig" class="modal modal--config" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2><img :src="iconModalSetting" alt="" aria-hidden="true" />测试参数设置</h2>
          <div class="modal__header-extra">
            <span class="modal__required"><span>*</span> 为必填项</span>
            <button type="button" @click="showConfig = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
          </div>
        </header>
        <div class="modal__body config-form">
          <template v-if="activeSub === 'build'">
            <label>
              <span><i>*</i>scholarId</span>
              <select v-model="buildParams.scholarId">
                <option v-for="s in options.scholars" :key="s.scholarId" :value="s.scholarId">{{ s.name }}（{{ s.scholarId }}）</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <label>
              <span><i>*</i>enterpriseId</span>
              <select v-model="buildParams.enterpriseId">
                <option v-for="e in options.enterprises" :key="e.enterpriseId" :value="e.enterpriseId">{{ e.name }}（{{ e.enterpriseId }}）</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <div class="config-multi">
              <span><i>*</i>relationTypes</span>
              <div class="ms-field">
                <select
                  class="ms-add"
                  @change="pushMulti('relationTypes', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
                >
                  <option value="" disabled selected>请选择（可多选，每选一项加一条）</option>
                  <option v-for="r in options.relationTypes" :key="r.value" :value="r.value">{{ r.label }}</option>
                </select>
                <div class="ms-tags">
                  <span
                    v-for="r in selectedItems(buildParams.relationTypes, options.relationTypes)"
                    :key="r.value"
                    class="ms-tag"
                  >
                    {{ r.label
                    }}<button type="button" class="ms-tag-x" @click="removeMulti('relationTypes', r.value ?? '')">×</button>
                  </span>
                </div>
              </div>
            </div>
          </template>

          <template v-else-if="activeSub === 'annotate'">
            <label>
              <span><i>*</i>relationId</span>
              <select v-model="annotateParams.relationId">
                <option v-for="e in options.edges" :key="e.relationId" :value="e.relationId">{{ e.relationId }}</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <label>
              <span><i>*</i>roleType</span>
              <select v-model="annotateParams.roleType">
                <option v-for="r in options.roles" :key="r.value" :value="r.value">{{ r.label }}</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <label>
              <span><i></i>techField</span>
              <select v-model="annotateParams.techField">
                <option v-for="t in options.techFields" :key="t" :value="t">{{ t }}</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <label><span><i></i>period.start</span><input v-model="annotateParams.period.start" placeholder="2021-01-01" /></label>
            <label><span><i></i>period.end</span><input v-model="annotateParams.period.end" placeholder="2024-12-31" /></label>
          </template>

          <template v-else-if="activeSub === 'analyze'">
            <label>
              <span><i>*</i>enterpriseId</span>
              <select v-model="analyzeParams.enterpriseId">
                <option v-for="e in options.enterprises" :key="e.enterpriseId" :value="e.enterpriseId">{{ e.name }}（{{ e.enterpriseId }}）</option>
              </select>
              <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
            </label>
            <div class="config-multi">
              <span><i>*</i>analysisDimensions</span>
              <div class="ms-field">
                <select
                  class="ms-add"
                  @change="pushMulti('analysisDimensions', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
                >
                  <option value="" disabled selected>请选择（可多选，每选一项加一条）</option>
                  <option v-for="d in options.dimensions" :key="d.value" :value="d.value">{{ d.label }}</option>
                </select>
                <div class="ms-tags">
                  <span
                    v-for="d in selectedItems(analyzeParams.analysisDimensions, options.dimensions)"
                    :key="d.value"
                    class="ms-tag"
                  >
                    {{ d.label
                    }}<button type="button" class="ms-tag-x" @click="removeMulti('analysisDimensions', d.value ?? '')">×</button>
                  </span>
                </div>
              </div>
            </div>
            <div class="config-multi">
              <span><i></i>patentCPC</span>
              <div class="ms-field">
                <select
                  class="ms-add"
                  @change="pushMulti('patentCPC', ($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
                >
                  <option value="" disabled selected>请选择（可多选，每选一项加一条）</option>
                  <option v-for="c in options.cpcCodes" :key="c" :value="c">{{ c }}</option>
                </select>
                <div class="ms-tags">
                  <span v-for="c in analyzeParams.patentCPC" :key="c" class="ms-tag">
                    {{ c }}<button type="button" class="ms-tag-x" @click="removeMulti('patentCPC', c)">×</button>
                  </span>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <label>
              <span><i>*</i>scholarId</span>
              <input
                type="text"
                v-model="miningParams.scholarId"
                placeholder="gkx 学者ID，如 007Rb117 / 14i45118"
              />
            </label>
            <label>
              <span><i></i>topN</span>
              <input
                type="number"
                min="1"
                max="10"
                :value="miningParams.topN"
                @input="miningParams.topN = Number(($event.target as HTMLInputElement).value)"
              />
            </label>
            <div class="config-multi">
              <span><i></i>analysisDimensions</span>
              <div class="ms-dropdown">
                <button
                  type="button"
                  class="ms-dropdown__box"
                  :class="{ 'is-open': miningDimsOpen }"
                  @click="miningDimsOpen = !miningDimsOpen"
                >
                  <span
                    v-if="!selectedItems(miningParams.analysisDimensions, options.dimensions).length"
                    class="ms-placeholder"
                    >请选择（可多选）</span
                  >
                  <span
                    v-for="d in selectedItems(miningParams.analysisDimensions, options.dimensions)"
                    :key="d.value"
                    class="ms-tag"
                  >
                    {{ d.label
                    }}<button
                      type="button"
                      class="ms-tag-x"
                      @click.stop="removeMulti('analysisDimensions', d.value ?? '')"
                    >×</button>
                  </span>
                  <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
                </button>
                <template v-if="miningDimsOpen">
                  <div class="ms-dropdown__backdrop" @click="miningDimsOpen = false"></div>
                  <div class="ms-dropdown__panel">
                    <label
                      v-for="d in options.dimensions"
                      :key="d.value"
                      class="ms-option"
                    >
                      <input
                        type="checkbox"
                        :checked="miningParams.analysisDimensions.includes(d.value ?? '')"
                        @change="toggleMulti('analysisDimensions', d.value ?? '')"
                      />
                      <span>{{ d.label }}</span>
                    </label>
                  </div>
                </template>
              </div>
            </div>
            <label class="config-check">
              <span>regenerate</span>
              <input type="checkbox" v-model="miningParams.regenerate" />
            </label>
          </template>
        </div>
        <footer class="modal__footer">
          <button class="kg-button kg-button--secondary" type="button" @click="showConfig = false">取消</button>
          <button class="kg-button" type="button" @click="showConfig = false; handleSearch()">保存并执行</button>
        </footer>
      </section>

      <section v-if="showTech" class="modal modal--tech" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2>技术方案</h2>
          <button type="button" @click="showTech = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
        </header>
        <div class="modal__body">
          <h3 class="modal__section-title">功能描述</h3>
          <p class="modal__desc">{{ currentSub.name }}：{{ techDesc }}</p>
          <h3 class="modal__section-title">接口信息</h3>
          <p class="modal__desc">接口路径：{{ apiPath }}（POST）。响应统一为 { code, success, data, msg }，业务结果在 data 字段。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.enterprise-relation {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--space-12);
  color: var(--text-primary);
}

.er-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
  padding: 0 var(--space-16);
}

.er-tech {
  gap: 4px;
}

.er-tech img {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.kg-tabs {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
}

.kg-tabs__item {
  height: 36px;
  padding: 0 var(--space-16);
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
  font-size: 16px;
}

.kg-tabs__item.is-active {
  color: var(--primary);
  background: var(--surface-subtle);
  font-weight: 500;
}

.kg-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-8);
  height: var(--control-height);
  padding: 0 var(--space-16);
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-inverse);
  background: var(--primary);
  font-size: 15px;
}

.kg-button--secondary {
  color: var(--primary);
  background: var(--primary-subtle);
}

.kg-button--text {
  color: var(--text-secondary);
  background: transparent;
}

.search-panel-inline {
  display: grid;
  grid-template-columns: 420px minmax(220px, 1fr);
  gap: var(--space-12);
  align-items: end;
  min-height: 44px;
  padding: 0 var(--space-16) var(--space-4);
}

.search-panel-inline__field,
.developer-view__meta label {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 14px;
  align-items: center;
  gap: var(--space-8);
}

.search-panel-inline__field select,
.developer-view__meta select,
.config-form select {
  width: 100%;
  height: var(--control-height);
  padding: 0 34px 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
}

.select-with-icon {
  appearance: none;
  -webkit-appearance: none;
  background-image: none;
  cursor: pointer;
}

.select-icon {
  position: absolute;
  right: 10px;
  width: 14px;
  height: 14px;
  pointer-events: none;
  object-fit: contain;
}

.search-panel-inline__field .select-icon,
.developer-view__meta label .select-icon {
  right: 28px;
  top: 50%;
  transform: translateY(-50%);
}

.field-info-icon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.search-panel-inline__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-16);
}

.er-main {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: var(--space-16);
  flex: 1;
  min-height: 0;
  padding: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--surface-subtle);
  overflow: hidden;
}

.er-side {
  display: flex;
  flex-direction: column;
  gap: var(--space-12);
  min-height: 0;
  overflow: hidden;
}

.kg-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.kg-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
}

.kg-panel__title {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.graph-panel__time {
  display: flex;
  gap: var(--space-12);
  color: var(--text-tertiary);
  font-size: 14px;
}

.graph-panel__time strong {
  font-weight: 400;
}

.graph-panel__canvas {
  position: relative;
  display: grid;
  place-items: center;
  flex: 1;
  min-height: 0;
  margin: 0 var(--space-16) var(--space-16);
  overflow: hidden;
  border-radius: var(--radius-md);
  background:
    radial-gradient(circle at 1px 1px, #dce5f0 1.2px, transparent 1.2px) 0 0 / 24px 24px,
    var(--surface);
}

.graph-stage {
  position: absolute;
  top: 50%;
  left: 50%;
  transform-origin: center center;
  touch-action: none;
  user-select: none;
}

.graph-lines {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 4;
  pointer-events: none;
}

.graph-lines .relation-edge {
  fill: none;
  stroke-width: 2.5;
}

.er-empty,
.er-error {
  display: grid;
  width: 360px;
  min-height: 180px;
  place-items: center;
  padding: var(--space-24);
  border: 1px dashed #b5d3fc;
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  text-align: center;
}

.er-empty strong {
  color: var(--text-primary);
  font-size: 18px;
}

.er-empty span {
  margin-top: var(--space-8);
}

.er-error {
  border-color: var(--danger);
  color: var(--danger);
  word-break: break-all;
}

.result-empty {
  display: grid;
  place-items: center;
  flex: 1;
  min-height: 0;
  color: var(--text-tertiary);
  font-size: 15px;
}

.graph-node {
  position: absolute;
  z-index: 2;
  display: grid;
  align-content: center;
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(246, 251, 255, 0.95));
  cursor: grab;
  transition:
    border-color 0.16s,
    box-shadow 0.16s;
}

.graph-node:hover,
.graph-node.dragging {
  box-shadow: 0 10px 26px rgba(31, 114, 255, 0.18);
}

.graph-node.dragging {
  cursor: grabbing;
}

.expert-node {
  border: 1px solid #91baff;
  text-align: center;
}

.expert-node strong {
  color: #1663e8;
  font-size: 24px;
}

.expert-node span {
  margin-top: 8px;
  color: #24466f;
  font-size: 19px;
}

.company-node {
  border: 1px solid #76cf8e;
  background: linear-gradient(180deg, #f7fff8, #effaf2);
  padding: 0 20px;
}

.company-node strong {
  color: var(--graph-green);
  font-size: 22px;
}

.company-node span {
  margin-top: 8px;
  color: #314662;
  font-size: 18px;
}

.role-node {
  border: 1px dashed #8b5cf6;
  background: linear-gradient(180deg, #faf8ff, #f3effe);
  padding: 0 14px;
}

.role-node strong {
  color: #8b5cf6;
  font-size: 16px;
}

.role-node span {
  margin-top: 4px;
  color: #5b3ba5;
  font-size: 16px;
}

.relation-label {
  position: absolute;
  z-index: 5;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.88);
  padding: 2px 8px;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  pointer-events: none;
}

.relation-blue {
  color: #2f7cff;
  stroke: #2f7cff;
}

.relation-purple {
  color: #8b5cf6;
  stroke: #8b5cf6;
}

.relation-orange {
  color: #f59e0b;
  stroke: #f59e0b;
}

.result-panel__tabs,
.profile-card-like-tabs {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border-radius: var(--radius-sm);
  background: var(--surface-subtle);
}

.result-panel__tabs button,
.profile-card-like-tabs button {
  height: 28px;
  padding: 0 var(--space-12);
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
  font-size: 15px;
}

.result-panel__tabs button.is-active,
.profile-card-like-tabs button.is-active {
  color: var(--primary);
  background: var(--surface);
  font-weight: 500;
}

.result-panel__table {
  flex: 1;
  min-height: 0;
  margin: 0;
  overflow: auto;
  overscroll-behavior: contain;
}

.result-panel__table div {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  min-height: 44px;
  border-bottom: 1px solid var(--border);
}

.result-panel__table dt,
.result-panel__table dd {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0 var(--space-16);
  font-size: 15px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.result-panel__table dt {
  justify-content: flex-start;
  border-right: 1px solid var(--border);
  color: var(--text-tertiary);
}

.result-panel__table dd {
  color: var(--text-primary);
}

.result-panel__code {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: var(--space-16) 24px;
  overflow: auto;
  overscroll-behavior: contain;
  color: #52c41a;
  background: var(--surface);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 24px;
  white-space: pre-wrap;
}

.developer-view {
  position: relative;
  display: grid;
  grid-template-rows: 44px minmax(0, 1.4fr) minmax(0, 1fr);
  gap: var(--space-16);
  flex: 1;
  min-height: 0;
  padding: 0 var(--space-16) var(--space-16);
  overflow: hidden;
}

.developer-view::before {
  position: absolute;
  z-index: 0;
  top: calc(44px + var(--space-16));
  right: var(--space-16);
  bottom: var(--space-16);
  left: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--surface-subtle);
  content: "";
}

.developer-view > * {
  position: relative;
  z-index: 1;
}

.developer-view__meta {
  display: grid;
  grid-template-columns: 420px 1fr 160px;
  gap: 48px;
  align-items: center;
  min-height: 44px;
}

.developer-view__meta input,
.config-form input {
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
}

.developer-view__meta input[readonly] {
  color: var(--text-primary);
}

.developer-view__cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-16);
  min-height: 0;
  padding: var(--space-16) var(--space-16) 0;
  overflow: hidden;
}

.developer-table-wrap {
  height: calc(100% - 52px);
  margin: 0 6px var(--space-16);
  overflow: auto;
}

.developer-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

.developer-table th,
.developer-table td {
  height: 36px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.developer-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--text-secondary);
  background: var(--surface-muted);
  font-weight: 400;
}

.developer-table td {
  color: var(--text-primary);
}

.developer-code {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  margin: 0 var(--space-16) var(--space-16);
  overflow: hidden;
}

.developer-code__copy {
  position: absolute;
  right: 22px;
  bottom: 22px;
  z-index: 1;
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
  background: var(--surface);
  box-shadow: 0 8px 18px rgba(29, 33, 41, 0.16);
}

.developer-code__copy img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.developer-code__copy span {
  color: var(--success);
  font-size: 20px;
  line-height: 1;
  font-weight: 600;
}

.developer-code__copy.is-copied {
  box-shadow: 0 8px 18px rgba(0, 180, 42, 0.18);
}

.developer-code pre {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: var(--space-16) 32px;
  overflow: auto;
  color: #95c47a;
  font-size: 13px;
  line-height: 24px;
  white-space: pre;
}

.scroll-on-demand {
  scrollbar-color: transparent transparent;
}

.scroll-on-demand::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.scroll-on-demand:hover {
  scrollbar-color: rgba(102, 110, 139, 0.36) transparent;
}

.scroll-on-demand:hover::-webkit-scrollbar-thumb {
  background: rgba(102, 110, 139, 0.34);
}

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  background: rgba(29, 33, 41, 0.42);
}

.modal {
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 18px 48px rgba(29, 33, 41, 0.2);
}

.modal--config {
  width: 560px;
}

.modal--tech {
  width: 640px;
}

.modal__header,
.modal__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
}

.modal__header h2 {
  display: inline-flex;
  align-items: center;
  gap: var(--space-8);
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.modal__header h2 img {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

.modal__header button {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 0;
  cursor: pointer;
  color: var(--text-tertiary);
  background: transparent;
  font-size: 24px;
}

.modal__header button img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.modal__header-extra {
  display: inline-flex;
  align-items: center;
  gap: var(--space-12);
}

.modal__required {
  color: var(--text-tertiary);
  font-size: 12px;
}

.modal__required span,
.config-form i {
  color: var(--danger);
  font-style: normal;
}

.modal__body {
  padding: var(--space-16);
  max-height: 60vh;
  overflow: auto;
}

.modal__footer {
  justify-content: flex-end;
  gap: var(--space-12);
  border-top: 1px solid var(--border);
  border-bottom: 0;
}

.config-form {
  display: grid;
  gap: var(--space-16);
}

.config-form label {
  position: relative;
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: var(--space-8);
}

.config-form label > span {
  display: inline-flex;
  align-items: center;
  color: #86909c;
}

.config-form i {
  width: 10px;
}

.config-form label.config-check {
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: var(--space-8);
  min-height: var(--control-height);
}

.config-form label.config-check > span {
  color: #86909c;
}

.config-form label.config-check input[type='checkbox'] {
  width: 16px;
  height: 16px;
}

.config-form .select-icon {
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
}

.config-multi {
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: start;
  gap: var(--space-8);
}

.config-multi > span {
  display: inline-flex;
  align-items: center;
  color: #86909c;
  padding-top: 8px;
}

.ms-field {
  display: flex;
  flex-direction: column;
}

.ms-add {
  width: 100%;
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 14px;
}

.ms-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: var(--space-8);
}

.ms-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 10px;
  background: var(--primary-subtle);
  border: 1px solid #c7d8ff;
  border-radius: 14px;
  font-size: 13px;
  color: var(--primary);
}

.ms-tag-x {
  border: 0;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 0 2px;
}

.ms-tag-x:hover {
  color: var(--danger);
}

/* 自定义多选下拉（选中项展示在框内） */
.ms-dropdown {
  position: relative;
}

.ms-dropdown__box {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: var(--control-height);
  width: 100%;
  padding: 5px 36px 5px 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
}

.ms-dropdown__box.is-open {
  border-color: var(--primary);
}

.ms-dropdown__box .select-icon {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
}

.ms-placeholder {
  color: var(--text-tertiary);
  font-size: 14px;
}

.ms-dropdown__backdrop {
  position: fixed;
  inset: 0;
  z-index: 19;
}

.ms-dropdown__panel {
  position: absolute;
  z-index: 20;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  max-height: 240px;
  overflow-y: auto;
  padding: 6px 0;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.ms-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
}

.ms-option input[type='checkbox'] {
  width: 13px;
  height: 13px;
}

.ms-option:hover {
  background: var(--primary-subtle);
}

.modal__section-title {
  position: relative;
  margin: 0 0 var(--space-12);
  padding-left: var(--space-12);
  font-size: 14px;
  font-weight: 500;
}

.modal__section-title::before {
  position: absolute;
  left: 0;
  width: 3px;
  height: 16px;
  border-radius: 2px;
  background: var(--primary);
  content: "";
}

.modal__desc {
  margin: 0 0 var(--space-16);
  padding: var(--space-16);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  background: var(--surface-subtle);
  line-height: 24px;
}
</style>
