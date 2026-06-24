<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getModuleByCode } from '../../../config/kg-modules'
import { useGraphNodeInteraction } from '../../../composables/useGraphNodeInteraction'
import { useModuleTest } from '../../../composables/useModuleTest'
import HighlightedCodeBlock from '../../../components/kg/HighlightedCodeBlock.vue'
import HighlightedJsonPanel from '../../../components/kg/HighlightedJsonPanel.vue'
import KgConstructionLayout from '../../../layouts/KgConstructionLayout.vue'
import type { DemoGraphNode, ScaffoldDemoPayload } from '../../../types/kg-module'
import { separatePercentNodes } from '../../../utils/graph-layout'
import { getScaffoldDemo, structuredResultToRows } from './demo-data'

const props = defineProps<{ moduleCode: string }>()

const moduleConfig = computed(() => getModuleByCode(props.moduleCode))
const demo = ref<ScaffoldDemoPayload | null>(null)

const activePage = ref<'test' | 'developer'>('test')
const activeTab = ref<'structured' | 'api'>('structured')
const showSchemeModal = ref(false)
const testSubfunctionOpen = ref(false)
const developerSubfunctionOpen = ref(false)
const developerCodeTab = ref<'python' | 'node' | 'curl'>('python')
const copiedCodeTab = ref('')

const selectedSubfunction = ref('')
const layoutNodes = ref<DemoGraphNode[]>([])
const boardRef = ref<HTMLElement | null>(null)
const { loading, error, lastTestTime, runWithLoading } = useModuleTest()

const detailRows = computed(() => {
  if (!demo.value) return []
  return structuredResultToRows(demo.value.structuredResult as Record<string, unknown>)
})

const graphLayout = computed(() => demo.value?.graphLayout ?? null)

const fallbackGraphNodes = computed(() => {
  const label = moduleConfig.value?.navLabel ?? '节点'
  return [
    { id: 'a', kind: 'default', title: `${label} A`, subtitle: '核心节点', x: 8, y: 12, w: 32, h: 14 },
    { id: 'b', kind: 'default', title: `${label} B`, subtitle: '关联节点', x: 58, y: 12, w: 32, h: 14 },
    { id: 'c', kind: 'default', title: '关系摘要', subtitle: '示例关系', x: 28, y: 55, w: 40, h: 12 },
  ]
})

const displayNodes = computed(() => {
  if (layoutNodes.value.length) {
    return layoutNodes.value
  }
  if (graphLayout.value?.nodes?.length) {
    return graphLayout.value.nodes
  }
  return fallbackGraphNodes.value
})

const graphInteraction = useGraphNodeInteraction({
  coordMode: 'percent',
  getBoardElement: () => boardRef.value,
  getCanvasSize: () => ({ width: 100, height: 100 }),
  getNodeSize: (id) => {
    const node = displayNodes.value.find((item) => item.id === id)
    return { w: node?.w ?? 0, h: node?.h ?? 0 }
  },
  onNodeMove: (id, x, y) => {
    layoutNodes.value = displayNodes.value.map((node) =>
      node.id === id ? { ...node, x, y } : node,
    )
  },
})

const developerCodeLines = computed(() => {
  const examples = demo.value?.codeExamples
  if (!examples) return []
  const text = developerCodeTab.value === 'python' ? examples.python : developerCodeTab.value === 'node' ? examples.node : examples.curl
  return text.split('\n')
})

function nodeStyle(node: DemoGraphNode | { x: number; y: number; w: number; h: number }) {
  return {
    left: `${node.x}%`,
    top: `${node.y}%`,
    width: `${node.w}%`,
    minHeight: `${node.h}%`,
  }
}

function nodeClass(kind: string) {
  if (kind === 'expertA') return 'node-a expert-card'
  if (kind === 'expertB') return 'node-b expert-card'
  if (kind === 'institution') return 'paper-node'
  if (kind === 'department') return 'topic-node'
  if (kind === 'major') return 'contribution-node'
  if (kind === 'period') return 'period-node'
  if (kind === 'cooperation') return 'contribution-node'
  return 'expert-card kg-scaffold-node'
}

function selectSubfunction(option: string) {
  selectedSubfunction.value = option
  testSubfunctionOpen.value = false
  developerSubfunctionOpen.value = false
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

async function runTest() {
  await runWithLoading(async () => {
    await new Promise((resolve) => setTimeout(resolve, 400))
    if (!demo.value) throw new Error('示例数据未加载')
    graphInteraction.clearFocus()
    layoutNodes.value = displayNodes.value.map((node) => ({ ...node }))
  })
}

function copyDeveloperCode() {
  const text = developerCodeLines.value.join('\n')
  void navigator.clipboard.writeText(text)
  copiedCodeTab.value = developerCodeTab.value
  setTimeout(() => {
    copiedCodeTab.value = ''
  }, 1500)
}

function normalizeDemoGraphLayout(payload: ScaffoldDemoPayload) {
  if (!payload.graphLayout?.nodes?.length) {
    return payload
  }
  const nodes = payload.graphLayout.nodes.map((node) => ({
    key: node.id,
    x: node.x,
    y: node.y,
    w: node.w,
    h: node.h,
  }))
  separatePercentNodes(nodes)
  return {
    ...payload,
    graphLayout: {
      ...payload.graphLayout,
      nodes: payload.graphLayout.nodes.map((node, index) => ({
        ...node,
        x: nodes[index].x,
        y: nodes[index].y,
      })),
    },
  }
}

onMounted(() => {
  document.addEventListener('click', closeSubfunctionDropdowns)
  const payload = getScaffoldDemo(props.moduleCode)
  if (payload) {
    demo.value = normalizeDemoGraphLayout(payload)
    layoutNodes.value = demo.value.graphLayout?.nodes?.map((node) => ({ ...node })) ?? []
    selectedSubfunction.value = moduleConfig.value?.subFunctions[0] ?? ''
    lastTestTime.value = payload.lastTestTime
  }
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
              v-for="option in moduleConfig?.subFunctions ?? []"
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
          <button class="primary-btn" type="button" @click="runTest">{{ loading ? '测试中' : '执行测试' }}</button>
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
            <div class="graph-preview-viewport">
              <div ref="boardRef" class="graph-preview-board">
                <svg class="graph-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  <template v-if="graphLayout">
                    <path
                      v-for="(edge, index) in graphLayout.edges"
                      :key="index"
                      class="line"
                      :class="edge.className ?? 'blue'"
                      :d="edge.path"
                    />
                  </template>
                  <template v-else>
                    <path class="line purple" d="M 18 22 C 35 22, 35 58, 45 62" />
                    <path class="line blue" d="M 78 22 C 62 22, 62 58, 52 62" />
                  </template>
                </svg>
                <div
                  v-if="graphLayout?.relationPill"
                  class="relation-pill"
                  :style="{ left: `${graphLayout.relationPill.x}%`, top: `${graphLayout.relationPill.y}%` }"
                >
                  {{ graphLayout.relationPill.text }}
                </div>
                <article
                  v-for="node in displayNodes"
                  :key="node.id"
                  class="node"
                  :class="[nodeClass(node.kind), graphInteraction.nodeClasses(node.id)]"
                  :style="nodeStyle(node)"
                  @mousedown="graphInteraction.startNodeDrag(node.id, $event, node.x, node.y)"
                  @click="graphInteraction.handleNodeClick(node.id)"
                >
                  <span v-if="node.kind === 'expertA'" class="card-corner-label">专家A</span>
                  <span v-else-if="node.kind === 'expertB'" class="card-corner-label">专家B</span>
                  <div class="expert-card-body">
                    <div class="expert-card-copy">
                      <strong>{{ node.title }}</strong>
                      <small v-if="node.subtitle">{{ node.subtitle }}</small>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>

          <div class="detail-column">
            <div v-if="activeTab === 'structured'" class="detail-table">
              <div v-for="row in detailRows" :key="String(row[0])" class="table-row">
                <span>{{ row[0] }}</span>
                <strong>{{ row[1] }}</strong>
              </div>
            </div>
            <div v-else class="api-panel-shell">
              <HighlightedJsonPanel :value="demo?.apiExample ?? {}" />
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
                v-for="option in moduleConfig?.subFunctions ?? []"
                :key="`dev-${option}`"
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
            <div class="developer-meta-box">{{ demo?.apiPath }}</div>
          </div>
          <div class="developer-method"><span>请求方法：</span><strong>{{ demo?.httpMethod }}</strong></div>
        </div>
      </div>

      <div class="developer-panels">
        <section class="developer-card">
          <div class="developer-card-title">请求参数</div>
          <div class="developer-table-shell">
            <div class="developer-table developer-request-table">
              <div class="developer-table-head developer-table-row four-col">
                <span>字段名</span><span>类型</span><span>必填</span><span>说明</span>
              </div>
              <div v-for="field in demo?.requestFields ?? []" :key="field.name" class="developer-table-row four-col">
                <strong>{{ field.name }}</strong>
                <span>{{ field.type }}</span>
                <span>{{ field.required ?? '-' }}</span>
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
                <span>字段名</span><span>类型</span><span>说明</span>
              </div>
              <div v-for="field in demo?.responseFields ?? []" :key="field.name" class="developer-table-row three-col">
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

    <div v-if="showSchemeModal" class="modal-mask" @click.self="showSchemeModal = false">
      <section class="scheme-modal">
        <header class="scheme-modal-header">
          <h3>技术方案</h3>
          <button class="scheme-close" type="button" @click="showSchemeModal = false">×</button>
        </header>
        <div class="scheme-modal-body">
          <section class="scheme-section">
            <h4>功能描述</h4>
            <div class="scheme-description-card">{{ moduleConfig?.schemeDescription }}</div>
          </section>
          <section class="scheme-section">
            <h4>推理流程</h4>
            <div class="scheme-flow">
              <template v-for="(step, index) in moduleConfig?.schemeFlow ?? []" :key="step">
                <article class="scheme-step-card">
                  <div class="scheme-step-icon">{{ index + 1 }}</div>
                  <strong>{{ step }}</strong>
                </article>
                <span v-if="index < (moduleConfig?.schemeFlow.length ?? 0) - 1" class="scheme-arrow">→</span>
              </template>
            </div>
          </section>
        </div>
      </section>
    </div>
  </KgConstructionLayout>
</template>
