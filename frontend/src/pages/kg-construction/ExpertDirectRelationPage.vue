<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  fetchBindingScenarios,
  type BindingQueryParams,
  type BindingRelationType,
  type BindingScenario,
} from '../../api/binding'
import { getModuleByCode } from '../../config/kg-modules'
import { buildCodeExamples } from '../../composables/useDeveloperExamples'
import { useAdaptiveGraphViewport } from '../../composables/useAdaptiveGraphViewport'
import { useGraphNodeInteraction } from '../../composables/useGraphNodeInteraction'
import { useModuleTest } from '../../composables/useModuleTest'
import HighlightedCodeBlock from '../../components/kg/HighlightedCodeBlock.vue'
import HighlightedJsonPanel from '../../components/kg/HighlightedJsonPanel.vue'
import KgConstructionLayout from '../../layouts/KgConstructionLayout.vue'
import { edgePathFromRecord, refreshGraphEdges } from '../../utils/graph-edges'
import { normalizePixelGraph, type PixelGraph } from '../../utils/graph-layout'

const boardRef = ref<HTMLElement | null>(null)

type DataSource = 'all' | 'knowledge_graph' | 'cnki' | 'wanfang' | 'web_of_science'

const moduleConfig = getModuleByCode('expert-direct-relation')!

const subfunctionOptions = moduleConfig.subFunctions
const relationTypeMap: Record<(typeof subfunctionOptions)[number], BindingRelationType> = {
  科技专家直接关系构建: 'direct',
  两跳关系构建: 'two_hop',
  三跳关系构建: 'three_hop',
}

const dataSourceOptions: Array<{ label: string; value: DataSource }> = [
  { label: '全部', value: 'all' },
  { label: '知识图谱', value: 'knowledge_graph' },
  { label: '知网', value: 'cnki' },
  { label: '万方', value: 'wanfang' },
  { label: 'Web of Science', value: 'web_of_science' },
]

const defaultParams: BindingQueryParams = {
  dataSource: 'knowledge_graph',
  expertAId: '',
  expertBId: '',
  institution: '',
  relationType: 'direct',
  startTime: '',
  endTime: '',
}

const activePage = ref<'test' | 'developer'>('test')
const activeTab = ref<'structured' | 'api'>('structured')
const showParamModal = ref(false)
const showSchemeModal = ref(false)
const testSubfunctionOpen = ref(false)
const developerSubfunctionOpen = ref(false)
const developerCodeTab = ref<'python' | 'node' | 'curl'>('python')
const copiedCodeTab = ref('')

const selectedSubfunction = ref<(typeof subfunctionOptions)[number]>(subfunctionOptions[0])
const draftParams = ref({ ...defaultParams })
const scenario = ref<BindingScenario | null>(null)
const graphData = ref<PixelGraph | null>(null)
const detailRows = ref<(string | number)[][]>([])
const apiExample = ref<Record<string, unknown> | null>(null)

const adaptiveViewport = useAdaptiveGraphViewport()
const { boardStyle, scaleWrapStyle, setCanvasSize } = adaptiveViewport

const graphInteraction = useGraphNodeInteraction({
  coordMode: 'pixel',
  getBoardElement: () => boardRef.value,
  getCanvasSize: () => ({
    width: graphData.value?.width ?? 720,
    height: graphData.value?.height ?? 480,
  }),
  getScale: () => adaptiveViewport.scale.value,
  getNodeSize: (id) => {
    const node = graphData.value?.nodes.find((item) => item.id === id)
    return { w: node?.width ?? 240, h: node?.height ?? 80 }
  },
  onNodeMove: (id, x, y) => {
    if (!graphData.value) return
    const nodes = graphData.value.nodes.map((node) =>
      node.id === id ? { ...node, x, y } : node,
    )
    const edges = graphData.value.edges?.length
      ? refreshGraphEdges(nodes, graphData.value.edges)
      : graphData.value.edges
    graphData.value = { ...graphData.value, nodes, edges }
  },
})

const { loading, error, lastTestTime, runWithLoading } = useModuleTest()

const apiPath = computed(() => {
  const relationType = relationTypeMap[selectedSubfunction.value]
  if (relationType === 'two_hop') return '/api/v1/binding/expert-direct-two-hop'
  if (relationType === 'three_hop') return '/api/v1/binding/expert-direct-three-hop'
  return '/api/v1/binding/expert-direct-relation'
})

const developerCodeLines = computed(() => {
  const examples = buildCodeExamples(apiPath.value, 'GET', draftParams.value as Record<string, unknown>)
  const text =
    developerCodeTab.value === 'python'
      ? examples.python
      : developerCodeTab.value === 'node'
        ? examples.node
        : examples.curl
  return text.split('\n')
})

function graphNodeStyle(node: { x: number; y: number; width?: number; height?: number }) {
  const width = graphData.value?.width ?? 860
  const height = graphData.value?.height ?? 640
  return {
    left: `${(node.x / width) * 100}%`,
    top: `${(node.y / height) * 100}%`,
    width: `${((node.width ?? 280) / width) * 100}%`,
    minHeight: `${((node.height ?? 90) / height) * 100}%`,
  }
}

function edgePath(edge: Record<string, unknown>) {
  const width = graphData.value?.width ?? 860
  const height = graphData.value?.height ?? 640
  return edgePathFromRecord(edge as Parameters<typeof edgePathFromRecord>[0], width, height)
}

function applyScenario(nextScenario: BindingScenario & { graph?: PixelGraph; detail_rows?: (string | number)[][] }) {
  scenario.value = nextScenario
  graphInteraction.clearFocus()
  if (nextScenario.graph) {
    const normalized = normalizePixelGraph(nextScenario.graph)
    graphData.value = normalized
    setCanvasSize(normalized.width, normalized.height)
  } else {
    graphData.value = null
  }
  detailRows.value = nextScenario.detail_rows ?? []
  apiExample.value = (nextScenario.api_example as Record<string, unknown>) ?? null
}

async function runTest(params: BindingQueryParams = draftParams.value) {
  await runWithLoading(async () => {
    const relationType = relationTypeMap[selectedSubfunction.value]
    const response = await fetchBindingScenarios({ ...params, relationType })
    const first = response.scenarios?.[0]
    if (!first) throw new Error('未返回可用场景数据')
    applyScenario(first)
  })
}

function selectSubfunction(option: (typeof subfunctionOptions)[number]) {
  selectedSubfunction.value = option
  draftParams.value.relationType = relationTypeMap[option]
  testSubfunctionOpen.value = false
  developerSubfunctionOpen.value = false
  void runTest()
}

function toggleTestSubfunction() {
  testSubfunctionOpen.value = !testSubfunctionOpen.value
  developerSubfunctionOpen.value = false
}

function toggleDeveloperSubfunction() {
  developerSubfunctionOpen.value = !developerSubfunctionOpen.value
  testSubfunctionOpen.value = false
}

function closeSubfunctionDropdowns() {
  testSubfunctionOpen.value = false
  developerSubfunctionOpen.value = false
}

function openParamModal() {
  draftParams.value = { ...draftParams.value }
  showParamModal.value = true
}

function closeParamModal() {
  showParamModal.value = false
}

async function saveAndRun() {
  showParamModal.value = false
  await runTest(draftParams.value)
}

function copyDeveloperCode() {
  void navigator.clipboard.writeText(developerCodeLines.value.join('\n'))
  copiedCodeTab.value = developerCodeTab.value
  setTimeout(() => {
    copiedCodeTab.value = ''
  }, 1500)
}

onMounted(() => {
  document.addEventListener('click', closeSubfunctionDropdowns)
  void runTest()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeSubfunctionDropdowns)
})
</script>

<template>
  <KgConstructionLayout>
    <header class="top-tabs">
      <div class="tabs">
        <button class="tab" :class="{ active: activePage === 'test' }" type="button" @click="activePage = 'test'">算法测试</button>
        <button class="tab" :class="{ active: activePage === 'developer' }" type="button" @click="activePage = 'developer'">开发者接口</button>
      </div>
      <button class="scheme-btn" type="button" @click="showSchemeModal = true">ⓘ 技术方案</button>
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
              :key="option"
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
            <div
              class="graph-preview-viewport"
              :ref="(el) => { adaptiveViewport.viewportRef.value = el as HTMLElement | null }"
            >
              <div class="graph-board-scale-wrap" :style="scaleWrapStyle">
              <div ref="boardRef" class="graph-preview-board binding-graph-board" :style="boardStyle">
                <svg v-if="graphData" class="graph-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  <path
                    v-for="(edge, index) in graphData.edges"
                    :key="index"
                    class="line blue"
                    :d="edgePath(edge)"
                  />
                </svg>
                <article
                  v-for="node in graphData?.nodes ?? []"
                  :key="node.id"
                  class="node expert-card kg-binding-node"
                  :class="[
                    { 'institution-node': node.kind === 'institution' },
                    graphInteraction.nodeClasses(node.id),
                  ]"
                  :style="graphNodeStyle(node)"
                  @mousedown="graphInteraction.startNodeDrag(node.id, $event, node.x, node.y)"
                  @click="graphInteraction.handleNodeClick(node.id)"
                >
                  <span v-if="node.kind === 'expertA'" class="card-corner-label">专家A</span>
                  <span v-else-if="node.kind === 'expertB'" class="card-corner-label">专家B</span>
                  <div class="expert-card-body">
                    <span class="badge-circle badge-expert" aria-hidden="true"></span>
                    <div class="expert-card-copy">
                      <strong>{{ node.title }}</strong>
                      <small>{{ node.subtitle }}</small>
                      <small v-if="node.desc">{{ node.desc }}</small>
                    </div>
                  </div>
                </article>
              </div>
              </div>
            </div>
          </div>

          <div class="detail-column">
            <div v-if="activeTab === 'structured'" class="detail-table">
              <div v-for="row in detailRows" :key="String(row[0])" class="table-row">
                <span>{{ row[0] }}</span>
                <strong>{{ Array.isArray(row[1]) ? row[1].join('、') : row[1] }}</strong>
              </div>
            </div>
            <div v-else class="api-panel-shell">
              <HighlightedJsonPanel :value="apiExample" />
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
                :key="`dev-${option}`"
                class="select-dropdown-item"
                type="button"
                @click.stop="selectSubfunction(option)"
              >
                {{ option }}
              </button>
            </div>
          </div>
        </div>
        <div class="developer-toolbar-side">
          <div class="developer-meta-item">
            <span>接口路径：</span>
            <div class="developer-meta-box">{{ apiPath }}</div>
          </div>
          <div class="developer-method"><span>请求方法：</span><strong>GET</strong></div>
        </div>
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
            <HighlightedCodeBlock :lines="developerCodeLines" />
          </div>
          <div class="developer-code-footer">
            <button class="developer-copy-btn" type="button" @click="copyDeveloperCode">
              {{ copiedCodeTab === developerCodeTab ? '已复制' : '复制' }}
            </button>
          </div>
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
          <button class="param-close" type="button" @click="closeParamModal">×</button>
        </header>
        <div class="param-form">
          <label class="param-row">
            <span class="param-label">dataSource</span>
            <select v-model="draftParams.dataSource" class="param-field param-select">
              <option v-for="option in dataSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="param-row">
            <span class="param-label">expertAId</span>
            <input v-model="draftParams.expertAId" class="param-field" type="text" />
          </label>
          <label class="param-row">
            <span class="param-label">expertBId</span>
            <input v-model="draftParams.expertBId" class="param-field" type="text" />
          </label>
          <label class="param-row">
            <span class="param-label">institution</span>
            <input v-model="draftParams.institution" class="param-field" type="text" />
          </label>
          <label class="param-row">
            <span class="param-label">startTime</span>
            <input v-model="draftParams.startTime" class="param-field" type="text" placeholder="2021-01-01" />
          </label>
          <label class="param-row">
            <span class="param-label">endTime</span>
            <input v-model="draftParams.endTime" class="param-field" type="text" placeholder="2024-12-31" />
          </label>
        </div>
        <footer class="param-modal-footer">
          <button class="param-cancel" type="button" @click="closeParamModal">取消</button>
          <button class="param-save" type="button" @click="saveAndRun">保存并执行</button>
        </footer>
      </section>
    </div>

    <div v-if="showSchemeModal" class="modal-mask" @click.self="showSchemeModal = false">
      <section class="scheme-modal">
        <header class="scheme-modal-header">
          <h3>技术方案</h3>
          <button class="scheme-close" type="button" @click="showSchemeModal = false">×</button>
        </header>
        <div class="scheme-modal-body">
          <section class="scheme-section">
            <h4>功能描述</h4>
            <div class="scheme-description-card">{{ moduleConfig.schemeDescription }}</div>
          </section>
          <section class="scheme-section">
            <h4>推理流程</h4>
            <div class="scheme-flow">
              <template v-for="(step, index) in moduleConfig.schemeFlow" :key="step">
                <article class="scheme-step-card">
                  <div class="scheme-step-icon">{{ index + 1 }}</div>
                  <strong>{{ step }}</strong>
                </article>
                <span v-if="index < moduleConfig.schemeFlow.length - 1" class="scheme-arrow">→</span>
              </template>
            </div>
          </section>
        </div>
      </section>
    </div>
  </KgConstructionLayout>
</template>
