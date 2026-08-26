<script setup lang="ts">
import { ref, computed } from 'vue'

interface DemoCase {
  id: string
  label: string
  candidate: Record<string, unknown>
  sourceRecord: { table: string; recordId: string; fields: Array<{ key: string; value: string }> }
  extraction: {
    model: string
    llmInput: { systemPrompt: string; userMessage: string }
    llmOutput: string
  }
  confidence: number
  threshold: number
  trace: {
    workflowId: string
    workflowType: string
    executionId: string
    sourceTaskId: string
    pipelineStepId: string
  }
}

const SYSTEM_PROMPT = `你是一个知识图谱抽取助手。从源记录中抽取实体和关系，输出 JSON。
每个候选必须包含 confidence 字段（0-1），表示你对这次抽取的把握程度。
低于 0.85 的候选会进入人工审核队列，由人工决定是否写图。`

const demoCases: DemoCase[] = [
  {
    id: 'MR-20260825-5AEA2B6440A1',
    label: 'Paper 实体',
    candidate: {
      _kind: 'entity', _nodeLabel: 'Paper',
      id: 'P-2',
      title: '《多模态大模型知识推理方法研究》',
      authors: '张三, 李四, 王五',
      publish_year: 2026,
      doi: '10.2026/kg.104',
      confidence: 0.78,
    },
    sourceRecord: {
      table: 'dwd_sample_source', recordId: '2',
      fields: [
        { key: 'id', value: '2' },
        { key: 'title', value: '多模态大模型知识推理方法研究' },
        { key: 'author_list', value: '张三;李四;王五' },
        { key: 'pub_year', value: '2026' },
        { key: 'doi', value: '10.2026/kg.104' },
        { key: 'abstract', value: '面向产业链多源数据，研究知识图谱构建与关系推理方法。提出基于多模态融合的实体识别框架，结合矩阵特征分解与图注意力实现跨模态实体对齐...' },
        { key: 'source_type', value: 'journal' },
        { key: 'journal', value: '情报学报' },
      ],
    },
    extraction: {
      model: 'glm-4.7-flash',
      llmInput: {
        systemPrompt: SYSTEM_PROMPT,
        userMessage: `源表: dwd_sample_source
记录 ID: 2

记录内容:
{
  "id": "2",
  "title": "多模态大模型知识推理方法研究",
  "author_list": "张三;李四;王五",
  "pub_year": 2026,
  "doi": "10.2026/kg.104",
  "abstract": "面向产业链多源数据，研究知识图谱构建与关系推理方法...",
  "source_type": "journal",
  "journal": "情报学报"
}

请抽取 Paper 实体，输出 JSON。`,
      },
      llmOutput: `{
  "entities": [
    {
      "type": "Paper",
      "id": "P-2",
      "properties": {
        "title": "多模态大模型知识推理方法研究",
        "authors": ["张三", "李四", "王五"],
        "publish_year": 2026,
        "doi": "10.2026/kg.104"
      },
      "confidence": 0.78
    }
  ],
  "relations": []
}`,
    },
    confidence: 0.78, threshold: 0.85,
    trace: {
      workflowId: 'sample-pipeline-b66f2362ea414310ae4666fae3e684f7',
      workflowType: 'kg.custom.steps',
      executionId: 'EXEC-492CF6AD2690445B',
      sourceTaskId: 'PI-20260825-C15446',
      pipelineStepId: 'extract',
    },
  },
  {
    id: 'MR-20260825-SCHOLAR-001',
    label: 'Scholar 实体',
    candidate: {
      _kind: 'entity', _nodeLabel: 'Scholar',
      id: 'S-100',
      name: '张三',
      org: '中国科学院自动化研究所',
      title: '研究员',
      research_fields: '知识图谱, 多模态推理',
      confidence: 0.72,
    },
    sourceRecord: {
      table: 'expert_basic_info', recordId: 'EXPERT-100',
      fields: [
        { key: 'id', value: 'EXPERT-100' },
        { key: 'name', value: '张三' },
        { key: 'affiliation', value: '中国科学院自动化研究所' },
        { key: 'position', value: '研究员' },
        { key: 'research_areas', value: '知识图谱;多模态推理' },
        { key: 'email', value: 'zhangsan@ia.cas.cn' },
        { key: 'orcid', value: '0000-0002-1234-5678' },
      ],
    },
    extraction: {
      model: 'glm-4.7-flash',
      llmInput: {
        systemPrompt: SYSTEM_PROMPT,
        userMessage: `源表: expert_basic_info
记录 ID: EXPERT-100

记录内容:
{
  "id": "EXPERT-100",
  "name": "张三",
  "affiliation": "中国科学院自动化研究所",
  "position": "研究员",
  "research_areas": "知识图谱;多模态推理",
  "email": "zhangsan@ia.cas.cn",
  "orcid": "0000-0002-1234-5678"
}

请抽取 Scholar 实体，输出 JSON。`,
      },
      llmOutput: `{
  "entities": [
    {
      "type": "Scholar",
      "id": "S-100",
      "properties": {
        "name": "张三",
        "org": "中国科学院自动化研究所",
        "title": "研究员",
        "research_fields": ["知识图谱", "多模态推理"]
      },
      "confidence": 0.72
    }
  ],
  "relations": []
}`,
    },
    confidence: 0.72, threshold: 0.85,
    trace: {
      workflowId: 'sample-pipeline-b66f2362ea414310ae4666fae3e684f7',
      workflowType: 'kg.custom.steps',
      executionId: 'EXEC-492CF6AD2690445B',
      sourceTaskId: 'PI-20260825-C15446',
      pipelineStepId: 'extract',
    },
  },
  {
    id: 'MR-20260825-CITES-001',
    label: 'CITES 关系',
    candidate: {
      _kind: 'relation',
      _edgeType: 'CITES',
      _fromId: 'P-2', _toId: 'P-5',
      _fromLabel: 'Paper', _toLabel: 'Paper',
      context: '文末参考文献 [12] 引用了《矩阵分析基础》',
      confidence: 0.72,
    },
    sourceRecord: {
      table: 'paper_references', recordId: '2',
      fields: [
        { key: 'id', value: '2' },
        { key: 'citing_paper_id', value: 'P-2' },
        { key: 'citing_paper_title', value: '多模态大模型知识推理方法研究' },
        { key: 'cited_paper_title', value: '矩阵分析基础' },
        { key: 'cited_doi', value: '10.2019.math.301' },
        { key: 'ref_index', value: '12' },
        { key: 'context_sentence', value: '本研究方法借鉴了矩阵分析中的特征分解技术[12]...' },
      ],
    },
    extraction: {
      model: 'glm-4.7-flash',
      llmInput: {
        systemPrompt: SYSTEM_PROMPT,
        userMessage: `源表: paper_references
记录 ID: 2

记录内容:
{
  "id": "2",
  "citing_paper_id": "P-2",
  "citing_paper_title": "多模态大模型知识推理方法研究",
  "cited_paper_title": "矩阵分析基础",
  "cited_doi": "10.2019.math.301",
  "ref_index": 12,
  "context_sentence": "本研究方法借鉴了矩阵分析中的特征分解技术[12]..."
}

请抽取引用关系（CITES），输出 JSON。`,
      },
      llmOutput: `{
  "entities": [],
  "relations": [
    {
      "type": "CITES",
      "from": "P-2",
      "to": "P-5",
      "properties": {
        "context": "文末参考文献 [12] 引用了《矩阵分析基础》"
      },
      "confidence": 0.72
    }
  ]
}`,
    },
    confidence: 0.72, threshold: 0.85,
    trace: {
      workflowId: 'sample-pipeline-b66f2362ea414310ae4666fae3e684f7',
      workflowType: 'kg.custom.steps',
      executionId: 'EXEC-492CF6AD2690445B',
      sourceTaskId: 'PI-20260825-C15446',
      pipelineStepId: 'extract',
    },
  },
  {
    id: 'MR-20260825-EMP-001',
    label: 'EMPLOYED_BY 关系',
    candidate: {
      _kind: 'relation',
      _edgeType: 'EMPLOYED_BY',
      _fromId: 'S-100', _toId: 'O-50',
      _fromLabel: 'Scholar', _toLabel: 'Organization',
      role: '研究员',
      period: '2020-06 至今',
      confidence: 0.69,
    },
    sourceRecord: {
      table: 'expert_employment', recordId: 'EMP-100',
      fields: [
        { key: 'id', value: 'EMP-100' },
        { key: 'expert_id', value: 'S-100' },
        { key: 'expert_name', value: '张三' },
        { key: 'org_id', value: 'O-50' },
        { key: 'org_name', value: '中国科学院自动化研究所' },
        { key: 'position', value: '研究员' },
        { key: 'start_date', value: '2020-06' },
        { key: 'end_date', value: '(空)' },
      ],
    },
    extraction: {
      model: 'glm-4.7-flash',
      llmInput: {
        systemPrompt: SYSTEM_PROMPT,
        userMessage: `源表: expert_employment
记录 ID: EMP-100

记录内容:
{
  "id": "EMP-100",
  "expert_id": "S-100",
  "expert_name": "张三",
  "org_id": "O-50",
  "org_name": "中国科学院自动化研究所",
  "position": "研究员",
  "start_date": "2020-06",
  "end_date": null
}

请抽取任职关系（EMPLOYED_BY），输出 JSON。`,
      },
      llmOutput: `{
  "entities": [],
  "relations": [
    {
      "type": "EMPLOYED_BY",
      "from": "S-100",
      "to": "O-50",
      "properties": {
        "role": "研究员",
        "period": "2020-06 至今"
      },
      "confidence": 0.69
    }
  ]
}`,
    },
    confidence: 0.69, threshold: 0.85,
    trace: {
      workflowId: 'sample-pipeline-b66f2362ea414310ae4666fae3e684f7',
      workflowType: 'kg.custom.steps',
      executionId: 'EXEC-492CF6AD2690445B',
      sourceTaskId: 'PI-20260825-C15446',
      pipelineStepId: 'extract',
    },
  },
]

const currentCaseId = ref(demoCases[0].id)
const currentCase = computed(() => demoCases.find(c => c.id === currentCaseId.value)!)

const candidateFields = computed(() =>
  Object.entries(currentCase.value.candidate).filter(([k]) => !k.startsWith('_'))
)
const isEntity = computed(() => currentCase.value.candidate._kind === 'entity')

const note = ref('')
const feedback = ref('')
const submitting = ref(false)
const decisionMade = ref<null | 'accept' | 'reject'>(null)

const switchCase = (id: string) => {
  currentCaseId.value = id
  note.value = ''
  feedback.value = ''
  decisionMade.value = null
}

const handleDecide = (accepted: boolean) => {
  if (submitting.value || decisionMade.value) return
  submitting.value = true
  window.setTimeout(() => {
    submitting.value = false
    decisionMade.value = accepted ? 'accept' : 'reject'
    const c = currentCase.value.candidate
    if (isEntity.value) {
      feedback.value = accepted
        ? `已通过 · 创建 ${c._nodeLabel} 节点 ${c.id}`
        : '已驳回 · 候选丢弃，不写图'
    } else {
      feedback.value = accepted
        ? `已通过 · 创建边 ${c._fromId} -[${c._edgeType}]-> ${c._toId}`
        : '已驳回 · 候选丢弃，不写图'
    }
  }, 400)
}
</script>

<template>
  <div class="direct-demo">
    <header class="dd-head">
      <RouterLink to="/manual-review" class="dd-back">← 返回处理队列</RouterLink>
      <h1>人工审核 · 候选入库决策</h1>
      <div class="dd-meta">
        <code>{{ currentCase.id }}</code>
        <span :class="['dd-status', `is-${decisionMade === 'accept' ? 'done' : decisionMade === 'reject' ? 'rejected' : 'open'}`]">{{ decisionMade === 'accept' ? '已通过' : decisionMade === 'reject' ? '已驳回' : '待处理' }}</span>
      </div>
    </header>

    <nav class="dd-switcher">
      <span class="dd-switcher-label">示例 schema：</span>
      <button v-for="c in demoCases" :key="c.id" :class="['dd-switch', { active: c.id === currentCaseId }]" @click="switchCase(c.id)">{{ c.label }}</button>
    </nav>

    <!-- 1. 原始记录（数据流起点） -->
    <section class="dd-block">
      <h2 class="dd-block-title">① 原始记录</h2>
      <p class="dd-source-head">
        来源表 <code>{{ currentCase.sourceRecord.table }}</code> · 记录 ID <code>{{ currentCase.sourceRecord.recordId }}</code>
      </p>
      <table class="dd-fields">
        <tbody>
          <tr v-for="f in currentCase.sourceRecord.fields" :key="f.key">
            <th>{{ f.key }}</th>
            <td>{{ f.value }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 2. 抽取推理过程（LLM 输入 + 输出） -->
    <section class="dd-block">
      <h2 class="dd-block-title">② 抽取推理过程</h2>
      <dl class="dd-extract-meta">
        <div><dt>使用模型</dt><dd>{{ currentCase.extraction.model }}</dd></div>
      </dl>
      <details class="dd-llm-io" open>
        <summary>LLM 输入（system prompt + user message）</summary>
        <div class="dd-llm-section">
          <h4>system prompt</h4>
          <pre>{{ currentCase.extraction.llmInput.systemPrompt }}</pre>
          <h4>user message</h4>
          <pre>{{ currentCase.extraction.llmInput.userMessage }}</pre>
        </div>
      </details>
      <details class="dd-llm-io" open>
        <summary>LLM 输出（JSON）</summary>
        <pre>{{ currentCase.extraction.llmOutput }}</pre>
      </details>
    </section>

    <!-- 3. 候选（LLM 输出规范化后的结果） -->
    <section class="dd-block">
      <h2 class="dd-block-title">③ 候选</h2>
      <p class="dd-hint">LLM 输出规范化后得到的候选实体/关系，这是你要决定是否入库的对象。</p>
      <div class="dd-candidate-head">
        <template v-if="isEntity">
          <strong class="dd-node-label">{{ currentCase.candidate._nodeLabel }}</strong>
          <code class="dd-object-id">{{ currentCase.candidate.id }}</code>
        </template>
        <template v-else>
          <div class="dd-relation">
            <span class="dd-relation-node">{{ currentCase.candidate._fromLabel }} · <code>{{ currentCase.candidate._fromId }}</code></span>
            <em class="dd-relation-edge">-[{{ currentCase.candidate._edgeType }}]-&gt;</em>
            <span class="dd-relation-node">{{ currentCase.candidate._toLabel }} · <code>{{ currentCase.candidate._toId }}</code></span>
          </div>
        </template>
      </div>
      <table class="dd-fields">
        <tbody>
          <tr v-for="[key, val] in candidateFields" :key="String(key)">
            <th>{{ key }}</th>
            <td>{{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 4. 为什么需要你确认（置信度来源可追溯） -->
    <section class="dd-block dd-why">
      <h2 class="dd-block-title">④ 为什么需要你确认</h2>
      <p>
        LLM 在 ② 的输出里给出 <code>confidence = {{ currentCase.confidence.toFixed(2) }}</code>，
        系统阈值 <strong>{{ currentCase.threshold.toFixed(2) }}</strong>。
        <strong>{{ currentCase.confidence.toFixed(2) }} &lt; {{ currentCase.threshold.toFixed(2) }}</strong>
        → 未达自动入库线 → 候选被隔离在写图前。通过则写入图，驳回则丢弃。
      </p>
      <details class="dd-trace">
        <summary>溯源信息（点击 ID 跳转任务详情）</summary>
        <dl>
          <div><dt>workflow</dt><dd><RouterLink :to="`/processing-instance/${currentCase.trace.workflowId}`" class="dd-trace-link"><code>{{ currentCase.trace.workflowId }}</code></RouterLink></dd></div>
          <div><dt>workflow 类型</dt><dd>{{ currentCase.trace.workflowType }}</dd></div>
          <div><dt>执行 ID</dt><dd><RouterLink :to="`/processing-instance/${currentCase.trace.executionId}`" class="dd-trace-link"><code>{{ currentCase.trace.executionId }}</code></RouterLink></dd></div>
          <div><dt>来源任务</dt><dd><RouterLink :to="`/processing-instance/${currentCase.trace.sourceTaskId}`" class="dd-trace-link"><code>{{ currentCase.trace.sourceTaskId }}</code></RouterLink></dd></div>
          <div><dt>产生 step</dt><dd>{{ currentCase.trace.pipelineStepId }}</dd></div>
        </dl>
      </details>
    </section>

    <!-- 5. 决策 -->
    <section v-if="!decisionMade" class="dd-block dd-decide">
      <h2 class="dd-block-title">⑤ 决策</h2>
      <label class="dd-note">
        <span>备注（可选）</span>
        <input v-model="note" placeholder="审核备注..." />
      </label>
      <div class="dd-actions">
        <button class="dd-accept" :disabled="submitting" @click="handleDecide(true)">
          <strong>通过·入库</strong>
          <em>{{ isEntity ? `创建 ${currentCase.candidate._nodeLabel} 节点` : `创建 ${currentCase.candidate._edgeType} 边` }}</em>
        </button>
        <button class="dd-reject" :disabled="submitting" @click="handleDecide(false)">
          <strong>驳回·丢弃</strong>
          <em>候选丢弃，不写图</em>
        </button>
      </div>
    </section>

    <p v-else class="dd-done">已决策 · {{ decisionMade === 'accept' ? '通过·入库' : '驳回·丢弃' }}</p>
    <p v-if="feedback" class="dd-feedback">{{ feedback }}</p>
  </div>
</template>

<style scoped>
.direct-demo {
  max-width: 820px;
  margin: 0 auto;
  padding: 24px 28px 40px;
  color: #17233b;
  font-size: 13px;
  line-height: 1.6;
}

.dd-head {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e4ecf6;
}

.dd-back {
  color: #165dff;
  font-size: 12px;
  text-decoration: none;
}

.dd-head h1 {
  margin: 8px 0 6px;
  font-size: 18px;
  font-weight: 600;
}

.dd-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dd-meta code {
  padding: 2px 8px;
  border-radius: 4px;
  background: #eef4ff;
  color: #175cd3;
  font-size: 11px;
}

.dd-status {
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 11px;
}

.dd-status.is-open { background: #fff0e8; color: #c4320a; }
.dd-status.is-done { background: #e9f8ef; color: #067647; }
.dd-status.is-rejected { background: #f2f4f7; color: #475467; }

.dd-switcher {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  padding: 10px 14px;
  border: 1px dashed #dce8f8;
  border-radius: 8px;
  background: #f8fbff;
}

.dd-switcher-label {
  color: #667085;
  font-size: 11px;
}

.dd-switch {
  padding: 5px 12px;
  border: 1px solid #dce8f8;
  border-radius: 99px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
}

.dd-switch.active {
  border-color: #165dff;
  background: #eef4ff;
  color: #165dff;
  font-weight: 600;
}

.dd-block {
  margin-bottom: 24px;
}

.dd-block-title {
  margin: 0 0 10px;
  padding-left: 10px;
  border-left: 3px solid #165dff;
  font-size: 13px;
  font-weight: 600;
  color: #344054;
}

.dd-hint {
  margin: 0 0 10px;
  color: #667085;
  font-size: 11px;
}

.dd-source-head {
  margin: 0 0 10px;
  color: #475569;
  font-size: 12px;
}

.dd-source-head code {
  padding: 2px 6px;
  border-radius: 3px;
  background: #f1f5fa;
  color: #344f73;
  font-size: 12px;
}

.dd-fields {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  overflow: hidden;
}

.dd-fields th,
.dd-fields td {
  padding: 9px 14px;
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  font-size: 13px;
  vertical-align: top;
}

.dd-fields tr:last-child th,
.dd-fields tr:last-child td {
  border-bottom: 0;
}

.dd-fields th {
  width: 180px;
  background: #f8fafc;
  color: #66758f;
  font-weight: 500;
  font-size: 12px;
}

.dd-fields td {
  color: #17233b;
  word-break: break-word;
}

.dd-extract-meta {
  margin: 0 0 10px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.dd-extract-meta > div {
  padding: 10px 12px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  background: #f8fafc;
}

.dd-extract-meta dt {
  color: #718099;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.dd-extract-meta dd {
  margin: 0;
  color: #17233b;
  font-size: 12px;
  font-weight: 500;
}

.dd-llm-io {
  margin-top: 10px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  background: #f8fafc;
}

.dd-llm-io summary {
  padding: 10px 14px;
  cursor: pointer;
  color: #667085;
  font-size: 12px;
}

.dd-llm-io pre {
  margin: 0;
  padding: 12px 14px;
  border-top: 1px solid #eef2f7;
  background: #fbfcfe;
  color: #344054;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
}

.dd-llm-section h4 {
  margin: 12px 14px 6px;
  color: #66758f;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.dd-llm-section h4:first-child {
  margin-top: 0;
}

.dd-llm-section pre {
  margin: 0 0 12px;
}

.dd-llm-section pre:last-child {
  margin-bottom: 0;
}

.dd-candidate-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.dd-node-label {
  font-size: 16px;
  font-weight: 700;
  color: #17233b;
}

.dd-object-id {
  padding: 2px 8px;
  border-radius: 4px;
  background: #f1f5fa;
  color: #344f73;
  font-size: 12px;
}

.dd-relation {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.dd-relation-node {
  font-size: 13px;
  color: #475569;
}

.dd-relation-node code {
  padding: 2px 6px;
  border-radius: 3px;
  background: #f1f5fa;
  color: #344f73;
  font-size: 12px;
}

.dd-relation-edge {
  color: #7f56d9;
  font-style: normal;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  background: #eee8ff;
}

.dd-why p {
  margin: 0 0 10px;
  color: #475569;
}

.dd-why strong {
  color: #b54708;
  font-weight: 600;
}

.dd-why code {
  padding: 2px 6px;
  border-radius: 3px;
  background: #fff0d5;
  color: #b54708;
  font-size: 12px;
  font-weight: 600;
}

.dd-trace {
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  background: #f8fafc;
}

.dd-trace summary {
  cursor: pointer;
  color: #667085;
  font-size: 12px;
}

.dd-trace dl {
  margin: 10px 0 0;
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 6px 14px;
}

.dd-trace dt {
  color: #718099;
  font-size: 11px;
}

.dd-trace dd {
  margin: 0;
  color: #344054;
  font-size: 12px;
}

.dd-trace dd code {
  padding: 2px 6px;
  border-radius: 3px;
  background: #eef4ff;
  color: #175cd3;
  font-size: 11px;
}

.dd-trace-link {
  text-decoration: none;
}

.dd-trace-link code {
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.dd-trace-link:hover code {
  background: #165dff;
  color: #fff;
}

.dd-decide {
  padding: 18px 20px;
  border: 1px solid #f4d39b;
  border-radius: 9px;
  background: #fffbf2;
}

.dd-decide .dd-block-title {
  border-left-color: #b54708;
  color: #b54708;
}

.dd-note {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
}

.dd-note span {
  color: #718099;
  font-size: 11px;
}

.dd-note input {
  padding: 8px 10px;
  border: 1px solid #dce8f8;
  border-radius: 5px;
  font: 13px/1.5 inherit;
  color: #17233b;
}

.dd-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.dd-accept,
.dd-reject {
  display: grid;
  gap: 4px;
  padding: 14px;
  border: 2px solid;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: opacity 0.15s;
}

.dd-accept {
  border-color: #12b76a;
  background: #12b76a;
  color: #fff;
}

.dd-reject {
  border-color: #d92d20;
  background: #d92d20;
  color: #fff;
}

.dd-accept strong,
.dd-reject strong {
  font-size: 15px;
  font-weight: 700;
}

.dd-accept em,
.dd-reject em {
  color: rgba(255, 255, 255, 0.85);
  font-style: normal;
  font-size: 11px;
}

.dd-accept:disabled,
.dd-reject:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dd-accept:hover:not(:disabled),
.dd-reject:hover:not(:disabled) {
  opacity: 0.92;
}

.dd-done {
  margin: 0;
  padding: 18px;
  text-align: center;
  border: 1px solid #e4ecf6;
  border-radius: 8px;
  background: #f8fafc;
  color: #475569;
  font-size: 14px;
}

.dd-feedback {
  margin-top: 16px;
  padding: 10px 14px;
  border: 1px solid #a6f4c5;
  border-radius: 6px;
  background: #ecfdf3;
  color: #067647;
  font-size: 12px;
}

@media (max-width: 720px) {
  .dd-extract-meta {
    grid-template-columns: 1fr;
  }
  .dd-actions {
    grid-template-columns: 1fr;
  }
}
</style>
