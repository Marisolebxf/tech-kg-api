<script setup lang="ts">
import { ref } from 'vue'

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
import { inferenceResult } from './mock'

const activeView = ref<'test' | 'developer'>('test')
const resultMode = ref<'structured' | 'api'>('structured')
const activeCode = ref<'python' | 'node' | 'curl'>('python')
const result = ref({ ...inferenceResult })
const running = ref(false)
const copied = ref(false)
const showConfigModal = ref(false)
const showTechModal = ref(false)

type GraphNodeKind = 'expert' | 'organization' | 'field' | 'period' | 'achievement' | 'count'

interface GraphNode {
  id: string
  kind: GraphNodeKind
  variant?: 'blue' | 'green' | 'purple' | 'gold' | 'orange'
  x: number
  y: number
  width: number
  height: number
  title?: string
  subtitle?: string
  items?: string[]
  value?: number
}

interface GraphEdge {
  id: string
  source: string
  target: string
  relation: string
  path: string
  labelX: number
  labelY: number
  marker: 'blue' | 'purple' | 'green' | 'orange'
  dashed?: boolean
  labelVariant?: 'blue' | 'purple' | 'green' | 'orange'
}

const graphNodes: GraphNode[] = [
  {
    id: 'expert-a',
    kind: 'expert',
    variant: 'blue',
    x: 40,
    y: 30,
    width: 160,
    height: 62,
    title: '专家A：张明远',
    subtitle: '研究员',
  },
  {
    id: 'expert-b',
    kind: 'expert',
    variant: 'green',
    x: 468,
    y: 30,
    width: 160,
    height: 62,
    title: '专家B：李佳宁',
    subtitle: '副研究员',
  },
  {
    id: 'org-casia',
    kind: 'organization',
    variant: 'purple',
    x: 235,
    y: 210,
    width: 210,
    height: 62,
    title: '共同机构：',
    subtitle: '中国科学院自动化研究所',
  },
  {
    id: 'research-direction',
    kind: 'field',
    variant: 'green',
    x: 16,
    y: 325,
    width: 122,
    height: 102,
    title: '研究方向',
    items: ['知识图谱', '机器学习'],
  },
  {
    id: 'overlap-period',
    kind: 'period',
    variant: 'gold',
    x: 260,
    y: 370,
    width: 150,
    height: 58,
    title: '共事时段：',
    subtitle: '2018.03 - 2022.12',
  },
  {
    id: 'achievements',
    kind: 'achievement',
    variant: 'orange',
    x: 500,
    y: 325,
    width: 150,
    height: 88,
    title: '协作成果',
    items: ['论文', '专利', '项目'],
  },
  { id: 'paper-count', kind: 'count', variant: 'blue', x: 486, y: 470, width: 34, height: 34, value: 4 },
  { id: 'patent-count', kind: 'count', variant: 'green', x: 558, y: 470, width: 34, height: 34, value: 2 },
  { id: 'project-count', kind: 'count', variant: 'orange', x: 626, y: 470, width: 34, height: 34, value: 2 },
]

const graphEdges: GraphEdge[] = [
  {
    id: 'colleague',
    source: 'expert-a',
    target: 'expert-b',
    relation: '同事关系',
    path: 'M185 62 H468',
    labelX: 326,
    labelY: 48,
    marker: 'purple',
    labelVariant: 'purple',
  },
  {
    id: 'employment-a',
    source: 'expert-a',
    target: 'org-casia',
    relation: '任职',
    path: 'M155 92 C170 142, 224 178, 302 210',
    labelX: 195,
    labelY: 142,
    marker: 'blue',
    labelVariant: 'blue',
  },
  {
    id: 'employment-b',
    source: 'expert-b',
    target: 'org-casia',
    relation: '任职',
    path: 'M514 92 C500 142, 428 178, 372 210',
    labelX: 428,
    labelY: 142,
    marker: 'blue',
    labelVariant: 'blue',
  },
  {
    id: 'research',
    source: 'org-casia',
    target: 'research-direction',
    relation: '研究方向',
    path: 'M235 272 C155 272, 95 290, 72 325',
    labelX: 80,
    labelY: 268,
    marker: 'green',
    labelVariant: 'green',
  },
  {
    id: 'period',
    source: 'org-casia',
    target: 'overlap-period',
    relation: '共事时段',
    path: 'M340 272 V350',
    labelX: 360,
    labelY: 318,
    marker: 'blue',
    dashed: true,
  },
  {
    id: 'achievement',
    source: 'org-casia',
    target: 'achievements',
    relation: '协作成果',
    path: 'M445 272 C504 278, 538 300, 574 325',
    labelX: 540,
    labelY: 272,
    marker: 'orange',
    labelVariant: 'orange',
  },
  {
    id: 'paper-participation',
    source: 'achievements',
    target: 'paper-count',
    relation: '参与',
    path: 'M528 410 C520 430, 508 448, 503 470',
    labelX: 488,
    labelY: 448,
    marker: 'orange',
    dashed: true,
  },
  {
    id: 'patent-participation',
    source: 'achievements',
    target: 'patent-count',
    relation: '参与',
    path: 'M576 410 V470',
    labelX: 586,
    labelY: 448,
    marker: 'orange',
    dashed: true,
  },
  {
    id: 'project-participation',
    source: 'achievements',
    target: 'project-count',
    relation: '参与',
    path: 'M624 410 C632 430, 642 448, 643 470',
    labelX: 636,
    labelY: 448,
    marker: 'orange',
    dashed: true,
  },
]

const codeSamples = {
  python: `import requests

url = "http://localhost:3001/api/v1/colleague/relation/infer"
payload = {
    "dataSource": "publications+cv",
    "expertAId": "E10001",
    "expertBId": "E10002",
    "relationType": "colleague",
    "startTime": "2018.03",
    "endTime": "2022.12",
    "organizationId": "ORG-CASIA-001",
    "overlapThreshold": 12,
    "includeAchievements": True,
    "includeEvidence": True,
    "limit": 20,
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers, timeout=15)
response.raise_for_status()
data = response.json()

print(data["relationType"])
print(data["organization"])
print(data["overlapPeriod"])`,
  node: `const url = "http://localhost:3001/api/v1/colleague/relation/infer";

const payload = {
  dataSource: "publications+cv",
  expertAId: "E10001",
  expertBId: "E10002",
  relationType: "colleague",
  startTime: "2018.03",
  endTime: "2022.12",
  organizationId: "ORG-CASIA-001",
  overlapThreshold: 12,
  includeAchievements: true,
  includeEvidence: true,
  limit: 20,
};

async function inferColleagueRelation() {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(\`Request failed: \${response.status}\`);
  }

  const data = await response.json();
  console.log(data.relationType, data.organization, data.overlapPeriod);
}

inferColleagueRelation().catch(console.error);`,
  curl: `curl -X POST "http://localhost:3001/api/v1/colleague/relation/infer" \\
  -H "Content-Type: application/json" \\
  -d '{
    "dataSource": "publications+cv",
    "expertAId": "E10001",
    "expertBId": "E10002",
    "relationType": "colleague",
    "startTime": "2018.03",
    "endTime": "2022.12",
    "organizationId": "ORG-CASIA-001",
    "overlapThreshold": 12,
    "includeAchievements": true,
    "includeEvidence": true,
    "limit": 20
  }'`,
}

function handleSearch() {
  running.value = true
  window.setTimeout(() => {
    result.value = {
      ...result.value,
      lastTestTime: new Date().toLocaleString('zh-CN', {
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
    }
    resultMode.value = 'structured'
    running.value = false
  }, 500)
}

async function handleCopyCode() {
  try {
    await navigator.clipboard?.writeText(codeSamples[activeCode.value])
  } catch {
    // Ignore clipboard permission failures; keep the visual feedback for the prototype.
  }
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1200)
}
</script>

<template>
  <div class="expert-colleague">
    <header class="expert-colleague__toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'test' }"
          type="button"
          @click="activeView = 'test'"
        >
          算法测试
        </button>
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'developer' }"
          type="button"
          @click="activeView = 'developer'"
        >
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
        <select class="select-with-icon">
          <option>{{ result.featureName }}</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
        <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
      </label>
      <div class="search-panel-inline__actions">
        <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = true">
          参数设置
        </button>
        <button class="kg-button" type="button" @click="handleSearch">
          {{ running ? '测试中...' : '执行测试' }}
        </button>
      </div>
    </section>

    <div v-if="activeView === 'test'" class="expert-colleague__main">
      <section class="kg-panel graph-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">测试结果预览</h2>
          <div class="graph-panel__time">
            <span>最近测试时间：</span>
            <strong>{{ result.lastTestTime }}</strong>
          </div>
        </div>
        <div class="graph-panel__canvas">
          <svg viewBox="0 0 660 520" role="img" aria-label="科技专家同事关系推理结果">
            <defs>
              <marker id="arrow-blue-page" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                <path d="M0,0 L8,4 L0,8 Z" fill="#4080ff" />
              </marker>
              <marker id="arrow-purple-page" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                <path d="M0,0 L8,4 L0,8 Z" fill="#722ed1" />
              </marker>
              <marker id="arrow-green-page" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                <path d="M0,0 L8,4 L0,8 Z" fill="#00b42a" />
              </marker>
              <marker id="arrow-orange-page" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
                <path d="M0,0 L8,4 L0,8 Z" fill="#ff7d00" />
              </marker>
            </defs>
            <g class="graph-edges">
              <template v-for="edge in graphEdges" :key="edge.id">
                <path
                  class="edge"
                  :class="[`edge--${edge.marker}`, { 'edge--dash': edge.dashed }]"
                  :d="edge.path"
                  :marker-end="`url(#arrow-${edge.marker}-page)`"
                />
                <text
                  class="edge-label"
                  :class="edge.labelVariant ? `edge-label--${edge.labelVariant}` : ''"
                  :x="edge.labelX"
                  :y="edge.labelY"
                >
                  {{ edge.relation }}
                </text>
              </template>
            </g>

            <g class="graph-nodes">
              <g
                v-for="node in graphNodes"
                :key="node.id"
                class="box"
                :class="[`box--${node.kind}`, node.variant ? `box--${node.variant}` : '']"
                :transform="`translate(${node.x} ${node.y})`"
              >
                <template v-if="node.kind === 'count'">
                  <rect :width="node.width" :height="node.height" rx="8" />
                  <text :x="node.width / 2" :y="node.height / 2 + 1">{{ node.value }}</text>
                </template>

                <template v-else-if="node.kind === 'field'">
                  <rect :width="node.width" :height="node.height" rx="6" />
                  <text :x="node.width / 2" y="26">{{ node.title }}</text>
                  <template v-for="(item, index) in node.items" :key="item">
                    <rect class="chip" :x="(node.width - 70) / 2" :y="42 + index * 30" width="70" height="26" rx="6" />
                    <text :x="node.width / 2" :y="60 + index * 30">{{ item }}</text>
                  </template>
                </template>

                <template v-else-if="node.kind === 'achievement'">
                  <rect :width="node.width" :height="node.height" rx="6" />
                  <text :x="node.width / 2" y="28">{{ node.title }}</text>
                  <template v-for="(item, index) in node.items" :key="item">
                    <rect class="result-chip" :x="18 + index * 42" y="46" width="36" height="34" rx="6" />
                    <text class="result-text" :x="36 + index * 42" y="68">{{ item }}</text>
                  </template>
                </template>

                <template v-else>
                  <rect :width="node.width" :height="node.height" rx="6" />
                  <text :x="node.width / 2" :y="node.kind === 'period' ? 24 : 27">{{ node.title }}</text>
                  <text :x="node.width / 2" :y="node.kind === 'period' ? 44 : 50">{{ node.subtitle }}</text>
                </template>
              </g>
            </g>
          </svg>
        </div>
      </section>

      <aside class="expert-colleague__side">
        <section class="kg-panel result-panel">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">结果详情</h2>
            <div class="result-panel__tabs">
              <button
                :class="{ 'is-active': resultMode === 'structured' }"
                type="button"
                @click="resultMode = 'structured'"
              >
                结构化结果
              </button>
              <button
                :class="{ 'is-active': resultMode === 'api' }"
                type="button"
                @click="resultMode = 'api'"
              >
                API结果示例
              </button>
            </div>
          </div>
          <dl v-if="resultMode === 'structured'" class="result-panel__table scroll-on-demand">
            <div><dt>专家 A</dt><dd>{{ result.expertA.name }}</dd></div>
            <div><dt>专家 A 职称</dt><dd>{{ result.expertA.title }}</dd></div>
            <div><dt>专家 B</dt><dd>{{ result.expertB.name }}</dd></div>
            <div><dt>专家 B 职称</dt><dd>{{ result.expertB.title }}</dd></div>
            <div><dt>关系类型</dt><dd>{{ result.relationType }}</dd></div>
            <div><dt>共同机构</dt><dd>{{ result.organization }}</dd></div>
            <div><dt>共同部门</dt><dd>模式识别国家重点实验室</dd></div>
            <div><dt>共事时段</dt><dd>{{ result.overlapPeriod }}</dd></div>
            <div><dt>关系强度</dt><dd>92</dd></div>
            <div><dt>置信等级</dt><dd>高置信同事</dd></div>
            <div><dt>研究方向</dt><dd>{{ result.researchDirections.join('、') }}</dd></div>
            <div><dt>数据来源</dt><dd>专家履历、论文成果、项目成员、机构任职</dd></div>
            <div><dt>命中规则</dt><dd>任职时间重叠 + 共同机构 + 成果协作</dd></div>
            <div><dt>证据数量</dt><dd>12 条</dd></div>
            <div><dt>更新时间</dt><dd>{{ result.lastTestTime }}</dd></div>
            <div>
              <dt>协作成果</dt>
              <dd>
                <span class="result-panel__tag">论文 {{ result.collaborations.paper }}</span>
                <span class="result-panel__tag">专利 {{ result.collaborations.patent }}</span>
                <span class="result-panel__tag">项目 {{ result.collaborations.project }}</span>
              </dd>
            </div>
          </dl>
          <pre v-else class="result-panel__code scroll-on-demand">{
  "from": "{{ result.expertA.name }}",
  "to": "{{ result.expertB.name }}",
  "relationType": "{{ result.relationType }}",
  "organization": "{{ result.organization }}",
  "department": "模式识别国家重点实验室",
  "period": {
    "start": "2018.03",
    "end": "2022.12"
  },
  "confidence": 92,
  "confidenceLevel": "高置信同事",
  "researchDirections": [
    "{{ result.researchDirections[0] }}",
    "{{ result.researchDirections[1] }}",
    "自然语言处理",
    "智能问答"
  ],
  "collaboration": {
    "paper": {{ result.collaborations.paper }},
    "patent": {{ result.collaborations.patent }},
    "project": {{ result.collaborations.project }},
    "samples": [
      {
        "type": "paper",
        "title": "面向科研知识组织的实体关系抽取方法",
        "year": "2020"
      },
      {
        "type": "project",
        "title": "科技知识图谱构建与智能推理平台",
        "year": "2021"
      },
      {
        "type": "patent",
        "title": "一种专家关系识别与证据聚合方法",
        "year": "2022"
      }
    ]
  },
  "evidenceList": [
    {
      "source": "expert_cv",
      "field": "employment",
      "matched": "2018.03-2022.12 中国科学院自动化研究所"
    },
    {
      "source": "publication",
      "field": "coauthor",
      "matched": "共同发表论文 4 篇"
    },
    {
      "source": "project",
      "field": "member",
      "matched": "共同参与项目 2 项"
    },
    {
      "source": "patent",
      "field": "inventor",
      "matched": "共同申请专利 2 件"
    }
  ],
  "rules": [
    "任职时间重叠超过 12 个月",
    "共同机构完全匹配",
    "存在论文 / 项目 / 专利协作证据",
    "研究方向相似度超过阈值"
  ],
  "updatedAt": "{{ result.lastTestTime }}",
  "status": "success"
}</pre>
        </section>
      </aside>
    </div>

    <section v-else class="developer-view">
      <div class="developer-view__meta">
        <label>
          <span>子功能名称：</span>
          <select class="select-with-icon">
            <option>{{ result.featureName }}</option>
          </select>
          <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
        </label>
        <label>
          <span>接口路径：</span>
          <input :value="result.endpoint" readonly />
        </label>
        <span>请求方法： {{ result.method }}</span>
      </div>
      <div class="developer-view__cards">
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
          <div class="developer-table-wrap scroll-on-demand">
            <table class="developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="param in result.requestParams" :key="param.field">
                  <td>{{ param.field }}</td>
                  <td>{{ param.type }}</td>
                  <td>{{ param.required }}</td>
                  <td>{{ param.description }}</td>
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
                <tr v-for="field in result.responseFields" :key="field.field">
                  <td>{{ field.field }}</td>
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
        <button
          class="developer-code__copy"
          :class="{ 'is-copied': copied }"
          type="button"
          :aria-label="copied ? '复制成功' : '复制代码'"
          @click="handleCopyCode"
        >
          <span v-if="copied" aria-hidden="true">✓</span>
          <img v-else :src="iconCopy" alt="" aria-hidden="true" />
        </button>
        <pre class="scroll-on-demand">{{ codeSamples[activeCode] }}</pre>
      </section>
    </section>

    <div v-if="showConfigModal || showTechModal" class="modal-mask" @click.self="showConfigModal = false; showTechModal = false">
      <section v-if="showConfigModal" class="modal modal--config" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2><img :src="iconModalSetting" alt="" aria-hidden="true" />测试参数设置</h2>
          <div class="modal__header-extra">
            <span class="modal__required"><span>*</span> 为必填项</span>
            <button type="button" @click="showConfigModal = false">
              <img :src="iconClose" alt="" aria-hidden="true" />
            </button>
          </div>
        </header>
        <div class="modal__body config-form">
          <label><span><i>*</i>dataSource</span><select><option>全部</option></select><img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" /></label>
          <label><span><i>*</i>expertAId</span><input placeholder="全部" /></label>
          <label><span><i>*</i>expertBId</span><input placeholder="全部" /></label>
          <label><span><i>*</i>relationType</span><select><option>同事关系</option></select><img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" /></label>
          <label><span><i></i>timeRange</span><input placeholder="开始时间        - 结束时间" /><img class="calendar-icon" :src="iconCalendar" alt="" aria-hidden="true" /></label>
        </div>
        <footer class="modal__footer">
          <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = false">取消</button>
          <button class="kg-button" type="button" @click="showConfigModal = false">保存并执行</button>
        </footer>
      </section>

      <section v-if="showTechModal" class="modal modal--tech" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2>技术方案</h2>
          <button type="button" @click="showTechModal = false">
            <img :src="iconClose" alt="" aria-hidden="true" />
          </button>
        </header>
        <div class="modal__body">
          <h3 class="modal__section-title">功能描述</h3>
          <p class="modal__desc">本模块基于专家任职履历、机构信息、部门与团队信息及成果数据，结合知识图谱中的组织与任命关系，识别并推断专家之间是否存在同事关系，并输出结构化结果。</p>
          <h3 class="modal__section-title">推理流程</h3>
          <div class="flow-steps">
            <div class="flow-step"><img class="flow-step__icon" :src="flowInput" alt="" aria-hidden="true" /><strong>输入数据</strong><span>接收专家ID及相关筛选参数</span></div>
            <img class="flow-step__arrow flow-step__arrow--one" :src="flowArrow" alt="" aria-hidden="true" />
            <div class="flow-step"><img class="flow-step__icon" :src="flowStandardize" alt="" aria-hidden="true" /><strong>标准化处理</strong><span>清洗并归一化参数</span></div>
            <img class="flow-step__arrow flow-step__arrow--two" :src="flowArrow" alt="" aria-hidden="true" />
            <div class="flow-step"><img class="flow-step__icon" :src="flowReasoning" alt="" aria-hidden="true" /><strong>关系推理</strong><span>基于时间重叠与团队归属规则</span></div>
            <img class="flow-step__arrow flow-step__arrow--three" :src="flowArrow" alt="" aria-hidden="true" />
            <div class="flow-step"><img class="flow-step__icon" :src="flowOutput" alt="" aria-hidden="true" /><strong>结果输出</strong><span>输出关系类型、时间区间等结构化结果</span></div>
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

.box--green rect {
  fill: #f5fff7;
  stroke: var(--graph-green);
}

.box--green text {
  fill: #237804;
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
  grid-template-columns: 120px minmax(0, 1fr);
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
}

.result-panel__table dt {
  justify-content: flex-end;
  border-right: 1px solid var(--border);
  color: var(--text-tertiary);
}

.result-panel__table dd {
  color: var(--text-primary);
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
</style>
