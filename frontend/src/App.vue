<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ApiReferencePanel from './components/ApiReferencePanel.vue'
import RelationDetailPanel from './components/RelationDetailPanel.vue'
import RelationGraph from './components/RelationGraph.vue'
import ScenarioList from './components/ScenarioList.vue'
import SidebarNav from './components/SidebarNav.vue'
import {
  apiRequestRows,
  apiResponseRows,
  fallbackRelationPreview,
  relationModes,
  sidebarItems,
} from './data/directRelation'
import type { RelationModeOption, RelationPreviewResponse, RelationScenario } from './types/directRelation'

const activeModeKey = ref<RelationModeOption['key']>('two_hop')
const selectedScenarioKey = ref('')
const activeTab = ref<'structured' | 'api'>('structured')
const codeLanguage = ref<'python' | 'node' | 'curl'>('python')
const scenarios = ref<RelationScenario[]>(fallbackRelationPreview)
const loading = ref(false)

const activeMode = computed(() => relationModes.find((item) => item.key === activeModeKey.value) || relationModes[0])
const selectedScenario = computed(() => scenarios.value.find((item) => item.key === selectedScenarioKey.value) || scenarios.value[0] || null)
const codeExample = computed(() => buildCodeExample(activeMode.value, codeLanguage.value, selectedScenario.value))

function normalizeResponse(payload: RelationPreviewResponse | null): RelationScenario[] {
  const items = payload?.scenarios ?? []
  return items.length > 0 ? items : fallbackRelationPreview
}

async function loadPreview(mode: RelationModeOption['key']) {
  loading.value = true
  try {
    const modeConfig = relationModes.find((item) => item.key === mode) || relationModes[0]
    const response = await fetch(`${modeConfig.path}?dataSource=all`, {
      headers: {
        Accept: 'application/json',
      },
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = (await response.json()) as RelationPreviewResponse
    scenarios.value = normalizeResponse(payload)
  } catch {
    scenarios.value = fallbackRelationPreview
  } finally {
    loading.value = false
    selectedScenarioKey.value = scenarios.value[0]?.key ?? ''
  }
}

function onModeChange(nextMode: RelationModeOption['key']) {
  if (nextMode === activeModeKey.value) {
    return
  }
  activeModeKey.value = nextMode
}

function onScenarioSelect(key: string) {
  selectedScenarioKey.value = key
}

function onTabChange(tab: 'structured' | 'api') {
  activeTab.value = tab
}

function onCodeChange(language: 'python' | 'node' | 'curl') {
  codeLanguage.value = language
}

watch(activeModeKey, (mode) => {
  void loadPreview(mode)
})

onMounted(() => {
  void loadPreview(activeModeKey.value)
})

function buildCodeExample(
  mode: RelationModeOption,
  language: 'python' | 'node' | 'curl',
  scenario: RelationScenario | null,
) {
  const requestExample = scenario?.api_example?.request_example ?? {
    dataSource: 'all',
    expertAId: scenario?.api_example?.expert_a.name ?? '张明远',
    expertBId: scenario?.api_example?.expert_b.name ?? '李佳宁',
    institution: scenario?.api_example?.institution ?? '中国科学院自动化研究所',
    relationType: mode.key,
    startTime: '2026-01-01',
    endTime: '2026-12-31',
  }

  const requestEntries = Object.entries(requestExample)
  const url = `${window.location.origin}${mode.path}`

  if (language === 'node') {
    return `const params = new URLSearchParams(${JSON.stringify(Object.fromEntries(requestEntries), null, 2)});

fetch('${url}?' + params)
  .then((response) => response.json())
  .then((data) => console.log(data));`
  }

  if (language === 'curl') {
    const curlParams = requestEntries.map(([key, value]) => `  --data-urlencode '${key}=${String(value)}'`).join(' \\\n')
    return `curl -G '${url}' \\\n${curlParams}`
  }

  const pythonParams = `{\n${requestEntries
    .map(([key, value]) => `    "${key}": ${JSON.stringify(value)},`)
    .join('\n')}\n}`
  return `import requests

url = "${url}"
params = ${pythonParams}
response = requests.get(url, params=params, timeout=10)
print(response.json())`
}
</script>

<template>
  <div class="app-shell">
    <div class="layout">
      <SidebarNav :items="sidebarItems" />

      <main class="content">
        <section class="header-card">
          <div class="tabs-row">
            <button class="top-tab active" type="button">算法测试</button>
            <button class="top-tab" type="button">开发者接口</button>
          </div>

          <div class="toolbar">
            <div class="toolbar-group">
              <span class="toolbar-label">子功能名称：</span>
              <select class="mode-select" :value="activeModeKey" @change="onModeChange(($event.target as HTMLSelectElement).value as RelationModeOption['key'])">
                <option v-for="mode in relationModes" :key="mode.key" :value="mode.key">{{ mode.label }}</option>
              </select>
              <span class="mode-hint">当前展示为正式交付配置</span>
            </div>
            <div class="toolbar-actions">
              <button class="ghost-btn" type="button">技术方案</button>
              <button class="ghost-btn" type="button">参数设置</button>
              <button class="primary-btn" type="button">执行测试</button>
            </div>
          </div>
        </section>

        <section class="workspace">
          <div class="graph-column">
            <div class="panel panel--graph">
              <div class="panel-header">
                <div>
                  <h2>测试结果预览</h2>
                  <p>{{ loading ? '正在加载真实接口结果...' : '来自后端真实接口的结构化展示' }}</p>
                </div>
                <div class="panel-badge">最近测试时间：{{ selectedScenario?.last_test_time || '—' }}</div>
              </div>
              <RelationGraph v-if="selectedScenario" :graph="selectedScenario.graph" />
            </div>
          </div>

          <div class="detail-column">
            <ScenarioList
              :scenarios="scenarios"
              :selected-key="selectedScenario?.key || ''"
              @select="onScenarioSelect"
            />
            <RelationDetailPanel
              :scenario="selectedScenario"
              :active-tab="activeTab"
              @tab-change="onTabChange"
            />
          </div>
        </section>

        <ApiReferencePanel
          :mode="activeMode"
          :code-language="codeLanguage"
          :code-example="codeExample"
          :request-rows="apiRequestRows"
          :response-rows="apiResponseRows"
          @code-change="onCodeChange"
        />
      </main>
    </div>
  </div>
</template>
