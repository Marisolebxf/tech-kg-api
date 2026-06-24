<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  analyzeEnterpriseBackground,
  annotateRelationDetail,
  buildExpertEnterpriseRelation,
  fetchKgOptions,
} from '../../api/enterprise-relation'
import { getModuleByCode } from '../../config/kg-modules'
import { useAdaptiveGraphViewport } from '../../composables/useAdaptiveGraphViewport'
import { useGraphNodeInteraction } from '../../composables/useGraphNodeInteraction'
import { buildCodeExamples } from '../../composables/useDeveloperExamples'
import { useModuleTest } from '../../composables/useModuleTest'
import HighlightedCodeBlock from '../../components/kg/HighlightedCodeBlock.vue'
import HighlightedJsonPanel from '../../components/kg/HighlightedJsonPanel.vue'
import KgConstructionLayout from '../../layouts/KgConstructionLayout.vue'
import { edgePathPercent } from '../../utils/graph-edges'
import { buildRadialStarLayout } from '../../utils/graph-layout'

const boardRef = ref<HTMLElement | null>(null)

const moduleConfig = getModuleByCode('expert-enterprise-relation')!
const subfunctionOptions = moduleConfig.subFunctions

type SubFunction = (typeof subfunctionOptions)[number]

interface GraphNode {
  key: string
  title: string
  subtitle: string
  relation?: string
  x: number
  y: number
  width: number
  height: number
  kind: 'expert' | 'company'
}

const adaptiveViewport = useAdaptiveGraphViewport()
const { boardStyle, scaleWrapStyle, setCanvasSize } = adaptiveViewport

const activePage = ref<'test' | 'developer'>('test')
const activeTab = ref<'structured' | 'api'>('structured')
const showParamModal = ref(false)
const showSchemeModal = ref(false)
const testSubfunctionOpen = ref(false)
const developerSubfunctionOpen = ref(false)
const developerCodeTab = ref<'python' | 'node' | 'curl'>('python')
const copiedCodeTab = ref('')

const selectedSubfunction = ref<SubFunction>(subfunctionOptions[0])
const graphNodes = ref<GraphNode[]>([])
const buildResult = ref<Record<string, unknown> | null>(null)
const annotationResp = ref<Record<string, unknown> | null>(null)
const analysisResp = ref<Record<string, unknown> | null>(null)

const params = ref({
  scholarId: 'E10001',
  enterpriseId: 'ENT001',
  relationTypes: ['employment'] as string[],
})

const annotationParams = ref({
  relationId: 'E10001->ENT001@0',
  roleType: 'chief_scientist',
  techField: '人工智能',
  period: { start: '2021-01-01', end: '2024-12-31' },
})

const analysisParams = ref({
  enterpriseId: 'ENT001',
  analysisDimensions: ['industry_status', 'core_tech', 'financial'] as string[],
  patentCPC: ['G06N', 'G06F'] as string[],
})

const relationTypeOptions = [
  { value: 'employment', label: '任职' },
  { value: 'advisor', label: '顾问' },
  { value: 'rd_cooperation', label: '研发合作' },
  { value: 'project_cooperation', label: '项目合作' },
  { value: 'tech_cooperation', label: '技术合作' },
]

const roleOptions = [
  { value: 'chief_scientist', label: '首席科学家' },
  { value: 'cto', label: '技术总监' },
  { value: 'technical_advisor', label: '技术顾问' },
]

const dimensionOptions = [
  { value: 'industry_status', label: '行业地位' },
  { value: 'core_tech', label: '核心技术' },
  { value: 'financial', label: '经营财务' },
]

const optionsData = ref({
  scholars: [] as { scholarId: string; name: string }[],
  enterprises: [] as { enterpriseId: string; name: string }[],
  relationTypes: [] as { value: string; label: string }[],
  roles: [] as { value: string; label: string }[],
  dimensions: [] as { value: string; label: string }[],
  techFields: [] as string[],
  cpcCodes: [] as string[],
})

const { loading, error, lastTestTime, runWithLoading } = useModuleTest()

const subFunctionKey = computed(() => {
  if (selectedSubfunction.value === '角色与合作详情标注') return 'annotate'
  if (selectedSubfunction.value === '企业背景关联分析') return 'analyze'
  return 'build'
})

const currentApiPath = computed(() => {
  if (subFunctionKey.value === 'annotate') return '/api/v1/kg-construction/relation-detail-annotations/annotate'
  if (subFunctionKey.value === 'analyze') return '/api/v1/kg-construction/enterprise-background-analyses/analyze'
  return '/api/v1/kg-construction/expert-enterprise-relations/build'
})

const detailRows = computed<(string | number)[][]>(() => {
  if (subFunctionKey.value === 'annotate' && annotationResp.value) {
    const resp = annotationResp.value
    return [
      ['关系ID', String(resp.relationId ?? annotationParams.value.relationId)],
      ['角色', String(resp.roleLabel ?? '-')],
      ['角色等级', String(resp.roleLevel ?? '-')],
      ['技术领域', String(resp.techField ?? annotationParams.value.techField)],
      ['标注结果', resp.annotated ? '成功' : '失败'],
    ]
  }
  if (subFunctionKey.value === 'analyze' && analysisResp.value) {
    const resp = analysisResp.value
    return [
      ['企业名称', String(resp.enterpriseName ?? '-')],
      ['核心技术布局', String(resp.coreTechLayout ?? '-')],
    ]
  }
  if (!buildResult.value) return []
  const data = buildResult.value
  const rows: (string | number)[][] = [
    ['专家', String(data.scholarName ?? params.value.scholarId)],
    ['关系ID', String(data.builtRelationId ?? '-')],
  ]
  const relations = Array.isArray(data.relations) ? data.relations : []
  relations.forEach((relation: Record<string, unknown>, index: number) => {
    rows.push([`企业${index + 1}`, String(relation.enterpriseName ?? relation.enterpriseId ?? '-')])
    rows.push(['关系类型', String(relation.relationType ?? '-')])
  })
  return rows
})

const apiExample = computed(() => {
  if (subFunctionKey.value === 'annotate') return annotationResp.value
  if (subFunctionKey.value === 'analyze') return analysisResp.value
  return buildResult.value
})

const developerCodeLines = computed(() => {
  let payload: Record<string, unknown> = params.value as Record<string, unknown>
  if (subFunctionKey.value === 'annotate') payload = annotationParams.value as Record<string, unknown>
  if (subFunctionKey.value === 'analyze') payload = analysisParams.value as Record<string, unknown>
  const examples = buildCodeExamples(currentApiPath.value, 'POST', payload)
  const text =
    developerCodeTab.value === 'python'
      ? examples.python
      : developerCodeTab.value === 'node'
        ? examples.node
        : examples.curl
  return text.split('\n')
})

const graphDimensions = ref({ width: 720, height: 480 })

const graphInteraction = useGraphNodeInteraction({
  coordMode: 'pixel',
  getBoardElement: () => boardRef.value,
  getCanvasSize: () => graphDimensions.value,
  getScale: () => adaptiveViewport.scale.value,
  getNodeSize: (id) => {
    const node = graphNodes.value.find((item) => item.key === id)
    return { w: node?.width ?? 240, h: node?.height ?? 80 }
  },
  onNodeMove: (id, x, y) => {
    const index = graphNodes.value.findIndex((item) => item.key === id)
    if (index < 0) return
    const next = [...graphNodes.value]
    next[index] = { ...next[index], x, y }
    graphNodes.value = next
  },
})

function buildRadialGraph(centerTitle: string, items: { title: string; subtitle: string; relation: string }[]) {
  graphInteraction.clearFocus()
  const layout = buildRadialStarLayout<GraphNode>({
    center: {
      key: 'expert',
      title: centerTitle,
      subtitle: '专家',
      kind: 'expert',
      x: 0,
      y: 0,
      width: 220,
      height: 72,
    },
    satellites: items.map((item, index) => ({
      key: `company${index + 1}`,
      title: item.title,
      subtitle: item.subtitle,
      relation: item.relation,
      kind: 'company',
      x: 0,
      y: 0,
      width: 260,
      height: 88,
    })),
    gap: 24,
    padding: 28,
    fixedCenter: true,
  })
  graphNodes.value = layout.nodes
  graphDimensions.value = { width: layout.width, height: layout.height }
  setCanvasSize(layout.width, layout.height)
}

function graphNodeStyle(node: GraphNode) {
  const { width, height } = graphDimensions.value
  return {
    left: `${(node.x / width) * 100}%`,
    top: `${(node.y / height) * 100}%`,
    width: `${(node.width / width) * 100}%`,
    minHeight: `${(node.height / height) * 100}%`,
  }
}

function edgePath(from: GraphNode, to: GraphNode) {
  const { width, height } = graphDimensions.value
  return edgePathPercent(from, to, width, height)
}

const centerNode = computed(() => graphNodes.value.find((node) => node.kind === 'expert'))
const companyNodes = computed(() => graphNodes.value.filter((node) => node.kind === 'company'))

async function dispatchLoader() {
  if (subFunctionKey.value === 'annotate') {
    await runWithLoading(async () => {
      const data = await annotateRelationDetail(annotationParams.value)
      annotationResp.value = data
      const parts = String(annotationParams.value.relationId).split('->')
      buildRadialGraph(`专家：${parts[0] ?? ''}`, [
        {
          title: `企业：${(parts[1] ?? '').split('@')[0] ?? ''}`,
          subtitle: String(data.techField ?? '企业'),
          relation: String(data.roleLabel ?? data.roleType ?? '标注'),
        },
      ])
    })
    return
  }

  if (subFunctionKey.value === 'analyze') {
    await runWithLoading(async () => {
      const data = await analyzeEnterpriseBackground(analysisParams.value)
      analysisResp.value = data
      const dimLabel: Record<string, string> = {
        industry_status: '行业地位',
        core_tech: '核心技术',
        financial: '经营财务',
      }
      const items = analysisParams.value.analysisDimensions.map((dimension) => {
        const detail = (data.dimensions as Record<string, Record<string, unknown>>)?.[dimension] ?? {}
        return {
          title: dimLabel[dimension] ?? dimension,
          subtitle: detail.available ? String(detail.conclusion ?? '已分析') : String(detail.summary ?? '暂无数据'),
          relation: detail.available ? '已分析' : '暂无数据',
        }
      })
      buildRadialGraph(`企业：${data.enterpriseName ?? analysisParams.value.enterpriseId}`, items)
    })
    return
  }

  await runWithLoading(async () => {
    const data = await buildExpertEnterpriseRelation({
      scholarId: params.value.scholarId,
      enterpriseId: params.value.enterpriseId,
      relationTypes: params.value.relationTypes,
    })
    buildResult.value = data
    const relations = Array.isArray(data.relations) ? data.relations : []
    buildRadialGraph(
      `专家：${data.scholarName ?? params.value.scholarId}`,
      relations.map((relation: Record<string, unknown>) => ({
        title: `企业：${relation.enterpriseName ?? relation.enterpriseId}`,
        subtitle: '企业',
        relation: String(relation.relationType ?? '-'),
      })),
    )
  })
}

function selectSubfunction(option: SubFunction) {
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

function copyDeveloperCode() {
  void navigator.clipboard.writeText(developerCodeLines.value.join('\n'))
  copiedCodeTab.value = developerCodeTab.value
  setTimeout(() => {
    copiedCodeTab.value = ''
  }, 1500)
}

onMounted(async () => {
  document.addEventListener('click', closeSubfunctionDropdowns)
  const options = await fetchKgOptions()
  if (options) {
    optionsData.value = {
      scholars: options.scholars ?? [],
      enterprises: options.enterprises ?? [],
      relationTypes: options.relationTypes ?? [],
      roles: options.roles ?? [],
      dimensions: options.dimensions ?? [],
      techFields: options.techFields ?? [],
      cpcCodes: options.cpcCodes ?? [],
    }
  }
  void dispatchLoader()
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
          <button class="outline-btn" type="button" @click="showParamModal = true">参数设置</button>
          <button class="primary-btn" type="button" @click="dispatchLoader">{{ loading ? '测试中' : '执行测试' }}</button>
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
                <svg v-if="centerNode && companyNodes.length" class="graph-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  <path
                    v-for="node in companyNodes"
                    :key="node.key"
                    class="line blue"
                    :d="edgePath(centerNode!, node)"
                  />
                </svg>
                <article
                  v-for="node in graphNodes"
                  :key="node.key"
                  class="node expert-card kg-binding-node"
                  :class="[
                    { 'kg-company-node': node.kind === 'company' },
                    graphInteraction.nodeClasses(node.key),
                  ]"
                  :style="graphNodeStyle(node)"
                  @mousedown="graphInteraction.startNodeDrag(node.key, $event, node.x, node.y)"
                  @click="graphInteraction.handleNodeClick(node.key)"
                >
                  <div class="expert-card-body">
                    <span class="badge-circle badge-expert" aria-hidden="true"></span>
                    <div class="expert-card-copy">
                      <strong>{{ node.title }}</strong>
                      <small>{{ node.subtitle }}</small>
                      <small v-if="node.relation">关系：{{ node.relation }}</small>
                    </div>
                  </div>
                </article>
              </div>
              </div>
            </div>
          </div>

          <div class="detail-column">
            <div v-if="activeTab === 'structured'" class="detail-table">
              <div v-if="!detailRows.length && !error" class="table-row">
                <span>提示</span>
                <strong>执行测试后展示结构化结果</strong>
              </div>
              <div v-for="row in detailRows" :key="String(row[0])" class="table-row">
                <span>{{ row[0] }}</span>
                <strong>{{ row[1] }}</strong>
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
            <div class="developer-meta-box">{{ currentApiPath }}</div>
          </div>
          <div class="developer-method"><span>请求方法：</span><strong>POST</strong></div>
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

    <div v-if="showParamModal" class="modal-mask" @click.self="showParamModal = false">
      <section class="param-modal">
        <header class="param-modal-header">
          <div class="param-modal-title-wrap">
            <span class="param-modal-icon">✻</span>
            <h3>测试参数设置</h3>
          </div>
          <button class="param-close" type="button" @click="showParamModal = false">×</button>
        </header>
        <div class="param-form">
          <template v-if="subFunctionKey === 'build'">
            <label class="param-row">
              <span class="param-label required">scholarId</span>
              <input v-model="params.scholarId" class="param-field" type="text" />
            </label>
            <label class="param-row">
              <span class="param-label required">enterpriseId</span>
              <input v-model="params.enterpriseId" class="param-field" type="text" />
            </label>
            <label class="param-row">
              <span class="param-label">relationTypes</span>
              <select v-model="params.relationTypes[0]" class="param-field param-select">
                <option
                  v-for="option in (optionsData.relationTypes.length ? optionsData.relationTypes : relationTypeOptions)"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </label>
          </template>
          <template v-else-if="subFunctionKey === 'annotate'">
            <label class="param-row">
              <span class="param-label required">relationId</span>
              <input v-model="annotationParams.relationId" class="param-field" type="text" />
            </label>
            <label class="param-row">
              <span class="param-label">roleType</span>
              <select v-model="annotationParams.roleType" class="param-field param-select">
                <option v-for="option in (optionsData.roles.length ? optionsData.roles : roleOptions)" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="param-row">
              <span class="param-label">techField</span>
              <input v-model="annotationParams.techField" class="param-field" type="text" />
            </label>
          </template>
          <template v-else>
            <label class="param-row">
              <span class="param-label required">enterpriseId</span>
              <input v-model="analysisParams.enterpriseId" class="param-field" type="text" />
            </label>
            <label class="param-row">
              <span class="param-label">analysisDimensions</span>
              <select v-model="analysisParams.analysisDimensions[0]" class="param-field param-select">
                <option
                  v-for="option in (optionsData.dimensions.length ? optionsData.dimensions : dimensionOptions)"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </label>
          </template>
        </div>
        <footer class="param-modal-footer">
          <button class="param-cancel" type="button" @click="showParamModal = false">取消</button>
          <button class="param-save" type="button" @click="showParamModal = false; dispatchLoader()">保存并执行</button>
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
