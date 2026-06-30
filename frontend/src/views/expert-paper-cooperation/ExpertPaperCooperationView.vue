<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'

import iconCalendar from '../../assets/icons/icon-calendar.svg'
import iconClose from '../../assets/icons/icon-close.svg'
import iconCopy from '../../assets/icons/icon-copy.svg'
import iconInfo from '../../assets/icons/icon-info.svg'
import iconModalSetting from '../../assets/icons/icon-modal-setting.svg'
import iconSelectArrow from '../../assets/icons/icon-select-arrow.svg'
import flowReasoning from '../../assets/icons/技术方案-关系推理.svg'
import flowStandardize from '../../assets/icons/技术方案-标准化处理.svg'
import flowOutput from '../../assets/icons/技术方案-结果输出.svg'
import flowInput from '../../assets/icons/技术方案-输入数据.svg'
import flowArrow from '../../assets/icons/技术方案-箭头.svg'
import { fetchExpertPaperCooperationStructuredResult } from '../../api/expert-paper-cooperation'
import type {
  DataSource,
  ExpertPaperCooperationDemoRequest,
  ExpertPaperCooperationStructuredResultOnlyResponse,
} from './types'

const endpoint = '/api/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result'

const subfunctionOptions = ['专家论文合作关系构建'] as const
const dataSourceOptions: Array<{ label: string; value: DataSource }> = [
  { label: '全部', value: 'all' },
  { label: '知识图谱', value: 'knowledge_graph' },
  { label: '知网', value: 'cnki' },
  { label: '万方', value: 'wanfang' },
  { label: 'Web of Science', value: 'web_of_science' },
]

const defaultParams: ExpertPaperCooperationDemoRequest = {
  dataSource: 'knowledge_graph',
  expertAId: '4P566No1',
  expertBId: 'd492835p',
  startTime: '2021-01-01',
  endTime: '2024-12-31',
}

const activeView = ref<'test' | 'developer'>('test')
const resultMode = ref<'structured' | 'api'>('structured')
const activeCode = ref<'python' | 'node' | 'curl'>('python')
const selectedSubfunction = ref<(typeof subfunctionOptions)[number]>('专家论文合作关系构建')
const showConfigModal = ref(false)
const showTechModal = ref(false)
const loading = ref(false)
const copied = ref(false)
const error = ref('')
const lastTestTime = ref('待执行')
const apiExample = ref<ExpertPaperCooperationStructuredResultOnlyResponse | null>(null)
const appliedParams = ref<ExpertPaperCooperationDemoRequest>({ ...defaultParams })
const draftParams = ref<ExpertPaperCooperationDemoRequest>({ ...defaultParams })

const result = computed(() => apiExample.value?.structuredResult ?? null)
const authorA = computed(() => result.value?.authorList?.[0] ?? '专家 A')
const authorB = computed(() => result.value?.authorList?.[1] ?? '专家 B')
const authorUnitA = computed(() => result.value?.authorUnits?.[0] ?? '待返回')
const authorUnitB = computed(() => result.value?.authorUnits?.[1] ?? '待返回')
const allPaperTopics = computed(() => result.value?.paperTopics ?? [])
const graphPreviewTopics = computed(() => allPaperTopics.value.slice(0, 2))

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength)}...`
}

const authorUnitPreviewA = computed(() => truncateText(authorUnitA.value, 16))
const authorUnitPreviewB = computed(() => truncateText(authorUnitB.value, 16))
const stableTeamMembers = computed(() => result.value?.stableTeamMembers ?? [])
const coreCollaborators = computed(() => result.value?.coreCollaborators ?? [])
const contributionTags = computed(() => result.value?.sharedContribution ?? [])
const periodText = computed(() => result.value?.cooperationTimeRange?.displayText ?? '待返回')
const paperCount = computed(() => result.value?.cooperationPaperCount ?? 0)
const citation = computed(() => result.value?.citation ?? { total: 0, max: 0 })
const impactScore = computed(() => result.value?.academicImpactScore ?? 0)
const frequency = computed(() => result.value?.cooperationFrequency ?? 0)
const topicText = computed(() => allPaperTopics.value.join('、') || '—')
const stableTeamText = computed(() => stableTeamMembers.value.join('、') || '—')
const collaboratorText = computed(() => coreCollaborators.value.join('、') || '—')
const contributionText = computed(() => contributionTags.value.join('、') || '—')
const journalSummary = computed(() => {
  if (!result.value) {
    return '—'
  }
  const parts = [
    ...Object.entries(result.value.journalLevelCount ?? {}).map(([key, value]) => `${key}×${value}`),
    ...Object.entries(result.value.conferenceLevelCount ?? {}).map(([key, value]) => `${key}×${value}`),
  ]
  return parts.join(' / ') || '—'
})

const structuredRows = computed(() => [
  ['作者列表', `${authorA.value}、${authorB.value}`],
  ['作者单位', `${authorUnitA.value} / ${authorUnitB.value}`],
  ['合作发表时间', periodText.value || '—'],
  ['论文主题', topicText.value],
  ['合作论文数量', paperCount.value ? `${paperCount.value} 篇` : '—'],
  ['期刊/会议级别', journalSummary.value],
  ['论文被引情况', `总被引${citation.value.total} / 最高${citation.value.max}`],
  ['合作频次', frequency.value ? `${frequency.value} 次` : '—'],
  ['学术影响力评分', impactScore.value ? `${impactScore.value}` : '—'],
  ['稳定团队成员', stableTeamText.value],
  ['核心合作人员', collaboratorText.value],
  ['合作贡献', contributionText.value],
])

const developerRequestFields = [
  { name: 'dataSource', type: 'string', required: '是', description: '论文数据源' },
  { name: 'expertAId', type: 'string', required: '是', description: '专家 A 唯一标识' },
  { name: 'expertBId', type: 'string', required: '是', description: '专家 B 唯一标识' },
  { name: 'startTime', type: 'string', required: '否', description: '开始时间，格式 YYYY-MM-DD' },
  { name: 'endTime', type: 'string', required: '否', description: '结束时间，格式 YYYY-MM-DD' },
] as const

const developerResponseFields = [
  { name: 'structuredResult', type: 'object', description: '结构化结果根对象' },
  { name: 'authorList', type: 'array', description: '作者列表' },
  { name: 'authorUnits', type: 'array', description: '作者单位列表' },
  { name: 'cooperationTimeRange', type: 'object', description: '合作发表时间范围' },
  { name: 'paperTopics', type: 'array', description: '合作论文主题列表' },
  { name: 'cooperationPaperCount', type: 'number', description: '合作论文数量' },
  { name: 'journalLevelCount', type: 'object', description: '期刊级别统计' },
  { name: 'conferenceLevelCount', type: 'object', description: '会议级别统计' },
  { name: 'citation', type: 'object', description: '论文被引情况' },
  { name: 'cooperationFrequency', type: 'number', description: '合作频次' },
  { name: 'academicImpactScore', type: 'number', description: '学术影响力评分' },
  { name: 'stableTeamMembers', type: 'array', description: '长期稳定合作团队成员' },
  { name: 'coreCollaborators', type: 'array', description: '核心合作人员' },
  { name: 'sharedContribution', type: 'array', description: '合作贡献标签' },
] as const

const codeSamples = computed(() => ({
  python: `import json\nimport requests\n\nurl = "http://127.0.0.1:8891${endpoint}"\npayload = {\n    "dataSource": "knowledge_graph",\n    "expertAId": "4P566No1",\n    "expertBId": "d492835p",\n    "startTime": "2021-01-01",\n    "endTime": "2024-12-31"\n}\n\nresponse = requests.post(url, json=payload, timeout=30)\nresponse.raise_for_status()\nresult = response.json()\nprint(json.dumps(result.get("structuredResult", {}), ensure_ascii=False, indent=2))`,
  node: `const url = "http://127.0.0.1:8891${endpoint}";\n\nconst payload = {\n  dataSource: "knowledge_graph",\n  expertAId: "4P566No1",\n  expertBId: "d492835p",\n  startTime: "2021-01-01",\n  endTime: "2024-12-31",\n};\n\nasync function fetchStructuredResult() {\n  const response = await fetch(url, {\n    method: "POST",\n    headers: { "Content-Type": "application/json" },\n    body: JSON.stringify(payload),\n  });\n\n  if (!response.ok) throw new Error(\`HTTP \${response.status}\`);\n  const result = await response.json();\n  console.log(result.structuredResult);\n}\n\nfetchStructuredResult().catch(console.error);`,
  curl: `curl --location "http://127.0.0.1:8891${endpoint}" \\\n  --header "Content-Type: application/json" \\\n  --data '{\n    "dataSource": "knowledge_graph",\n    "expertAId": "4P566No1",\n    "expertBId": "d492835p",\n    "startTime": "2021-01-01",\n    "endTime": "2024-12-31"\n  }'`,
}))

function formatNow() {
  return new Date().toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function extractErrorMessage(raw: unknown) {
  if (axios.isAxiosError(raw)) {
    const detail = raw.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  if (raw instanceof Error) {
    return raw.message
  }
  return '执行测试失败，请稍后重试。'
}

async function runTest(payload: ExpertPaperCooperationDemoRequest = appliedParams.value) {
  loading.value = true
  error.value = ''
  try {
    apiExample.value = await fetchExpertPaperCooperationStructuredResult(payload)
    lastTestTime.value = formatNow()
    resultMode.value = 'structured'
  } catch (rawError) {
    error.value = extractErrorMessage(rawError)
  } finally {
    loading.value = false
  }
}

async function handleSaveAndRun() {
  appliedParams.value = { ...draftParams.value }
  showConfigModal.value = false
  await runTest(appliedParams.value)
}

async function handleCopyCode() {
  try {
    await navigator.clipboard?.writeText(codeSamples.value[activeCode.value])
  } catch {
    // Keep UI feedback even when clipboard permissions are unavailable.
  }
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1200)
}

onMounted(() => {
  void runTest()
})
</script>

<template>
  <div class="expert-colleague">
    <header class="expert-colleague__toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button class="kg-tabs__item" :class="{ 'is-active': activeView === 'test' }" type="button" @click="activeView = 'test'">
          算法测试
        </button>
        <button class="kg-tabs__item" :class="{ 'is-active': activeView === 'developer' }" type="button" @click="activeView = 'developer'">
          开发者接口
        </button>
      </div>
      <button class="kg-button kg-button--text expert-colleague__tech" type="button" @click="showTechModal = true">
        <img :src="iconInfo" alt="" aria-hidden="true" />
        技术方案
      </button>
    </header>

    <section v-if="activeView === 'test'" class="search-panel-inline">
      <label class="search-panel-inline__field">
        <span>子功能名称：</span>
        <select v-model="selectedSubfunction" class="select-with-icon">
          <option v-for="option in subfunctionOptions" :key="option" :value="option">{{ option }}</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
        <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
      </label>
      <div class="search-panel-inline__actions">
        <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = true">参数设置</button>
        <button class="kg-button" type="button" :disabled="loading" @click="runTest()">
          {{ loading ? '测试中...' : '执行测试' }}
        </button>
      </div>
    </section>

    <div v-if="activeView === 'test'" class="expert-colleague__main">
      <section class="kg-panel graph-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">测试结果预览</h2>
          <div class="graph-panel__time">
            <span>最近测试时间：</span>
            <strong>{{ lastTestTime }}</strong>
          </div>
        </div>
        <div class="graph-panel__canvas">
          <div v-if="loading" class="graph-panel__state graph-panel__state--loading">正在生成合作关系图谱预览...</div>
          <div v-else-if="error" class="graph-panel__state graph-panel__state--error">{{ error }}</div>
          <div v-else-if="!result" class="graph-panel__state">执行测试后将在这里展示合作关系图谱。</div>
          <svg v-else viewBox="0 0 720 520" role="img" aria-label="专家论文合作关系图谱预览">
            <defs>
              <marker id="paper-arrow-blue" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="#4080ff" />
              </marker>
              <marker id="paper-arrow-purple" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="#722ed1" />
              </marker>
              <marker id="paper-arrow-green" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="#00b42a" />
              </marker>
              <marker id="paper-arrow-orange" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="#ff7d00" />
              </marker>
              <marker id="paper-arrow-gray" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                <path d="M0,0 L8,4 L0,8 Z" fill="#8a93a3" />
              </marker>
            </defs>

            <g class="graph-edges">
              <path class="edge edge--purple" d="M183 78 H534" marker-end="url(#paper-arrow-purple)" />
              <text class="edge-label edge-label--purple" x="320" y="62">论文合作</text>

              <path class="edge edge--blue" d="M134 118 C168 182, 240 204, 302 234" marker-end="url(#paper-arrow-blue)" />
              <text class="edge-label edge-label--blue" x="166" y="176">参与合作</text>

              <path class="edge edge--green" d="M586 118 C552 182, 480 204, 418 234" marker-end="url(#paper-arrow-green)" />
              <text class="edge-label edge-label--green" x="494" y="176">参与合作</text>

              <path class="edge edge--green" d="M302 308 C236 314, 166 338, 122 382" marker-end="url(#paper-arrow-green)" />
              <text class="edge-label edge-label--green" x="160" y="324">论文主题</text>

              <path class="edge edge--dash" d="M360 308 V382" marker-end="url(#paper-arrow-gray)" />
              <text class="edge-label" x="378" y="344">合作周期</text>

              <path class="edge edge--orange" d="M418 308 C480 320, 542 342, 604 366" marker-end="url(#paper-arrow-orange)" />
              <text class="edge-label edge-label--orange" x="526" y="324">合作贡献</text>
            </g>

            <g class="box box--blue" transform="translate(28 36)">
              <rect width="156" height="82" rx="8" />
              <text x="78" y="28">专家A</text>
              <text x="78" y="52">{{ authorA }}</text>
              <foreignObject x="12" y="60" width="132" height="18">
                <div class="svg-unit-text" :title="authorUnitA">{{ authorUnitPreviewA }}</div>
              </foreignObject>
            </g>

            <g class="box box--green" transform="translate(534 36)">
              <rect width="156" height="82" rx="8" />
              <text x="78" y="28">专家B</text>
              <text x="78" y="52">{{ authorB }}</text>
              <foreignObject x="12" y="60" width="132" height="18">
                <div class="svg-unit-text" :title="authorUnitB">{{ authorUnitPreviewB }}</div>
              </foreignObject>
            </g>

            <g class="box box--purple" transform="translate(246 234)">
              <rect width="228" height="74" rx="8" />
              <text x="114" y="28">合作论文</text>
              <text x="114" y="50">共同论文 {{ paperCount }} 篇 / 合作频次 {{ frequency }} 次</text>
            </g>

            <g class="box box--green" transform="translate(16 382)">
              <rect width="218" height="112" rx="8" />
              <text x="109" y="28">论文主题</text>
              <template v-for="(item, index) in graphPreviewTopics" :key="item">
                <rect class="chip" :x="24" :y="46 + index * 30" width="170" height="22" rx="6" />
                <text :x="109" :y="61 + index * 30">{{ truncateText(item, 24) }}</text>
              </template>
            </g>

            <g class="box box--gold" transform="translate(286 392)">
              <rect width="150" height="70" rx="8" />
              <text x="75" y="28">合作周期</text>
              <text x="75" y="50">{{ periodText }}</text>
            </g>

            <g class="box box--orange" transform="translate(490 372)">
              <rect width="198" height="122" rx="8" />
              <text x="99" y="28">合作贡献</text>
              <text x="99" y="52">{{ journalSummary }}</text>
              <text x="99" y="74">总被引 {{ citation.total }} / 最高 {{ citation.max }}</text>
              <text x="99" y="96">评分 {{ impactScore }}</text>
            </g>
          </svg>
        </div>
      </section>

      <aside class="expert-colleague__side">
        <section class="kg-panel result-panel">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">结果详情</h2>
            <div class="result-panel__tabs">
              <button :class="{ 'is-active': resultMode === 'structured' }" type="button" @click="resultMode = 'structured'">结构化结果</button>
              <button :class="{ 'is-active': resultMode === 'api' }" type="button" @click="resultMode = 'api'">API结果示例</button>
            </div>
          </div>
          <dl v-if="resultMode === 'structured'" class="result-panel__table scroll-on-demand">
            <div
              v-for="([label, value]) in structuredRows"
              :key="label"
              :class="{ 'is-long': ['论文主题', '稳定团队成员', '核心合作人员', '合作贡献'].includes(label) }"
            >
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </dl>
          <pre v-else class="result-panel__code scroll-on-demand">{{ JSON.stringify(apiExample, null, 2) }}</pre>
        </section>
      </aside>
    </div>

    <section v-else class="developer-view">
      <div class="developer-view__meta">
        <label>
          <span>子功能名称：</span>
          <select v-model="selectedSubfunction" class="select-with-icon">
            <option v-for="option in subfunctionOptions" :key="option" :value="option">{{ option }}</option>
          </select>
          <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
        </label>
        <label>
          <span>接口路径：</span>
          <input :value="endpoint" readonly />
        </label>
        <span>请求方法：POST</span>
      </div>

      <div class="developer-view__cards">
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
          <div class="developer-table-wrap scroll-on-demand">
            <table class="developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="field in developerRequestFields" :key="field.name">
                  <td>{{ field.name }}</td>
                  <td>{{ field.type }}</td>
                  <td>{{ field.required }}</td>
                  <td>{{ field.description }}</td>
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
                <tr v-for="field in developerResponseFields" :key="field.name">
                  <td>{{ field.name }}</td>
                  <td>{{ field.type }}</td>
                  <td>{{ field.description }}</td>
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
        <button class="developer-code__copy" :class="{ 'is-copied': copied }" type="button" @click="handleCopyCode">
          <span v-if="copied" aria-hidden="true">✓</span>
          <img v-else :src="iconCopy" alt="" aria-hidden="true" />
        </button>
        <pre>{{ codeSamples[activeCode] }}</pre>
      </section>
    </section>

    <div v-if="showConfigModal || showTechModal" class="modal-mask" @click.self="showConfigModal = false; showTechModal = false">
      <section v-if="showConfigModal" class="modal modal--config" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2><img :src="iconModalSetting" alt="" aria-hidden="true" />测试参数设置</h2>
          <div class="modal__header-extra">
            <span class="modal__required"><span>*</span> 为必填项</span>
            <button type="button" @click="showConfigModal = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
          </div>
        </header>
        <div class="modal__body config-form">
          <label>
            <span><i>*</i>子功能名称</span>
            <select v-model="selectedSubfunction"><option v-for="option in subfunctionOptions" :key="option">{{ option }}</option></select>
            <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          </label>
          <label>
            <span><i>*</i>数据来源</span>
            <select v-model="draftParams.dataSource">
              <option v-for="option in dataSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          </label>
          <label>
            <span><i>*</i>专家 A ID</span>
            <input v-model="draftParams.expertAId" placeholder="请输入专家 A 唯一标识" />
          </label>
          <label>
            <span><i>*</i>专家 B ID</span>
            <input v-model="draftParams.expertBId" placeholder="请输入专家 B 唯一标识" />
          </label>
          <label>
            <span><i></i>开始时间</span>
            <input v-model="draftParams.startTime" placeholder="YYYY-MM-DD" />
            <img class="calendar-icon" :src="iconCalendar" alt="" aria-hidden="true" />
          </label>
          <label>
            <span><i></i>结束时间</span>
            <input v-model="draftParams.endTime" placeholder="YYYY-MM-DD" />
            <img class="calendar-icon" :src="iconCalendar" alt="" aria-hidden="true" />
          </label>
        </div>
        <footer class="modal__footer">
          <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = false">取消</button>
          <button class="kg-button" type="button" @click="handleSaveAndRun">保存并执行</button>
        </footer>
      </section>

      <section v-if="showTechModal" class="modal modal--tech" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2>技术方案</h2>
          <button type="button" @click="showTechModal = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
        </header>
        <div class="modal__body">
          <h3 class="modal__section-title">功能描述</h3>
          <p class="modal__desc">
            该模块根据专家 A/B、时间范围和论文数据源，查询共享论文、作者清单和合作摘要，输出结构化合作结果，并在前端生成合作关系预览图。
          </p>
          <h3 class="modal__section-title">推理流程</h3>
          <div class="flow-steps">
            <div class="flow-step"><img :src="flowInput" alt="" /><strong>输入数据</strong><span>专家 ID、数据源、起止时间</span></div>
            <img class="flow-step__arrow flow-step__arrow--one" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowStandardize" alt="" /><strong>标准化处理</strong><span>主题归一、作者聚合、时间过滤</span></div>
            <img class="flow-step__arrow flow-step__arrow--two" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowReasoning" alt="" /><strong>关系推理</strong><span>合作频次、团队识别、影响力评分</span></div>
            <img class="flow-step__arrow flow-step__arrow--three" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowOutput" alt="" /><strong>结果输出</strong><span>结构化结果与图谱预览</span></div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.expert-colleague {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--space-12);
  color: var(--text-primary);
}

.expert-colleague__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
  padding: 0 var(--space-16);
}

.expert-colleague__tech {
  gap: 4px;
}

.expert-colleague__tech img {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.search-panel-inline {
  display: grid;
  grid-template-columns: 420px minmax(220px, 1fr);
  gap: var(--space-12);
  align-items: end;
  min-height: 44px;
  padding: 0 var(--space-16) var(--space-4);
}

.search-panel-inline__field {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 14px;
  align-items: center;
  gap: var(--space-8);
}

.search-panel-inline__field select {
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

.select-icon,
.calendar-icon {
  position: absolute;
  right: 10px;
  width: 14px;
  height: 14px;
  pointer-events: none;
  object-fit: contain;
}

.select-icon {
  top: 50%;
  transform: translateY(-50%);
}

.search-panel-inline__field .select-icon,
.developer-view__meta label .select-icon {
  right: 28px;
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

.expert-colleague__main {
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

.expert-colleague__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-12);
  min-height: 0;
  overflow: hidden;
}

.graph-panel,
.result-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.graph-panel__time {
  display: flex;
  gap: var(--space-12);
  color: var(--text-tertiary);
}

.graph-panel__time strong {
  font-weight: 400;
}

.graph-panel__canvas {
  display: grid;
  place-items: center;
  height: calc(100% - 68px);
  min-height: 0;
  margin: 0 var(--space-16) var(--space-16);
  padding: var(--space-16);
  background: var(--surface);
  overflow: hidden;
}

.graph-panel__canvas svg {
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  display: block;
}

.edge {
  fill: none;
  stroke-width: 2;
}

.edge--blue {
  stroke: var(--graph-blue);
}

.edge--purple {
  stroke: var(--graph-purple);
}

.edge--green {
  stroke: var(--graph-green);
}

.edge--orange {
  stroke: var(--graph-orange);
}

.edge--dash {
  stroke: var(--text-tertiary);
  stroke-dasharray: 5 5;
}

.edge--dash.edge--orange {
  stroke: var(--graph-orange);
}

.edge-label {
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 5px;
  stroke-linejoin: round;
  fill: var(--text-secondary);
  font-size: 12px;
  text-anchor: middle;
}

.edge-label--blue {
  fill: #1d4ed8;
}

.edge-label--purple {
  fill: #722ed1;
}

.edge-label--green {
  fill: #237804;
}

.edge-label--orange {
  fill: #d46b08;
}

.box rect {
  fill: #f8fbff;
  stroke: var(--graph-blue);
  stroke-width: 1.4;
}

.box text {
  fill: #174ea6;
  font-size: 12px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
}

.svg-unit-text {
  width: 132px;
  overflow: hidden;
  color: #174ea6;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.box--green rect {
  fill: #f5fff7;
  stroke: var(--graph-green);
}

.box--green text {
  fill: #237804;
}

.box--green .svg-unit-text {
  color: #237804;
}

.box--purple rect {
  fill: #fbf7ff;
  stroke: #b37feb;
}

.box--purple text {
  fill: #722ed1;
}

.box--gold rect {
  fill: #fffbe6;
  stroke: var(--graph-gold);
}

.box--gold text {
  fill: #ad6800;
}

.box--orange rect {
  fill: #fff7ed;
  stroke: var(--graph-orange);
}

.box--orange text {
  fill: #d46b08;
}

.box .chip,
.box .result-chip {
  fill: var(--surface);
}

.box .chip {
  stroke: #95de64;
}

.box .result-chip {
  stroke: var(--graph-orange);
}

.box .result-text {
  fill: #ff4d00;
  font-size: 11px;
}

.box--count rect {
  fill: #f8fbff;
  stroke: var(--graph-blue);
}

.box--count text {
  fill: var(--primary);
  font-size: 13px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
}

.box--count.box--green rect {
  fill: var(--success-subtle);
  stroke: var(--graph-green);
}

.box--count.box--green text {
  fill: #237804;
}

.box--count.box--orange rect {
  fill: var(--warning-subtle);
  stroke: var(--graph-orange);
}

.box--count.box--orange text {
  fill: #d46b08;
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
  font-size: 16px;
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
  grid-template-columns: 160px minmax(0, 1fr);
  min-height: 44px;
  border-bottom: 1px solid var(--border);
}

.result-panel__table dt,
.result-panel__table dd {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0 var(--space-16);
  font-size: 16px;
  line-height: 1.6;
}

.result-panel__table dt {
  justify-content: flex-end;
  border-right: 1px solid var(--border);
  color: var(--text-tertiary);
  font-size: 15px;
  white-space: nowrap;
}

.result-panel__table dd {
  min-width: 0;
  color: var(--text-primary);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.result-panel__table div.is-long dt,
.result-panel__table div.is-long dd {
  align-items: flex-start;
  padding-top: var(--space-12);
  padding-bottom: var(--space-12);
}

.result-panel__tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  margin-right: var(--space-8);
  padding: 0 var(--space-8);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  font-size: 12px;
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

.developer-view__meta label {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 14px;
  align-items: center;
  gap: var(--space-8);
}

.developer-view__meta input,
.developer-view__meta select,
.config-form input,
.config-form select {
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
}

.developer-view__meta select,
.config-form select {
  appearance: none;
  -webkit-appearance: none;
  background-image: none;
  padding-right: 34px;
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

.developer-view__cards > .kg-panel {
  overflow: hidden;
}

.developer-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

.developer-table-wrap {
  height: calc(100% - 52px);
  margin: 0 6px var(--space-16);
  overflow: auto;
}

.developer-table th,
.developer-table td {
  height: 36px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.developer-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  white-space: nowrap;
}

.developer-table th {
  color: var(--text-secondary);
  background: var(--surface-muted);
  font-weight: 400;
}

.developer-table td {
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.developer-table th:nth-child(1),
.developer-table td:nth-child(1) {
  width: 30%;
}

.developer-table th:nth-child(2),
.developer-table td:nth-child(2) {
  width: 18%;
}

.developer-table th:nth-child(3),
.developer-table td:nth-child(3) {
  width: 12%;
}

.developer-table th:nth-child(4),
.developer-table td:nth-child(4) {
  width: 40%;
}

.developer-view__cards .kg-panel:nth-child(2) .developer-table th:nth-child(1),
.developer-view__cards .kg-panel:nth-child(2) .developer-table td:nth-child(1) {
  width: 34%;
}

.developer-view__cards .kg-panel:nth-child(2) .developer-table th:nth-child(2),
.developer-view__cards .kg-panel:nth-child(2) .developer-table td:nth-child(2) {
  width: 18%;
}

.developer-view__cards .kg-panel:nth-child(2) .developer-table th:nth-child(3),
.developer-view__cards .kg-panel:nth-child(2) .developer-table td:nth-child(3) {
  width: 48%;
}

.developer-code {
  display: flex;
  flex-direction: column;
  position: relative;
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
  overscroll-behavior: contain;
  color: #95c47a;
  font-size: 13px;
  line-height: 24px;
  white-space: pre;
}

.developer-code pre::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.scroll-on-demand {
  scrollbar-color: transparent transparent;
}

.scroll-on-demand::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.scroll-on-demand::-webkit-scrollbar-track {
  background: transparent;
}

.scroll-on-demand::-webkit-scrollbar-thumb {
  background: transparent;
}

.scroll-on-demand::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}

.scroll-on-demand:hover,
.scroll-on-demand:focus-within {
  scrollbar-color: rgba(102, 110, 139, 0.36) transparent;
}

.scroll-on-demand:hover::-webkit-scrollbar-thumb,
.scroll-on-demand:focus-within::-webkit-scrollbar-thumb {
  background: rgba(102, 110, 139, 0.34);
}

.profile-card-like-tabs {
  display: inline-flex;
  padding: 2px;
  background: var(--surface-subtle);
}

.profile-card-like-tabs button {
  height: 28px;
  padding: 0 var(--space-12);
  border: 0;
  background: transparent;
  color: var(--text-secondary);
}

.profile-card-like-tabs .is-active {
  color: var(--primary);
  background: var(--surface);
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
  width: 780px;
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
  color: var(--text-primary);
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
  line-height: 20px;
}

.modal__required span {
  color: var(--danger);
}

.modal__body {
  padding: var(--space-16);
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
  font-weight: 400;
}

.config-form label > span i {
  width: 10px;
  font-style: normal;
  color: var(--danger);
}

.config-form input::placeholder {
  color: #86909c;
  opacity: 1;
}

.config-form select:invalid,
.config-form input {
  font-weight: 400;
}

.config-form input,
.config-form select {
  color: #86909c;
  font-weight: 400;
}

.config-form input::placeholder {
  color: #86909c;
  opacity: 1;
}

.config-form option {
  color: #86909c;
}

.config-form .select-icon {
  right: 10px;
}

.calendar-icon {
  top: 9px;
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
  margin: 0 0 var(--space-20);
  padding: var(--space-16);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  background: var(--surface-subtle);
  line-height: 24px;
}

.flow-steps {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-16);
}

.flow-step {
  min-height: 136px;
  padding: var(--space-16);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  text-align: center;
}

.flow-step__icon {
  display: block;
  width: 38px;
  height: 38px;
  margin: 0 auto var(--space-12);
  object-fit: contain;
}

.flow-step__arrow {
  position: absolute;
  top: 67px;
  width: 14px;
  height: 9px;
  object-fit: contain;
  opacity: 0.86;
}

.flow-step__arrow--one {
  left: calc(25% - 15px);
}

.flow-step__arrow--two {
  left: calc(50% - 7px);
}

.flow-step__arrow--three {
  left: calc(75% + 1px);
}

.flow-steps strong,
.flow-steps span {
  display: block;
}

.flow-steps strong {
  margin-bottom: var(--space-12);
}

.flow-steps span {
  color: var(--text-secondary);
  line-height: 22px;
}


.graph-panel__state {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  border: 1px dashed rgba(22, 93, 255, 0.16);
  color: var(--text-secondary);
  text-align: center;
}

.graph-panel__state--loading {
  color: var(--primary);
}

.graph-panel__state--error {
  color: var(--danger);
}

</style>
