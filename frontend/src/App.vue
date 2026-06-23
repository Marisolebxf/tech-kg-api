<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import sidebarLogo from './assets/sidebar/logo.png'
import sidebarMenu from './assets/sidebar/menu.png'
import navFlowIcon from './assets/sidebar/nav-flow.png'
import navGraphIcon from './assets/sidebar/nav-graph.png'
import navReasonIcon from './assets/sidebar/nav-reason.png'
import chatIcon from './assets/sidebar/chat.png'

type DataSource = 'all' | 'knowledge_graph' | 'cnki' | 'wanfang' | 'web_of_science'
type NodeId = 'expertA' | 'expertB' | 'paper' | 'topic' | 'period' | 'contribution'

type TestRequestPayload = {
  dataSource: DataSource
  expertAId: string
  expertBId: string
  startTime: string
  endTime: string
}

type StructuredResultPayload = {
  authorList: string[]
  authorUnits: string[]
  paperTopics: string[]
  cooperationPaperCount: number
  journalLevelCount: Record<string, number>
  conferenceLevelCount: Record<string, number>
  cooperationFrequency: number
  academicImpactScore: number
  citation: { total: number; max: number }
  cooperationTimeRange: { displayText: string }
  stableTeamName?: string | null
  stableTeamMembers?: string[]
  coreCollaborators?: string[]
  sharedContribution?: string[]
  representativePapers?: string[]
}

type StructuredResultOnlyResponse = {
  structuredResult: StructuredResultPayload
}

type NodeLayout = {
  x: number
  y: number
  w: number
  h: number
}

type Point = {
  x: number
  y: number
}

const defaultParams: TestRequestPayload = {
  dataSource: 'knowledge_graph',
  expertAId: 'COOP-SCH001',
  expertBId: 'COOP-SCH002',
  startTime: '2021-01-01',
  endTime: '2024-12-31',
}

const defaultNodeLayout: Record<NodeId, NodeLayout> = {
  expertA: { x: 6.5, y: 10, w: 30, h: 15 },
  expertB: { x: 62.5, y: 10, w: 30, h: 15 },
  paper: { x: 33.8, y: 37.6, w: 32.4, h: 20 },
  topic: { x: 3.8, y: 64.6, w: 38.2, h: 26.6 },
  period: { x: 44.3, y: 78.3, w: 16.8, h: 11.8 },
  contribution: { x: 67.2, y: 63.8, w: 29.4, h: 27.8 },
}

const subfunctionOptions = ['专家论文合作关系构建'] as const

const dataSourceOptions: Array<{ label: string; value: DataSource }> = [
  { label: '全部', value: 'all' },
  { label: '知识图谱', value: 'knowledge_graph' },
  { label: '知网', value: 'cnki' },
  { label: '万方', value: 'wanfang' },
  { label: 'Web of Science', value: 'web_of_science' },
]

const apiExample = ref<StructuredResultOnlyResponse | null>(null)
const loading = ref(false)
const error = ref('')
const activePage = ref<'test' | 'developer'>('test')
const activeTab = ref<'structured' | 'api'>('structured')
const developerCodeTab = ref<'python' | 'node' | 'curl'>('python')
const copiedCodeTab = ref<'' | 'python' | 'node' | 'curl'>('')
const lastTestTime = ref('2026-07-23 11:00:00')
const showParamModal = ref(false)
const showSchemeModal = ref(false)
const appliedParams = ref<TestRequestPayload>({ ...defaultParams })
const draftParams = ref<TestRequestPayload>({ ...defaultParams })
const inferMenuExpanded = ref(true)
const selectedSubfunction = ref<(typeof subfunctionOptions)[number]>('专家论文合作关系构建')
const testSubfunctionOpen = ref(false)
const developerSubfunctionOpen = ref(false)
const previewViewportRef = ref<HTMLElement | null>(null)
const previewNodes = ref<Record<NodeId, NodeLayout>>({ ...defaultNodeLayout })
const draggingNodeId = ref<NodeId | null>(null)
const dragOrigin = ref({ mouseX: 0, mouseY: 0, x: 0, y: 0 })

const result = computed(() => apiExample.value?.structuredResult)
const authorA = computed(() => result.value?.authorList?.[0] || '张伟')
const authorB = computed(() => result.value?.authorList?.[1] || '李明')
const rawAuthorUnits = computed(() => (result.value?.authorUnits || []).filter(Boolean))
const previewAuthorUnits = computed(() => {
  const units = rawAuthorUnits.value
  return [
    units[0] || '清华大学',
    units[1] || units[0] || '北京大学',
  ]
})
const detailAuthorUnitsText = computed(() => rawAuthorUnits.value.join(' / ') || '清华大学 / 北京大学')
const unitA = computed(() => previewAuthorUnits.value[0])
const unitB = computed(() => previewAuthorUnits.value[1])
const paperCount = computed(() => result.value?.cooperationPaperCount ?? 286)
const previewTopics = computed(() => result.value?.paperTopics || ['社区发现', '学术图谱', '知识图谱', '合作网络'])
const detailTopicsText = computed(() => (result.value?.paperTopics || ['社区发现', '学术图谱', '知识图谱', '合作网络']).join('、'))
const period = computed(() => result.value?.cooperationTimeRange?.displayText || '2019 - 2026')
const periodCompact = computed(() => period.value.replace(/\s*[-–—]\s*/g, '-'))
const citation = computed(() => result.value?.citation || { total: 8420, max: 620 })
const frequency = computed(() => result.value?.cooperationFrequency ?? 36)
const impactScore = computed(() => result.value?.academicImpactScore ?? 87.5)
const stableTeamMembers = computed(() => result.value?.stableTeamMembers || ['王志远', '孙明辉', '徐晨曦'])
const coreCollaborators = computed(() => result.value?.coreCollaborators || ['王志远', '孙明辉', '徐晨曦'])
const sharedContributionTags = computed(() => result.value?.sharedContribution || ['高水平合作论文', '高被引学术成果', '跨机构协同研究'])

const journalSummary = computed(() => {
  const journal = result.value?.journalLevelCount || { A类期刊: 132 }
  const conference = result.value?.conferenceLevelCount || { A类会议: 52 }
  const left = Object.entries(journal).map(([key, value]) => `${key}×${value}`).join(' / ')
  const right = Object.entries(conference).map(([key, value]) => `${key}×${value}`).join(' / ')
  return [left, right].filter(Boolean).join(' / ') || 'A类期刊132 / A类会议52'
})

const cooperationMetrics = computed(() => [
  journalSummary.value,
  `总被引${citation.value.total}`,
  `最高${citation.value.max}`,
  `评分${impactScore.value}`,
])
const stableTeamMembersText = computed(() => stableTeamMembers.value.join('、'))
const coreCollaboratorsText = computed(() => coreCollaborators.value.join('、'))

const rows = computed(() => [
  ['作者列表', `${authorA.value}、${authorB.value}`],
  ['作者单位', detailAuthorUnitsText.value],
  ['合作发表时间', period.value],
  ['论文主题', detailTopicsText.value],
  ['合作论文数量', `共同论文${paperCount.value}篇`],
  ['期刊/会议级别', journalSummary.value],
  ['论文被引情况', `总被引${citation.value.total} / 最高${citation.value.max}`],
  ['合作频次', `${frequency.value}次`],
  ['学术影响力', `核心贡献评分${impactScore.value}`],
  ['稳定团队成员', stableTeamMembersText.value || '—'],
  ['核心合作人员', coreCollaboratorsText.value || '—'],
  ['共同贡献', sharedContributionTags.value.join('、') || '—'],
])


const developerRequestFields = [
  { name: 'dataSource', type: 'string', required: '是', description: '数据来源：all、knowledge_graph、cnki、wanfang、web_of_science' },
  { name: 'expertAId', type: 'string', required: '是', description: '专家A唯一标识' },
  { name: 'expertBId', type: 'string', required: '是', description: '专家B唯一标识' },
  { name: 'startTime', type: 'string', required: '否', description: '开始时间，格式 YYYY-MM-DD' },
  { name: 'endTime', type: 'string', required: '否', description: '结束时间，格式 YYYY-MM-DD' },
] as const

const developerResponseFields = [
  { name: 'structuredResult', type: 'object', description: '结构化结果根对象' },
  { name: 'authorList', type: 'array', description: '作者列表' },
  { name: 'authorUnits', type: 'array', description: '作者单位，按专家A/专家B顺序输出' },
  { name: 'cooperationTimeRange', type: 'object', description: '合作发表时间范围' },
  { name: 'paperTopics', type: 'array', description: '合作论文主题列表' },
  { name: 'cooperationPaperCount', type: 'number', description: '合作论文数量' },
  { name: 'journalLevelCount', type: 'object', description: '期刊级别统计' },
  { name: 'conferenceLevelCount', type: 'object', description: '会议级别统计' },
  { name: 'citation', type: 'object', description: '论文被引情况' },
  { name: 'cooperationFrequency', type: 'number', description: '合作频次' },
  { name: 'academicImpactScore', type: 'number', description: '学术影响力/核心贡献评分' },
  { name: 'stableTeamName', type: 'string|null', description: '长期稳定合作团队名称' },
  { name: 'stableTeamMembers', type: 'array', description: '长期稳定合作团队成员' },
  { name: 'coreCollaborators', type: 'array', description: '核心合作人员' },
  { name: 'sharedContribution', type: 'array', description: '共同贡献标签' },
  { name: 'representativePapers', type: 'array', description: '代表性合作论文标题' },
] as const

const developerCodeExamples = {
  python: `import json
import requests

url = "http://127.0.0.1:8881/api/v1/scholar-paper-cooperation/demo/structured-result"

payload = {
    "dataSource": "knowledge_graph",
    "expertAId": "COOP-SCH001",
    "expertBId": "COOP-SCH002",
    "startTime": "2021-01-01",
    "endTime": "2024-12-31"
}

headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers, timeout=30)
response.raise_for_status()

result = response.json()
structured_result = result.get("structuredResult", {})

print(json.dumps(structured_result, ensure_ascii=False, indent=2))
print("稳定团队成员：", structured_result.get("stableTeamMembers", []))
print("核心合作人员：", structured_result.get("coreCollaborators", []))
print("共同贡献：", structured_result.get("sharedContribution", []))`,
  node: `const url = "http://127.0.0.1:8881/api/v1/scholar-paper-cooperation/demo/structured-result";

const payload = {
  dataSource: "knowledge_graph",
  expertAId: "COOP-SCH001",
  expertBId: "COOP-SCH002",
  startTime: "2021-01-01",
  endTime: "2024-12-31",
};

async function fetchStructuredResult() {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(\`HTTP \${response.status}\`);
  }

  const result = await response.json();
  const structuredResult = result.structuredResult ?? {};

  console.log(JSON.stringify(structuredResult, null, 2));
  console.log("稳定团队成员：", structuredResult.stableTeamMembers ?? []);
  console.log("核心合作人员：", structuredResult.coreCollaborators ?? []);
  console.log("共同贡献：", structuredResult.sharedContribution ?? []);
}

fetchStructuredResult().catch(console.error);`,
  curl: `curl --location "http://127.0.0.1:8881/api/v1/scholar-paper-cooperation/demo/structured-result" \\
  --header "Content-Type: application/json" \\
  --data '{
    "dataSource": "knowledge_graph",
    "expertAId": "COOP-SCH001",
    "expertBId": "COOP-SCH002",
    "startTime": "2021-01-01",
    "endTime": "2024-12-31"
  }'`,
} as const

const currentDeveloperCode = computed(() => developerCodeExamples[developerCodeTab.value])
const currentDeveloperCodeLines = computed(() => currentDeveloperCode.value.split('\n'))

async function copyDeveloperCode() {
  try {
    await navigator.clipboard.writeText(currentDeveloperCode.value)
    copiedCodeTab.value = developerCodeTab.value
    window.setTimeout(() => {
      if (copiedCodeTab.value === developerCodeTab.value) {
        copiedCodeTab.value = ''
      }
    }, 1600)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = currentDeveloperCode.value
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    copiedCodeTab.value = developerCodeTab.value
    window.setTimeout(() => {
      if (copiedCodeTab.value === developerCodeTab.value) {
        copiedCodeTab.value = ''
      }
    }, 1600)
  }
}

function formatNow() {
  return '2026-07-23 11:00:00'
}

function centerPoint(node: NodeLayout): Point {
  return {
    x: node.x + node.w / 2,
    y: node.y + node.h / 2,
  }
}

function clampPoint(point: Point): Point {
  return {
    x: Math.min(99.2, Math.max(0.8, point.x)),
    y: Math.min(99.2, Math.max(0.8, point.y)),
  }
}

function edgeAnchor(node: NodeLayout, target: Point): Point {
  const origin = centerPoint(node)
  const dx = target.x - origin.x
  const dy = target.y - origin.y
  if (dx === 0 && dy === 0) {
    return origin
  }
  const halfW = node.w / 2
  const halfH = node.h / 2
  const scale = 1 / Math.max(Math.abs(dx) / halfW || 0, Math.abs(dy) / halfH || 0)
  return clampPoint({
    x: origin.x + dx * scale,
    y: origin.y + dy * scale,
  })
}

function linePath(start: Point, end: Point) {
  const safeStart = clampPoint(start)
  const safeEnd = clampPoint(end)
  return `M ${safeStart.x} ${safeStart.y} L ${safeEnd.x} ${safeEnd.y}`
}

function curvePath(start: Point, end: Point, controlA: Point, controlB: Point) {
  const safeStart = clampPoint(start)
  const safeEnd = clampPoint(end)
  const safeControlA = clampPoint(controlA)
  const safeControlB = clampPoint(controlB)
  return `M ${safeStart.x} ${safeStart.y} C ${safeControlA.x} ${safeControlA.y}, ${safeControlB.x} ${safeControlB.y}, ${safeEnd.x} ${safeEnd.y}`
}

function linkedCurve(start: Point, end: Point, startDepth: number, endDepth: number) {
  const dx = end.x - start.x
  return curvePath(
    start,
    end,
    { x: start.x + dx * 0.22, y: start.y + startDepth },
    { x: end.x - dx * 0.22, y: end.y - endDepth },
  )
}

function midpoint(a: Point, b: Point, offsetX = 0, offsetY = 0): Point {
  return {
    x: (a.x + b.x) / 2 + offsetX,
    y: (a.y + b.y) / 2 + offsetY,
  }
}

function sidePoint(node: NodeLayout, side: 'top' | 'right' | 'bottom' | 'left', ratio = 0.5): Point {
  if (side === 'top') {
    return clampPoint({ x: node.x + node.w * ratio, y: node.y })
  }
  if (side === 'right') {
    return clampPoint({ x: node.x + node.w, y: node.y + node.h * ratio })
  }
  if (side === 'bottom') {
    return clampPoint({ x: node.x + node.w * ratio, y: node.y + node.h })
  }
  return clampPoint({ x: node.x, y: node.y + node.h * ratio })
}

function nodeStyle(id: NodeId) {
  const node = previewNodes.value[id]
  return {
    left: `${node.x}%`,
    top: `${node.y}%`,
    width: `${node.w}%`,
    height: `${node.h}%`,
  }
}

const previewGraph = computed(() => {
  const expertANode = previewNodes.value.expertA
  const expertBNode = previewNodes.value.expertB
  const paperNode = previewNodes.value.paper
  const topicNode = previewNodes.value.topic
  const periodNode = previewNodes.value.period
  const contributionNode = previewNodes.value.contribution

  const topStart = sidePoint(expertANode, 'right', 0.66)
  const topEnd = sidePoint(expertBNode, 'left', 0.66)
  const authorStart = sidePoint(expertANode, 'bottom', 0.62)
  const authorEnd = sidePoint(paperNode, 'top', 0.32)
  const frequencyStart = sidePoint(expertBNode, 'bottom', 0.38)
  const frequencyEnd = sidePoint(paperNode, 'top', 0.74)
  const topicStart = sidePoint(paperNode, 'left', 0.78)
  const topicEnd = sidePoint(topicNode, 'top', 0.72)
  const periodStart = sidePoint(paperNode, 'bottom', 0.5)
  const periodEnd = sidePoint(periodNode, 'top', 0.5)
  const contributionStart = sidePoint(paperNode, 'right', 0.74)
  const contributionEnd = sidePoint(contributionNode, 'top', 0.22)

  return {
    topPath: linePath(topStart, topEnd),
    authorPath: curvePath(
      authorStart,
      authorEnd,
      { x: authorStart.x + 1.5, y: authorStart.y + 16 },
      { x: authorEnd.x - 11, y: authorEnd.y + 6 },
    ),
    frequencyPath: curvePath(
      frequencyStart,
      frequencyEnd,
      { x: frequencyStart.x - 1.5, y: frequencyStart.y + 16 },
      { x: frequencyEnd.x + 11, y: frequencyEnd.y + 6 },
    ),
    topicPath: curvePath(
      topicStart,
      topicEnd,
      { x: topicStart.x - 10, y: topicStart.y + 8 },
      { x: topicEnd.x + 2, y: topicEnd.y + 8 },
    ),
    periodPath: linePath(periodStart, periodEnd),
    contributionPath: curvePath(
      contributionStart,
      contributionEnd,
      { x: contributionStart.x + 12, y: contributionStart.y + 4 },
      { x: contributionEnd.x - 2, y: contributionEnd.y + 7 },
    ),
    relationPill: midpoint(topStart, topEnd, 0, -0.5),
  }
})

function clampNodePosition(id: NodeId, nextX: number, nextY: number) {
  const node = previewNodes.value[id]
  return {
    x: Math.min(100 - node.w, Math.max(0, nextX)),
    y: Math.min(100 - node.h, Math.max(0, nextY)),
  }
}

function handleNodeMouseMove(event: MouseEvent) {
  const nodeId = draggingNodeId.value
  const viewport = previewViewportRef.value
  if (!nodeId || !viewport) {
    return
  }
  const deltaX = ((event.clientX - dragOrigin.value.mouseX) / viewport.clientWidth) * 100
  const deltaY = ((event.clientY - dragOrigin.value.mouseY) / viewport.clientHeight) * 100
  const next = clampNodePosition(nodeId, dragOrigin.value.x + deltaX, dragOrigin.value.y + deltaY)
  previewNodes.value = {
    ...previewNodes.value,
    [nodeId]: {
      ...previewNodes.value[nodeId],
      ...next,
    },
  }
}

function stopNodeDrag() {
  draggingNodeId.value = null
  window.removeEventListener('mousemove', handleNodeMouseMove)
  window.removeEventListener('mouseup', stopNodeDrag)
}

function startNodeDrag(id: NodeId, event: MouseEvent) {
  if (event.button !== 0) {
    return
  }
  const node = previewNodes.value[id]
  draggingNodeId.value = id
  dragOrigin.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    x: node.x,
    y: node.y,
  }
  window.addEventListener('mousemove', handleNodeMouseMove)
  window.addEventListener('mouseup', stopNodeDrag)
}

function openParamModal() {
  draftParams.value = { ...appliedParams.value }
  showParamModal.value = true
}

function toggleInferMenu() {
  inferMenuExpanded.value = !inferMenuExpanded.value
}

function toggleTestSubfunction() {
  testSubfunctionOpen.value = !testSubfunctionOpen.value
  if (testSubfunctionOpen.value) {
    developerSubfunctionOpen.value = false
  }
}

function toggleDeveloperSubfunction() {
  developerSubfunctionOpen.value = !developerSubfunctionOpen.value
  if (developerSubfunctionOpen.value) {
    testSubfunctionOpen.value = false
  }
}

function selectSubfunction(option: (typeof subfunctionOptions)[number]) {
  selectedSubfunction.value = option
  testSubfunctionOpen.value = false
  developerSubfunctionOpen.value = false
}

function closeSubfunctionDropdowns() {
  testSubfunctionOpen.value = false
  developerSubfunctionOpen.value = false
}

function closeParamModal() {
  draftParams.value = { ...appliedParams.value }
  showParamModal.value = false
}

function openSchemeModal() {
  showSchemeModal.value = true
}

function closeSchemeModal() {
  showSchemeModal.value = false
}

async function runTest(payload: TestRequestPayload = appliedParams.value) {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/v1/scholar-paper-cooperation/demo/structured-result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.detail || `接口请求失败：${response.status}`)
    }
    apiExample.value = await response.json()
    appliedParams.value = { ...payload }
    previewNodes.value = { ...defaultNodeLayout }
    lastTestTime.value = formatNow()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '测试数据加载失败'
  } finally {
    loading.value = false
  }
}

async function saveAndRun() {
  const payload = { ...draftParams.value }
  if (!payload.dataSource || !payload.expertAId.trim() || !payload.expertBId.trim()) {
    error.value = '请填写 dataSource、expertAId 和 expertBId'
    return
  }
  if (payload.expertAId.trim() === payload.expertBId.trim()) {
    error.value = 'expertAId 和 expertBId 不能相同'
    return
  }
  showParamModal.value = false
  await runTest(payload)
}

onMounted(() => {
  document.addEventListener('click', closeSubfunctionDropdowns)
  void runTest()
})

onBeforeUnmount(() => {
  stopNodeDrag()
  document.removeEventListener('click', closeSubfunctionDropdowns)
})
</script>

<template>
  <main class="app-frame">
    <div class="breadcrumb"></div>

    <section class="workspace">
      <aside class="sidebar">
        <div class="brand">
          <img class="brand-logo" :src="sidebarLogo" alt="知识图谱平台" />
          <img class="brand-menu-icon" :src="sidebarMenu" alt="" aria-hidden="true" />
        </div>

        <nav class="nav-main">
          <div class="nav-root"><span class="nav-icon"><img :src="navFlowIcon" alt="" aria-hidden="true" /></span>流程编排<i>›</i></div>
          <div class="nav-root"><span class="nav-icon"><img :src="navGraphIcon" alt="" aria-hidden="true" /></span>图谱服务</div>
          <div class="nav-root active-root">
            <span class="nav-icon"><img :src="navReasonIcon" alt="" aria-hidden="true" /></span>
            知识推理服务
            <button
              class="nav-toggle"
              type="button"
              :aria-expanded="inferMenuExpanded"
              aria-label="展开或收起知识推理服务列表"
              @click="toggleInferMenu"
            >
              <i :class="{ expanded: inferMenuExpanded }">›</i>
            </button>
          </div>
          <div v-show="inferMenuExpanded" class="nav-branch">
            <span>科技专家直接关系</span>
            <span>科技节点间接关系</span>
            <span>科技两点合作成果</span>
            <span>科技专家同事关系</span>
            <span>科技专家校友关系</span>
            <span class="selected">专家论文合作关系</span>
            <span>重点科技企业关系</span>
            <span>产业链点事件关系</span>
            <span>科技产业链全景图</span>
          </div>
        </nav>

        <div class="user-box">
          <span class="avatar"></span>
          <strong>Ben</strong>
          <img class="chat-icon" :src="chatIcon" alt="" aria-hidden="true" />
        </div>
      </aside>

      <section class="main-card">
        <div class="inner-card">
          <header class="top-tabs">
            <div class="tabs">
              <button class="tab" :class="{ active: activePage === 'test' }" type="button" @click="activePage = 'test'">算法测试</button>
              <button class="tab" :class="{ active: activePage === 'developer' }" type="button" @click="activePage = 'developer'">开发者接口</button>
            </div>
            <button class="scheme-btn" type="button" @click="openSchemeModal">ⓘ 技术方案</button>
          </header>

          <template v-if="activePage === 'test'">
            <div class="control-row">
              <label class="select-label">子功能名称：<span class="info">ⓘ</span></label>
              <div class="select-dropdown" :class="{ open: testSubfunctionOpen }">
                <button class="select-box" type="button" @click.stop="toggleTestSubfunction">
                  {{ selectedSubfunction }} <span>⌄</span>
                </button>
                <div v-if="testSubfunctionOpen" class="select-dropdown-menu">
                  <button
                    v-for="option in subfunctionOptions"
                    :key="`test-${option}`"
                    class="select-dropdown-item"
                    type="button"
                    @click.stop="selectSubfunction(option)"
                  >
                    {{ option }}
                  </button>
                </div>
              </div>
              <div class="control-actions">
                <button class="outline-btn" type="button" @click="openParamModal">参数设置</button>
                <button class="primary-btn" type="button" @click="runTest()">{{ loading ? '测试中' : '执行测试' }}</button>
              </div>
            </div>

            <p v-if="error" class="error-text">{{ error }}</p>

            <section class="result-shell">
              <div class="result-head">
                <div class="preview-head">
                  <h2>测试结果预览</h2>
                  <span>最近测试时间：　{{ lastTestTime }}</span>
                </div>
                <div class="detail-head">
                  <h2>结果详情</h2>
                  <div class="detail-tabs">
                    <button type="button" :class="{ active: activeTab === 'structured' }" @click="activeTab = 'structured'">结构化结果</button>
                    <button type="button" :class="{ active: activeTab === 'api' }" @click="activeTab = 'api'">API结果示例</button>
                  </div>
                </div>
              </div>

              <div class="result-grid">
                <div class="graph-preview">
                  <div ref="previewViewportRef" class="graph-preview-viewport">
                    <div class="graph-preview-board">
                      <svg class="graph-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                        <path class="line purple" :d="previewGraph.topPath" />
                        <path class="line blue" :d="previewGraph.authorPath" />
                        <path class="line green" :d="previewGraph.frequencyPath" />
                        <path class="line green" :d="previewGraph.topicPath" />
                        <path class="line dashed" :d="previewGraph.periodPath" />
                        <path class="line orange" :d="previewGraph.contributionPath" />
                      </svg>

                      <div
                        class="relation-pill"
                        :style="{ left: `${previewGraph.relationPill.x}%`, top: `${previewGraph.relationPill.y}%` }"
                      >
                        论文合作
                      </div>

                      <article
                        class="node node-a expert-card"
                        :class="{ dragging: draggingNodeId === 'expertA' }"
                        :style="nodeStyle('expertA')"
                        @mousedown="startNodeDrag('expertA', $event)"
                      >
                        <span class="card-corner-label">专家A</span>
                        <div class="expert-card-body">
                          <span class="badge-circle badge-expert" aria-hidden="true"></span>
                          <div class="expert-card-copy">
                            <strong>{{ authorA }}</strong>
                            <small>{{ unitA }}</small>
                          </div>
                        </div>
                      </article>

                      <article
                        class="node node-b expert-card"
                        :class="{ dragging: draggingNodeId === 'expertB' }"
                        :style="nodeStyle('expertB')"
                        @mousedown="startNodeDrag('expertB', $event)"
                      >
                        <span class="card-corner-label">专家B</span>
                        <div class="expert-card-body">
                          <span class="badge-circle badge-expert" aria-hidden="true"></span>
                          <div class="expert-card-copy">
                            <strong>{{ authorB }}</strong>
                            <small>{{ unitB }}</small>
                          </div>
                        </div>
                      </article>

                      <article
                        class="node paper-node"
                        :class="{ dragging: draggingNodeId === 'paper' }"
                        :style="nodeStyle('paper')"
                        @mousedown="startNodeDrag('paper', $event)"
                      >
                        <div class="paper-card-body">
                          <span class="badge-circle badge-paper" aria-hidden="true"></span>
                          <div class="paper-copy">
                            <strong>合作论文</strong>
                            <div class="paper-metric">共同论文 <em>{{ paperCount }}</em> 篇</div>
                            <div class="paper-metric">合作频次 <em>{{ frequency }}</em> 次</div>
                            <div class="paper-metric-chip-row">
                              <span
                                v-for="(metric, index) in cooperationMetrics"
                                :key="metric"
                                :class="{ wide: index === 0 }"
                              >
                                {{ metric }}
                              </span>
                            </div>
                          </div>
                        </div>
                      </article>

                      <article
                        class="node topic-node"
                        :class="{ dragging: draggingNodeId === 'topic' }"
                        :style="nodeStyle('topic')"
                        @mousedown="startNodeDrag('topic', $event)"
                      >
                        <div class="summary-card-body">
                          <span class="badge-circle badge-topic" aria-hidden="true"></span>
                          <div class="summary-copy">
                            <strong>论文主题</strong>
                            <div class="topic-chip-row">
                              <span v-for="topic in previewTopics" :key="topic">{{ topic }}</span>
                            </div>
                          </div>
                        </div>
                      </article>

                      <article
                        class="node period-node"
                        :class="{ dragging: draggingNodeId === 'period' }"
                        :style="nodeStyle('period')"
                        @mousedown="startNodeDrag('period', $event)"
                      >
                        <div class="summary-card-body">
                          <span class="badge-circle badge-period" aria-hidden="true"></span>
                          <div class="summary-copy">
                            <strong>合作周期</strong>
                            <small>{{ periodCompact }}</small>
                          </div>
                        </div>
                      </article>

                      <article
                        class="node contribution-node"
                        :class="{ dragging: draggingNodeId === 'contribution' }"
                        :style="nodeStyle('contribution')"
                        @mousedown="startNodeDrag('contribution', $event)"
                      >
                        <div class="summary-card-body impact-card-body">
                          <span class="badge-circle badge-impact" aria-hidden="true"></span>
                          <div class="summary-copy impact-copy">
                            <strong>共同贡献</strong>
                            <div class="impact-tag-row">
                              <span v-for="tag in sharedContributionTags" :key="tag">{{ tag }}</span>
                            </div>
                            <div class="impact-info-block">
                              <span class="impact-info-label">稳定团队成员</span>
                              <span class="impact-info-value">{{ stableTeamMembersText }}</span>
                            </div>
                            <div class="impact-info-block">
                              <span class="impact-info-label">核心合作人员</span>
                              <span class="impact-info-value">{{ coreCollaboratorsText }}</span>
                            </div>
                          </div>
                        </div>
                      </article>
                    </div>
                  </div>
                </div>

                <div class="detail-column">
                  <div class="detail-table" v-if="activeTab === 'structured'">
                    <div v-for="row in rows" :key="row[0]" class="table-row">
                      <span>{{ row[0] }}</span>
                      <strong>{{ row[1] }}</strong>
                    </div>
                  </div>
                  <div v-else class="api-panel-shell">
                    <pre class="api-panel">{{ JSON.stringify(apiExample, null, 2) }}</pre>
                  </div>
                </div>
              </div>
            </section>
          </template>

          <section v-else class="developer-shell">
            <div class="developer-toolbar">
              <div class="developer-toolbar-main">
                <label class="select-label">子功能名称：</label>
                <div class="select-dropdown developer-select-dropdown" :class="{ open: developerSubfunctionOpen }">
                  <button class="select-box developer-select" type="button" @click.stop="toggleDeveloperSubfunction">
                    {{ selectedSubfunction }} <span>⌄</span>
                  </button>
                  <div v-if="developerSubfunctionOpen" class="select-dropdown-menu">
                    <button
                      v-for="option in subfunctionOptions"
                      :key="`developer-${option}`"
                      class="select-dropdown-item"
                      type="button"
                      @click.stop="selectSubfunction(option)"
                    >
                      {{ option }}
                    </button>
                  </div>
                </div>
                <span class="developer-info">ⓘ</span>
              </div>
              <div class="developer-toolbar-side">
                <div class="developer-meta-item">
                  <span>接口路径：</span>
                  <div class="developer-meta-box">/api/v1/scholar-paper-cooperation/demo/structured-result</div>
                </div>
                <div class="developer-method"><span>请求方法：</span><strong>POST</strong></div>
              </div>
            </div>

            <div class="developer-panels">
              <section class="developer-card">
                <div class="developer-card-title">请求参数</div>
                <div class="developer-table-shell">
                  <div class="developer-table developer-request-table">
                    <div class="developer-table-head developer-table-row four-col">
                      <span>字段名</span>
                      <span>类型</span>
                      <span>必填</span>
                      <span>说明</span>
                    </div>
                    <div v-for="field in developerRequestFields" :key="field.name" class="developer-table-row four-col">
                      <strong>{{ field.name }}</strong>
                      <span>{{ field.type }}</span>
                      <span>{{ field.required }}</span>
                      <span>{{ field.description }}</span>
                    </div>
                  </div>
                </div>
              </section>

              <section class="developer-card">
                <div class="developer-card-title">返回字段</div>
                <div class="developer-table-shell">
                  <div class="developer-table">
                    <div class="developer-table-head developer-table-row three-col">
                      <span>字段名</span>
                      <span>类型</span>
                      <span>说明</span>
                    </div>
                    <div v-for="field in developerResponseFields" :key="field.name" class="developer-table-row three-col">
                      <strong>{{ field.name }}</strong>
                      <span>{{ field.type }}</span>
                      <span>{{ field.description }}</span>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            <section class="developer-code-shell">
              <div class="developer-code-head">
                <div class="developer-card-title">代码示例</div>
                <div class="developer-language-tabs">
                  <button type="button" :class="{ active: developerCodeTab === 'python' }" @click="developerCodeTab = 'python'">Python</button>
                  <button type="button" :class="{ active: developerCodeTab === 'node' }" @click="developerCodeTab = 'node'">Node.js</button>
                  <button type="button" :class="{ active: developerCodeTab === 'curl' }" @click="developerCodeTab = 'curl'">cURL</button>
                </div>
              </div>

              <div class="developer-code-block">
                <div class="developer-code-scroll">
                  <div v-for="(line, index) in currentDeveloperCodeLines" :key="`${developerCodeTab}-${index}`" class="developer-code-line">
                    <span class="developer-code-number">{{ index + 1 }}</span>
                    <code class="developer-code-text">{{ line || ' ' }}</code>
                  </div>
                </div>
                <div class="developer-code-footer">
                  <button
                    class="developer-copy-btn"
                    type="button"
                    :title="copiedCodeTab === developerCodeTab ? '已复制' : '复制示例'"
                    @click="copyDeveloperCode"
                  >
                    {{ copiedCodeTab === developerCodeTab ? '已复制' : '复制' }}
                  </button>
                </div>
              </div>
            </section>
          </section>
        </div>
      </section>
    </section>

    <div v-if="showParamModal" class="modal-mask" @click.self="closeParamModal">
      <section class="param-modal">
        <header class="param-modal-header">
          <div class="param-modal-title-wrap">
            <span class="param-modal-icon">✻</span>
            <h3>测试参数设置</h3>
          </div>
          <div class="param-modal-meta">
            <span><em>*</em> 为必填项</span>
            <button class="param-close" type="button" @click="closeParamModal">×</button>
          </div>
        </header>

        <div class="param-form">
          <label class="param-row">
            <span class="param-label required">dataSource</span>
            <select v-model="draftParams.dataSource" class="param-field param-select">
              <option v-for="option in dataSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>

          <label class="param-row">
            <span class="param-label required">expertAId</span>
            <input v-model="draftParams.expertAId" class="param-field" type="text" placeholder="请输入 expertAId" />
          </label>

          <label class="param-row">
            <span class="param-label required">expertBId</span>
            <input v-model="draftParams.expertBId" class="param-field" type="text" placeholder="请输入 expertBId" />
          </label>

          <div class="param-row">
            <span class="param-label">timeRange</span>
            <div class="param-date-range">
              <input v-model="draftParams.startTime" class="param-field" type="date" />
              <span class="date-separator">-</span>
              <input v-model="draftParams.endTime" class="param-field" type="date" />
            </div>
          </div>
        </div>

        <footer class="param-modal-footer">
          <button class="param-cancel" type="button" @click="closeParamModal">取消</button>
          <button class="param-save" type="button" @click="saveAndRun">保存并执行</button>
        </footer>
      </section>
    </div>

    <div v-if="showSchemeModal" class="modal-mask" @click.self="closeSchemeModal">
      <section class="scheme-modal">
        <header class="scheme-modal-header">
          <h3>技术方案</h3>
          <button class="scheme-close" type="button" @click="closeSchemeModal">×</button>
        </header>

        <div class="scheme-modal-body">
          <section class="scheme-section">
            <h4>功能描述</h4>
            <div class="scheme-description-card">
              基于科技专家发表论文的作者列表、作者单位、合作发表时间、论文主题与被引数据，通过作者关联、合作频次与影响力评估算法构建论文合作关系网络，输出合作论文、期刊/会议级别、研究方向、合作成果、长期稳定团队和核心合作人员。
            </div>
          </section>

          <section class="scheme-section">
            <h4>推理流程</h4>
            <div class="scheme-flow">
              <article class="scheme-step-card">
                <div class="scheme-step-icon">↓</div>
                <strong>输入数据</strong>
                <p>接收专家ID及相关筛选参数作为请求输入</p>
              </article>
              <span class="scheme-arrow">→</span>
              <article class="scheme-step-card">
                <div class="scheme-step-icon">⚙</div>
                <strong>标准化处理</strong>
                <p>统一作者、机构、时间和主题字段格式</p>
              </article>
              <span class="scheme-arrow">→</span>
              <article class="scheme-step-card">
                <div class="scheme-step-icon">⌘</div>
                <strong>合作推理</strong>
                <p>共同论文、合作次数、级别分布、被引情况</p>
              </article>
              <span class="scheme-arrow">→</span>
              <article class="scheme-step-card">
                <div class="scheme-step-icon">▤</div>
                <strong>结果输出</strong>
                <p>输出包含合作网络、稳定团队、核心人员、影响力结论</p>
              </article>
            </div>
          </section>
        </div>
      </section>
    </div>
  </main>
</template>
