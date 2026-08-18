<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github-dark.css'
import {
  createEntitySchema,
  createRelationSchema,
  getScriptContent,
  getSchemaOverview,
  listAllSchemas,
  schemaErrorMessage,
  verifyAndSaveScript,
  type EntitySchemaCreatePayload,
  type RelationSchemaCreatePayload,
  type SchemaDefinition,
  type SchemaOverview,
} from '../../api/schemaManagement'
import { useToast } from '../../composables/use-toast'

hljs.registerLanguage('python', python)

type Entity = { id: string; name: string; label: string; level: '核心实体' | '支撑实体'; key: string; source: string; description: string; schema: SchemaDefinition }
type Relation = { id: string; name: string; label: string; source: string; target: string; basis: string; level?: '标准' | '扩展'; schema: SchemaDefinition }
type Attribute = { entity: string; key: string; core: string; dynamic: string; source: string }

type PropertyDataType = 'string' | 'int64' | 'double' | 'bool' | 'date' | 'datetime' | 'geo' | 'fixed_string'
type PropertyRow = { name: string; dataType: PropertyDataType; length: number; required: boolean }
type CreateForm = {
  name: string
  label: string
  description: string
  sourceEntityId: string
  targetEntityId: string
  properties: PropertyRow[]
}

const currentUserId = window.localStorage.getItem('tech-kg-schema-user-id') || 'schema-admin'
const router = useRouter()

const activeTab = ref('标准实体')
const keyword = ref('')
// 版本记录（已隐藏）
// const schemaVersionMessage = ref('')
const tabs = ['标准实体', '事实关系', '推理关系', '属性定义']

const entities = ref<Entity[]>([])

const factRelations = ref<Relation[]>([])
const inferenceRelations = ref<Relation[]>([])
const attributes = ref<Attribute[]>([])
// 版本记录（已隐藏）
// const schemaVersions = [
//   { version: 'v1.8', status: '当前版本', time: '2026-07-12 22:10', entities: '14 个标准实体', relations: '42 标准 / 9 推理', change: '统一候选层字段；新增 Event 类型；调整 3 项关系约束', publisher: '张建图' },
//   { version: 'v1.7', status: '历史版本', time: '2026-06-28 18:30', entities: '13 个标准实体', relations: '39 标准 / 8 推理', change: '增加 Project / Patent 字段映射与对齐规则', publisher: '张建图' },
//   { version: 'v1.6', status: '历史版本', time: '2026-06-10 20:06', entities: '10 个标准实体', relations: '31 标准 / 6 推理', change: '建立专家、机构、论文与项目的基础 Schema', publisher: '张建图' },
// ]

const { showToast } = useToast()

const overview = ref<SchemaOverview>({
  currentVersion: '',
  environment: '',
  releasedAt: '',
  entityTypes: 0,
  coreEntityTypes: 0,
  relationTypes: 0,
  factRelationTypes: 0,
  inferredRelationTypes: 0,
  propertyFields: 0,
  requiredFields: 0,
  constraintRules: 0,
  sourceMappings: 0,
})
const modalOpen = ref(false)
const createForm = ref<CreateForm>(emptyCreateForm())
const creating = ref(false)
const scriptByRow = ref<Record<string, { name: string; workflowDefinitionId: string | null }>>({})

// 上传脚本弹窗（行级「上传脚本/更换脚本」）
const uploadModalOpen = ref(false)
const uploadTargetId = ref('')
const uploadTargetName = ref('')
const uploadState = ref<'idle' | 'working' | 'success' | 'error'>('idle')
const uploadStage = ref('')
const uploadMessage = ref('')
const uploadIssues = ref<string[]>([])
const uploadFileName = ref('')
const uploadFileInput = ref<HTMLInputElement | null>(null)

// 查看脚本弹窗
const viewModalOpen = ref(false)
const viewState = ref<'loading' | 'ready' | 'error'>('loading')
const viewFilename = ref('')
const viewContent = ref('')
const viewError = ref('')
const viewCodeRef = ref<HTMLElement | null>(null)

const PROPERTY_TYPES: PropertyDataType[] = ['string', 'int64', 'double', 'bool', 'date', 'datetime', 'geo', 'fixed_string']

function emptyCreateForm(): CreateForm {
  return {
    name: '',
    label: '',
    description: '',
    sourceEntityId: '',
    targetEntityId: '',
    properties: [{ name: '', dataType: 'string', length: 64, required: true }],
  }
}

function isRelationTab(): boolean {
  return activeTab.value === '事实关系' || activeTab.value === '推理关系'
}

function addProperty() {
  createForm.value.properties.push({ name: '', dataType: 'string', length: 64, required: false })
}

function removeProperty(index: number) {
  createForm.value.properties.splice(index, 1)
}

function resolveDataType(row: PropertyRow): string {
  return row.dataType === 'fixed_string' ? `fixed_string(${row.length || 64})` : row.dataType
}

const createDdlPreview = computed(() => {
  const f = createForm.value
  const keyword = isRelationTab() ? 'EDGE' : 'TAG'
  const parts = f.properties
    .filter((p) => p.name.trim())
    .map((p) => {
      let col = `${p.name} ${resolveDataType(p)}`
      if (p.required) col += ' NOT NULL'
      return col
    })
  return `CREATE ${keyword} IF NOT EXISTS ${f.name || '...'}(${parts.join(', ')});`
})

function mapEntity(schema: SchemaDefinition): Entity {
  return {
    id: schema.id,
    name: schema.name,
    label: schema.label,
    level: schema.isCore ? '核心实体' : '支撑实体',
    key: schema.identityKey,
    source: schema.mappings.join(' / '),
    description: schema.description,
    schema,
  }
}

function mapRelation(schema: SchemaDefinition): Relation {
  return {
    id: schema.id,
    name: schema.name,
    label: schema.label,
    source: schema.sourceSchemaName || '',
    target: schema.targetSchemaName || '',
    basis: schema.description,
    level: schema.isSystem ? '标准' : '扩展',
    schema,
  }
}

function applyDefinitions(definitions: SchemaDefinition[]) {
  const entitySchemas = definitions.filter((item) => item.kind === 'entity')
  entities.value = entitySchemas.map(mapEntity)
  factRelations.value = definitions
    .filter((item) => item.kind === 'relation' && item.relationCategory === 'fact')
    .map(mapRelation)
  inferenceRelations.value = definitions
    .filter((item) => item.kind === 'relation' && item.relationCategory === 'inferred')
    .map(mapRelation)
  attributes.value = entitySchemas
    .filter((item) => item.isCore)
    .map((item) => ({
      entity: item.name,
      key: item.attributeIdentityKey || item.identityKey,
      core: item.properties
        .filter((property) => property.category === 'core')
        .map((property) => property.name)
        .join(', '),
      dynamic: item.properties
        .filter((property) => property.category === 'dynamic')
        .map((property) => property.name)
        .join(', '),
      source: item.attributeSource || item.mappings.join(' / '),
    }))
  scriptByRow.value = Object.fromEntries(
    definitions
      .filter((item) => item.script)
      .map((item) => [
        item.name,
        {
          name: item.script!.filename,
          workflowDefinitionId: item.script!.workflowDefinitionId,
        },
      ]),
  )
}

function executeSchemaWorkflow(schemaName: string) {
  const definitionId = scriptByRow.value[schemaName]?.workflowDefinitionId
  if (!definitionId) {
    showToast('该脚本未定义 workflow(payload)，不能在工作流平台执行', 'warning')
    return
  }
  void router.push({
    name: 'tasks',
    query: { module: '图谱构建', workflowDefinitionId: definitionId },
  })
}

async function loadSchemas() {
  const [overviewData, definitions] = await Promise.all([
    getSchemaOverview(),
    listAllSchemas(currentUserId),
  ])
  overview.value = overviewData
  applyDefinitions(definitions)
}

function openCreate() {
  createForm.value = emptyCreateForm()
  modalOpen.value = true
}

function schemaKey(name: string) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replaceAll('_', '-')
    .toLowerCase()
}

async function saveItem() {
  const f = createForm.value
  if (!f.name.trim()) {
    showToast(isRelationTab() ? '请填写关系英文名（UPPER_SNAKE_CASE）' : '请填写实体名（PascalCase）', 'warning')
    return
  }
  if (!f.label.trim()) {
    showToast('请填写中文名', 'warning')
    return
  }
  const props = f.properties.filter((p) => p.name.trim())
  if (props.length === 0) {
    showToast('至少添加一个属性', 'warning')
    return
  }
  const relation = isRelationTab()
  if (relation && (!f.sourceEntityId || !f.targetEntityId)) {
    showToast('请选择起点和终点实体', 'warning')
    return
  }

  const properties = props.map((p) => ({
    name: p.name.trim(),
    dataType: resolveDataType(p),
    required: p.required,
    rule: '',
    category: 'core' as const,
  }))

  creating.value = true
  try {
    if (relation) {
      const source = entities.value.find((e) => e.id === f.sourceEntityId)
      const target = entities.value.find((e) => e.id === f.targetEntityId)
      const payload: RelationSchemaCreatePayload = {
        schemaKey: schemaKey(f.name),
        name: f.name.trim(),
        label: f.label.trim(),
        description: f.description || '',
        sourceSchemaId: f.sourceEntityId,
        targetSchemaId: f.targetEntityId,
        sourceExpression: source?.name || '',
        targetExpression: target?.name || '',
        relationCategory: activeTab.value === '事实关系' ? 'fact' : 'inferred',
        properties,
      }
      const result = await createRelationSchema(payload, currentUserId)
      toastCreateResult(result)
    } else {
      const payload: EntitySchemaCreatePayload = {
        schemaKey: schemaKey(f.name),
        name: f.name.trim(),
        label: f.label.trim(),
        description: f.description || '',
        identityKey: '',
        properties,
        mappings: [],
        isCore: false,
      }
      const result = await createEntitySchema(payload, currentUserId)
      toastCreateResult(result)
    }
    modalOpen.value = false
    await loadSchemas()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    creating.value = false
  }
}

function toastCreateResult(result: SchemaDefinition) {
  if (result.ddlStatus === 'succeeded') {
    showToast(`已创建并执行图 DDL：${result.ddlStatement?.split('(')[0] || result.name}`, 'success')
  } else if (result.ddlStatus === 'failed') {
    showToast(`Schema 已保存，但图 DDL 执行失败：${result.ddlError || '未知错误'}`, 'warning')
  } else {
    showToast('Schema 已创建', 'success')
  }
}

function openUploadModal(rowId: string, rowName: string) {
  uploadTargetId.value = rowId
  uploadTargetName.value = rowName
  uploadState.value = 'idle'
  uploadStage.value = ''
  uploadMessage.value = ''
  uploadIssues.value = []
  uploadFileName.value = ''
  uploadModalOpen.value = true
}

function pickUploadFile() {
  uploadFileInput.value?.click()
}

async function onUploadFileChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  uploadFileName.value = file.name
  uploadState.value = 'working'
  uploadStage.value = 'starting'
  uploadMessage.value = '正在上传并校验...'
  uploadIssues.value = []
  let succeeded = false
  try {
    await verifyAndSaveScript(uploadTargetId.value, file, currentUserId, {
      onProgress: (stage, message) => {
        uploadStage.value = stage
        uploadMessage.value = message
      },
      onSuccess: () => {
        succeeded = true
        uploadState.value = 'success'
        uploadMessage.value = '脚本已通过安全校验并保存'
      },
      onError: (message, issues) => {
        uploadState.value = 'error'
        uploadMessage.value = message
        uploadIssues.value = issues
      },
    })
    if (succeeded) {
      await loadSchemas()
    }
  } catch (error) {
    uploadState.value = 'error'
    uploadMessage.value = schemaErrorMessage(error)
    uploadIssues.value = []
  }
}

function closeUploadModal() {
  uploadModalOpen.value = false
}

async function openViewModal(rowId: string, rowName: string) {
  uploadModalOpen.value = false
  viewModalOpen.value = true
  viewState.value = 'loading'
  viewFilename.value = rowName
  viewContent.value = ''
  viewError.value = ''
  try {
    const data = await getScriptContent(rowId, currentUserId)
    viewFilename.value = data.filename
    viewContent.value = data.content
    viewState.value = 'ready'
    await nextTick()
    if (viewCodeRef.value) {
      viewCodeRef.value.removeAttribute('data-highlighted')
      viewCodeRef.value.className = 'language-python'
      hljs.highlightElement(viewCodeRef.value)
    }
  } catch (error) {
    viewState.value = 'error'
    viewError.value = schemaErrorMessage(error)
  }
}

onMounted(async () => {
  try {
    await loadSchemas()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
})
const normalizedKeyword = computed(() => keyword.value.trim().toLowerCase())
const matches = (row: unknown) => !normalizedKeyword.value || Object.values(row as Record<string, unknown>).join(' ').toLowerCase().includes(normalizedKeyword.value)
const filteredEntities = computed(() => entities.value.filter(matches))
const filteredFacts = computed(() => factRelations.value.filter(matches))
const filteredInference = computed(() => inferenceRelations.value.filter(matches))
const filteredAttributes = computed(() => attributes.value.filter(matches))
</script>

<template>
  <main class="schema-page">
    <section class="schema-summary" aria-label="Schema 概览">
      <article><span>标准实体</span><strong>{{ overview.entityTypes }}</strong><em>专家、机构、论文等</em></article>
      <article><span>标准事实关系</span><strong>{{ overview.factRelationTypes }}</strong><em>专家、机构、成果等</em></article>
      <article><span>业务推理关系</span><strong>{{ overview.inferredRelationTypes }}</strong><em>均基于事实关系计算</em></article>
      <!-- <article><span>当前 Schema 版本</span><strong>v1.8</strong><em>已发布 · 2026-07-12</em></article> -->
    </section>

    <section class="schema-shell">
      <nav class="schema-tabs"><button v-for="tab in tabs" :key="tab" type="button" :class="{ active: activeTab === tab }" @click="activeTab=tab;keyword=''">{{ tab }}</button></nav>
      <div class="schema-toolbar"><div><strong>{{ activeTab }}</strong><span v-if="activeTab === '属性定义'">枚举字典作为属性约束统一维护</span></div><div class="schema-toolbar__actions"><button v-if="activeTab !== '属性定义'" class="primary" type="button" @click="openCreate">＋ 增加</button><label><span>⌕</span><input v-model="keyword" :placeholder="`搜索${activeTab}`" /></label></div></div>
      <!-- <p v-if="schemaVersionMessage" class="schema-version-message">{{ schemaVersionMessage }}</p> -->

      <div v-if="activeTab === '标准实体'" class="schema-table-wrap"><table><thead><tr><th>实体中文名</th><th>Schema 名称</th><th>主键 / 唯一标识</th><th>主要来源表组</th><th>建模说明</th><th>操作</th></tr></thead><tbody><tr v-for="row in filteredEntities" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.key }}</td><td>{{ row.source }}</td><td>{{ row.description }}</td><td class="schema-actions"><div class="schema-actions__inner"><button type="button" class="schema-action-link" :title="scriptByRow[row.name] ? '更换脚本' : '上传脚本'" @click="openUploadModal(row.id, row.name)">{{ scriptByRow[row.name] ? '更换脚本' : '上传脚本' }} →</button><button v-if="scriptByRow[row.name]" type="button" class="schema-action-link" @click="openViewModal(row.id, row.name)">查看脚本 →</button><button v-if="scriptByRow[row.name]?.workflowDefinitionId" type="button" class="schema-action-link" @click="executeSchemaWorkflow(row.name)">执行工作流 →</button><span v-if="scriptByRow[row.name]" class="script-badge">{{ scriptByRow[row.name].name }}</span></div></td></tr></tbody></table></div>

      <div v-else-if="activeTab === '事实关系'" class="schema-table-wrap"><table><thead><tr><th>关系中文名</th><th>关系英文名</th><th>起点</th><th>终点</th><th>生成依据</th><th>操作</th></tr></thead><tbody><tr v-for="row in filteredFacts" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.source }}</td><td>{{ row.target }}</td><td>{{ row.basis }}</td><td class="schema-actions"><div class="schema-actions__inner"><button type="button" class="schema-action-link" :title="scriptByRow[row.name] ? '更换脚本' : '上传脚本'" @click="openUploadModal(row.id, row.name)">{{ scriptByRow[row.name] ? '更换脚本' : '上传脚本' }} →</button><button v-if="scriptByRow[row.name]" type="button" class="schema-action-link" @click="openViewModal(row.id, row.name)">查看脚本 →</button><span v-if="scriptByRow[row.name]" class="script-badge">{{ scriptByRow[row.name].name }}</span></div></td></tr></tbody></table></div>

      <div v-else-if="activeTab === '推理关系'" class="schema-table-wrap"><table><thead><tr><th>推理关系</th><th>Schema 名称</th><th>起点</th><th>终点</th><th>生成依据</th><th>操作</th></tr></thead><tbody><tr v-for="row in filteredInference" :key="row.name"><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.source }}</td><td>{{ row.target }}</td><td>{{ row.basis }}</td><td class="schema-actions"><div class="schema-actions__inner"><button type="button" class="schema-action-link" :title="scriptByRow[row.name] ? '更换脚本' : '上传脚本'" @click="openUploadModal(row.id, row.name)">{{ scriptByRow[row.name] ? '更换脚本' : '上传脚本' }} →</button><button v-if="scriptByRow[row.name]" type="button" class="schema-action-link" @click="openViewModal(row.id, row.name)">查看脚本 →</button><span v-if="scriptByRow[row.name]" class="script-badge">{{ scriptByRow[row.name].name }}</span></div></td></tr></tbody></table></div>

      <div v-else-if="activeTab === '属性定义'" class="schema-table-wrap"><table><thead><tr><th>实体</th><th>主键</th><th>核心属性</th><th>动态属性 / 补充</th><th>主要来源</th></tr></thead><tbody><tr v-for="row in filteredAttributes" :key="row.entity"><td><code>{{ row.entity }}</code></td><td><b>{{ row.key }}</b></td><td class="mono-list">{{ row.core }}</td><td>{{ row.dynamic }}</td><td>{{ row.source }}</td></tr></tbody></table></div>

      <!-- 版本记录（已隐藏）
      <div v-else class="schema-table-wrap schema-version-table"><table><thead><tr><th>版本</th><th>状态</th><th>发布时间</th><th>实体范围</th><th>关系范围</th><th>变更内容</th><th>发布人</th><th>操作</th></tr></thead><tbody><tr v-for="row in schemaVersions" :key="row.version"><td><code>{{ row.version }}</code></td><td><span :class="row.status === '当前版本' ? 'core' : 'support'">{{ row.status }}</span></td><td>{{ row.time }}</td><td>{{ row.entities }}</td><td>{{ row.relations }}</td><td>{{ row.change }}</td><td>{{ row.publisher }}</td><td><div class="schema-version-actions"><button type="button" @click="schemaVersionMessage = `已打开 ${row.version} 的完整变更清单。`">变更详情</button><button v-if="row.status !== '当前版本'" class="danger" type="button" @click="schemaVersionMessage = `已创建回退至 ${row.version} 的申请，通过影响分析与审批后才会执行。`">申请回退</button></div></td></tr></tbody></table></div>
      -->
    </section>

    <Teleport to="body">
      <div v-if="modalOpen" class="schema-modal schema-create-modal">
        <button class="schema-modal__mask" type="button" @click="modalOpen = false"></button>
        <aside class="schema-modal__panel schema-create-panel">
          <header><h2>新增{{ activeTab }}</h2><button type="button" @click="modalOpen = false">×</button></header>
          <div class="schema-modal__body schema-create-body">
            <div class="create-row">
              <label class="create-field">
                <span>{{ isRelationTab() ? '关系英文名 *' : '实体名 *' }}</span>
                <input v-model="createForm.name" :placeholder="isRelationTab() ? 'USES_TECHNOLOGY' : 'Gadget'" />
              </label>
              <label class="create-field">
                <span>中文名 *</span>
                <input v-model="createForm.label" placeholder="如：技术" />
              </label>
            </div>

            <div v-if="isRelationTab()" class="create-row">
              <label class="create-field">
                <span>起点实体 *</span>
                <select v-model="createForm.sourceEntityId">
                  <option value="">请选择</option>
                  <option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}（{{ e.label }}）</option>
                </select>
              </label>
              <label class="create-field">
                <span>终点实体 *</span>
                <select v-model="createForm.targetEntityId">
                  <option value="">请选择</option>
                  <option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}（{{ e.label }}）</option>
                </select>
              </label>
            </div>

            <label class="create-field create-field--full">
              <span>建模说明</span>
              <textarea v-model="createForm.description" rows="2"></textarea>
            </label>

            <div class="create-props">
              <div class="create-props__head">
                <span>属性列表 *</span>
                <button type="button" class="create-props__add" @click="addProperty">＋ 添加属性</button>
              </div>
              <div v-for="(p, i) in createForm.properties" :key="i" class="create-prop-row">
                <input v-model="p.name" placeholder="属性名" class="prop-name" />
                <select v-model="p.dataType" class="prop-type">
                  <option v-for="t in PROPERTY_TYPES" :key="t" :value="t">{{ t }}</option>
                </select>
                <input v-if="p.dataType === 'fixed_string'" v-model.number="p.length" type="number" min="1" max="1024" class="prop-len" placeholder="N" />
                <label class="prop-required"><input v-model="p.required" type="checkbox" />必填</label>
                <button type="button" class="prop-remove" @click="removeProperty(i)" title="删除">×</button>
              </div>
            </div>

            <div class="create-ddl">
              <span class="create-ddl__label">nGQL 预览（创建时将执行）</span>
              <pre class="create-ddl__pre">{{ createDdlPreview }}</pre>
            </div>
          </div>
          <footer>
            <button type="button" @click="modalOpen = false">取消</button>
            <button type="button" class="primary" :disabled="creating" @click="saveItem">{{ creating ? '创建中...' : '创建' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <input ref="uploadFileInput" type="file" accept=".py" hidden @change="onUploadFileChosen" />

    <Teleport to="body">
      <div v-if="uploadModalOpen" class="schema-modal script-upload-modal">
        <button class="schema-modal__mask" type="button" @click="closeUploadModal"></button>
        <aside class="schema-modal__panel">
          <header><h2>上传脚本 · {{ uploadTargetName }}</h2><button type="button" @click="closeUploadModal">×</button></header>
          <div class="schema-modal__body">
            <div v-if="uploadState === 'idle'" class="upload-idle">
              <p>选择 .py 脚本文件，上传后将通过 LLM 进行安全校验，校验通过才会保存。</p>
              <button type="button" class="primary" @click="pickUploadFile">选择 .py 文件</button>
            </div>
            <div v-else-if="uploadState === 'working'" class="upload-working">
              <div class="spinner" aria-label="校验中"></div>
              <div class="upload-working__text">
                <strong>{{ uploadFileName }}</strong>
                <span class="upload-stage">阶段：{{ uploadStage }}</span>
                <span class="upload-message">{{ uploadMessage }}</span>
              </div>
            </div>
            <div v-else-if="uploadState === 'success'" class="upload-result">
              <div class="upload-result__icon ok">✓</div>
              <strong>脚本已通过安全校验并保存</strong>
              <span>{{ uploadFileName }}</span>
            </div>
            <div v-else class="upload-result">
              <div class="upload-result__icon err">✕</div>
              <strong>校验未通过</strong>
              <p class="upload-result__msg">{{ uploadMessage }}</p>
              <ul v-if="uploadIssues.length" class="upload-result__issues">
                <li v-for="(issue, i) in uploadIssues" :key="i">{{ issue }}</li>
              </ul>
            </div>
          </div>
          <footer>
            <template v-if="uploadState === 'working'">
              <button type="button" disabled>校验中...</button>
            </template>
            <template v-else>
              <button v-if="uploadState === 'error'" type="button" class="primary" @click="uploadState = 'idle'">重新选择</button>
              <button type="button" @click="closeUploadModal">{{ uploadState === 'success' ? '关闭' : '取消' }}</button>
            </template>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="viewModalOpen" class="schema-modal script-view-modal">
        <button class="schema-modal__mask" type="button" @click="viewModalOpen = false"></button>
        <aside class="schema-modal__panel script-view-panel">
          <header><h2>查看脚本 · {{ viewFilename }}</h2><button type="button" @click="viewModalOpen = false">×</button></header>
          <div class="schema-modal__body script-view-body">
            <div v-if="viewState === 'loading'" class="view-loading">加载中...</div>
            <div v-else-if="viewState === 'error'" class="view-error">{{ viewError }}</div>
            <pre v-else class="script-pre"><code ref="viewCodeRef" class="language-python">{{ viewContent }}</code></pre>
          </div>
          <footer>
            <button type="button" @click="viewModalOpen = false">关闭</button>
          </footer>
        </aside>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.schema-page{display:flex;height:100%;min-height:0;overflow:hidden;padding-bottom:2px;color:#142443;flex-direction:column}.schema-summary{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin-bottom:12px}.schema-summary article{display:grid;gap:5px;padding:13px 15px;border:1px solid #bfd6fa;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.schema-summary span{color:#687996;font-size:11px}.schema-summary strong{font-size:23px}.schema-summary em{color:#8191aa;font-size:10px;font-style:normal}.schema-flow{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));margin-bottom:12px;padding:12px;border:1px solid #c5d9f6;border-radius:8px;background:#fff}.schema-flow>div{position:relative;display:flex;align-items:center;gap:7px;min-width:0;padding:4px 15px 4px 5px}.schema-flow i{display:grid;flex:0 0 auto;place-items:center;width:23px;height:23px;border-radius:50%;background:#eaf2ff;color:#165dff;font-size:10px;font-style:normal}.schema-flow span{color:#40536f;font-size:10px;line-height:15px}.schema-flow b{position:absolute;right:2px;color:#9bb5d9}.schema-shell{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #bcd4f7;border-radius:9px;background:#fff;box-shadow:0 10px 24px rgba(48,105,194,.08);flex-direction:column}.schema-tabs{display:flex;flex:0 0 auto;overflow:auto;padding:0 12px;border-bottom:1px solid #dce8f8}.schema-tabs button{padding:12px 15px;border:0;border-bottom:2px solid transparent;background:transparent;color:#566985;white-space:nowrap;cursor:pointer}.schema-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.schema-toolbar{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:14px;padding:10px 13px;border-bottom:1px solid #e3ebf6;background:#f8fbff}.schema-toolbar>div{display:flex;align-items:center;gap:10px}.schema-toolbar strong{font-size:13px}.schema-toolbar>div span{color:#7b8ba3;font-size:10px}.schema-toolbar label{display:flex;align-items:center;gap:6px;width:270px;padding:0 9px;border:1px solid #c7d8ef;border-radius:5px;background:#fff}.schema-toolbar input{width:100%;height:30px;border:0;outline:0;font-size:11px}.schema-table-wrap{flex:1;min-height:0;max-height:none;overflow:auto}.schema-table-wrap table,.trace-layout table{width:100%;border-collapse:collapse;font-size:11px}.schema-table-wrap th,.schema-table-wrap td,.trace-layout td{padding:11px 13px;border-bottom:1px solid #e5edf8;text-align:left;line-height:17px;vertical-align:top}.schema-table-wrap th{position:sticky;z-index:2;top:0;background:#f1f6fc;color:#5e6f88;white-space:nowrap}.schema-table-wrap td{color:#344763}.schema-table-wrap td:nth-child(5),.schema-table-wrap td:nth-child(6){max-width:330px}.schema-table-wrap code,.trace-layout code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;white-space:nowrap}.core,.support,.evidence,.auto,.review{display:inline-flex;padding:2px 7px;border-radius:999px;background:#e9f8ef;color:#067647;font-size:9px;white-space:nowrap}.support{background:#f0f2f5;color:#5e6b7e}.evidence{background:#f0edff;color:#6941c6}.auto{white-space:normal}.review{background:#fff3df;color:#b54708;white-space:normal}.mono-list{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}.arrow{margin:0 5px;color:#8ba2c2}.candidate-layout{display:grid;flex:1;min-height:0;grid-template-columns:minmax(0,1fr) 245px}.candidate-layout>.schema-table-wrap{grid-column:1}.candidate-note{grid-column:1/-1;padding:10px 13px;border-bottom:1px solid #dce8f8;background:#f3f8ff}.candidate-note strong{font-size:12px}.candidate-note p{margin:3px 0 0;color:#657690;font-size:10px}.mention-fields{grid-column:2;grid-row:2;padding:13px;border-left:1px solid #e0e9f5;background:#fafcff}.mention-fields strong{display:block;margin-bottom:10px;font-size:12px}.mention-fields span{display:inline-flex;margin:0 5px 6px 0;padding:3px 6px;border-radius:4px;background:#edf4ff;color:#315b95;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}.trace-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:12px;background:#f8fbff}.trace-layout section{overflow:hidden;border:1px solid #d5e3f5;border-radius:7px;background:#fff}.trace-layout header{display:flex;align-items:flex-start;justify-content:space-between;padding:13px;border-bottom:1px solid #e3ebf6}.trace-layout h2{margin:0;font-size:13px}.trace-layout p{margin:3px 0 0;color:#7b899e;font-size:10px}.trace-layout header>span{color:#165dff;font-size:10px}.trace-layout table{display:block;max-height:390px;overflow:auto}.trace-layout tbody,.trace-layout tr{display:table;width:100%;table-layout:fixed}.trace-layout td:first-child{width:160px}@media(max-width:1250px){.schema-summary{grid-template-columns:repeat(3,1fr)}.schema-flow{grid-template-columns:repeat(4,1fr)}.schema-flow b{display:none}}@media(max-width:900px){.schema-summary{grid-template-columns:repeat(2,1fr)}.trace-layout{grid-template-columns:1fr}.candidate-layout{display:block}.mention-fields{border-top:1px solid #e0e9f5;border-left:0}}

/* Layout refinements for wide management screens. */
.schema-page{box-sizing:border-box;padding:2px 2px 18px}
.schema-summary article{position:relative;min-height:92px;padding:15px 17px;overflow:hidden}
.schema-summary article::after{position:absolute;right:-15px;bottom:-28px;width:72px;height:72px;border-radius:50%;background:rgba(22,93,255,.055);content:""}
.schema-summary span{font-size:12px}.schema-summary strong{font-size:26px;line-height:31px}.schema-summary em{font-size:11px}

.schema-flow{display:block;margin-bottom:14px;padding:0;border-color:#bcd4f7;background:linear-gradient(180deg,#fff,#f6faff)}
.schema-flow>header{display:flex;align-items:center;gap:12px;padding:10px 15px;border-bottom:1px solid #dce8f8}
.schema-flow>header strong{color:#243b5d;font-size:13px}
.schema-flow>header span{color:#7a8aa3;font-size:11px}
.schema-flow ol{display:flex;align-items:stretch;margin:0;padding:12px 14px;list-style:none}
.schema-flow li{position:relative;flex:1;display:flex;align-items:center;gap:9px;min-width:0;padding:8px 26px 8px 10px;border:1px solid #d5e4f7;border-right:0;background:#fff}
.schema-flow li:first-child{border-radius:6px 0 0 6px}
.schema-flow li:last-child{border-right:1px solid #d5e4f7;border-radius:0 6px 6px 0}
.schema-flow li:not(:last-child)::after{position:absolute;z-index:2;right:-8px;width:15px;height:15px;border-top:1px solid #d5e4f7;border-right:1px solid #d5e4f7;background:#fff;content:"";transform:rotate(45deg)}
.schema-flow li i{position:relative;z-index:3;display:grid;flex:0 0 auto;place-items:center;width:25px;height:25px;border-radius:50%;background:#e9f2ff;color:#165dff;font-size:11px;font-style:normal;font-weight:700}
.schema-flow li:nth-child(4) i,.schema-flow li:nth-child(5) i{background:#e9f8ef;color:#067647}
.schema-flow li:nth-child(6) i,.schema-flow li:nth-child(7) i{background:#f1edff;color:#6941c6}
.schema-flow li span{position:relative;z-index:3;color:#40536f;font-size:11px;line-height:16px}

.schema-shell{min-height:0}
.schema-tabs{min-height:45px;background:#fff}
.schema-tabs button{padding:13px 18px;font-size:12px}
.schema-toolbar{min-height:48px;padding:9px 16px}
.schema-toolbar strong{font-size:15px}
.schema-toolbar>div span{font-size:11px}

.trace-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;min-height:435px;padding:16px;background:#f7faff}
.trace-card{display:flex;min-width:0;overflow:hidden;border:1px solid #cfdef2;border-radius:9px;background:#fff;box-shadow:0 6px 16px rgba(48,105,194,.06);flex-direction:column}
.trace-card>header{display:flex;align-items:center;justify-content:space-between;min-height:68px;padding:13px 15px;border-bottom:1px solid #e0e9f5;background:linear-gradient(90deg,#eef5ff,#fff 62%)}
.trace-card>header>div{display:flex;align-items:center;gap:10px}
.trace-card>header i{display:grid;place-items:center;width:31px;height:31px;border-radius:8px;background:#165dff;color:#fff;font-size:11px;font-style:normal;font-weight:700}
.trace-card>header span{display:block}
.trace-card h2{margin:0;color:#20324e;font-size:14px}
.trace-card p{margin:3px 0 0;color:#74849b;font-size:10px}
.trace-card>header b{padding:4px 8px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:10px;font-weight:500;white-space:nowrap}
.trace-card dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;margin:0;padding:10px}
.trace-card dl>div{min-width:0;padding:10px 11px;border-right:1px solid #e8eef7;border-bottom:1px solid #e8eef7}
.trace-card dl>div:nth-child(2n){border-right:0}
.trace-card dt{margin-bottom:5px}
.trace-card dd{margin:0;color:#53647d;font-size:10px;line-height:16px}
.trace-card code{display:inline-flex;max-width:100%;padding:3px 7px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trace-layout>aside{grid-column:1/-1;display:flex;align-items:center;gap:22px;min-height:48px;padding:10px 14px;border:1px solid #d4e1f2;border-radius:7px;background:#fff}
.trace-layout>aside strong{color:#263b5a;font-size:11px;white-space:nowrap}
.trace-layout>aside span{display:flex;align-items:flex-start;gap:7px;color:#64758d;font-size:10px;line-height:16px}
.trace-layout>aside i{flex:0 0 auto;width:6px;height:6px;margin-top:5px;border-radius:50%;background:#165dff}

@media(max-width:1500px){.schema-flow li{padding-right:18px}.schema-flow li span{font-size:10px}.trace-card dl{grid-template-columns:1fr}.trace-card dl>div{border-right:0}}
@media(max-width:1100px){.schema-flow ol{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.schema-flow li,.schema-flow li:last-child{border:1px solid #d5e4f7;border-radius:6px}.schema-flow li::after{display:none}.trace-layout{grid-template-columns:1fr}.trace-layout>aside{grid-column:1;align-items:flex-start;flex-direction:column;gap:7px}.trace-card dl{grid-template-columns:repeat(2,1fr)}.trace-card dl>div{border-right:1px solid #e8eef7}.trace-card dl>div:nth-child(2n){border-right:0}}
.schema-summary{grid-template-columns:repeat(3,minmax(0,1fr))}
.schema-version-message{margin:0;padding:9px 13px;border-bottom:1px solid #b7d0f5;background:#eef5ff;color:#344f7a;font-size:11px}
.schema-version-table{max-height:470px}.schema-version-table td:nth-child(6){min-width:280px}.schema-version-actions{display:flex;gap:6px}.schema-version-actions button{padding:3px 7px;border:1px solid #bdd0ea;border-radius:4px;background:#fff;color:#165dff;font-size:9px;white-space:nowrap;cursor:pointer}.schema-version-actions button.danger{border-color:#f6b9b4;color:#b42318}
@media(max-width:1500px){.schema-summary{grid-template-columns:repeat(3,1fr)}}

.schema-toolbar__actions{display:flex;align-items:center;gap:10px}
.schema-toolbar .primary{height:32px;padding:0 14px;border:0;border-radius:6px;background:#165dff;color:#fff;font-size:13px;cursor:pointer}
.schema-toolbar .primary:hover{background:#0e4ed8}
.schema-actions{white-space:nowrap}
.schema-actions__inner{display:flex;gap:8px;align-items:center}
.schema-action-link{border:0;background:transparent;color:#165dff;font-size:11px;line-height:17px;padding:0;cursor:pointer}
.schema-action-link:hover{text-decoration:underline}
.script-badge{max-width:120px;padding:0 8px;height:22px;border:1px solid #d8e6fa;border-radius:11px;background:#f7faff;color:#4e5969;font-size:11px;line-height:22px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.schema-modal{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:24px}
.schema-modal__mask{position:fixed;inset:0;border:0;background:rgba(16,38,76,0.42);backdrop-filter:blur(2px);cursor:pointer}
.schema-modal__panel{position:relative;z-index:1;width:min(520px,100%);overflow:hidden;border-radius:8px;background:#fff;box-shadow:0 24px 70px rgba(28,58,107,0.3)}
.schema-modal__panel header{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #e5e6eb}
.schema-modal__panel header h2{margin:0;font-size:15px;font-weight:600;color:#1d2129}
.schema-modal__panel header button{width:24px;height:24px;border:0;background:transparent;color:#86909c;font-size:18px;cursor:pointer}
.schema-modal__body{padding:18px;display:flex;flex-direction:column;gap:12px;max-height:60vh;overflow:auto}
.schema-modal__body label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#4e5969}
.schema-modal__body label em{color:#f53f3f;font-style:normal;margin-left:2px}
.schema-modal__body input,.schema-modal__body textarea{height:32px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;color:#1d2129}
.schema-modal__body textarea{height:auto;padding:6px 8px;resize:vertical}
.schema-modal__panel footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid #e5e6eb}
.schema-modal__panel footer button{height:32px;padding:0 14px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:13px;cursor:pointer}
.schema-modal__panel footer .primary{background:#165dff;color:#fff;border-color:#165dff}
.schema-modal__panel footer button:disabled{opacity:.6;cursor:not-allowed}

/* 上传脚本弹窗 */
.script-upload-modal .schema-modal__body{min-height:140px}
.upload-idle{display:flex;flex-direction:column;gap:14px;align-items:center;padding:14px 0;text-align:center}
.upload-idle p{margin:0;color:#4e5969;font-size:13px;line-height:20px}
.upload-idle .primary{height:34px;padding:0 18px;border:0;border-radius:6px;background:#165dff;color:#fff;font-size:13px;cursor:pointer}
.upload-working{display:flex;align-items:center;gap:16px;padding:10px 4px}
.spinner{flex:0 0 auto;width:28px;height:28px;border:3px solid #e3ebf6;border-top-color:#165dff;border-radius:50%;animation:spin 0.9s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.upload-working__text{display:flex;flex-direction:column;gap:4px;min-width:0}
.upload-working__text strong{font-size:13px;color:#1d2129;word-break:break-all}
.upload-stage{color:#165dff;font-size:11px}
.upload-message{color:#74849b;font-size:11px}
.upload-result{display:flex;flex-direction:column;gap:8px;align-items:center;padding:18px 0;text-align:center}
.upload-result__icon{display:grid;place-items:center;width:42px;height:42px;border-radius:50%;font-size:22px;color:#fff}
.upload-result__icon.ok{background:#15a05a}
.upload-result__icon.err{background:#e54848}
.upload-result strong{font-size:14px;color:#1d2129}
.upload-result span{color:#74849b;font-size:12px}
.upload-result__msg{margin:0;color:#e54848;font-size:12px;line-height:18px;max-width:420px;word-break:break-all}
.upload-result__issues{margin:6px 0 0;padding:10px 14px;list-style:none;border-radius:6px;background:#fff3f3;color:#b42318;font-size:12px;line-height:20px;text-align:left;max-width:440px;max-height:200px;overflow:auto}
.upload-result__issues li{padding:2px 0}

/* 查看脚本弹窗 */
.script-view-panel{width:min(820px,100%)}
.script-view-body{max-height:72vh;padding:0}
.script-pre{margin:0;max-height:72vh;overflow:auto;background:#0d1117;border-radius:0}
.script-pre code{display:block;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;line-height:20px;background:transparent;color:#c9d1d9;white-space:pre}
.view-loading,.view-error{padding:30px;text-align:center;color:#74849b;font-size:13px}
.view-error{color:#e54848}

/* 创建 Schema 弹窗 */
.schema-create-panel{width:min(680px,100%)}
.schema-create-body{max-height:72vh;gap:14px}
.create-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.create-field{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#4e5969}
.create-field--full{grid-column:1/-1}
.create-field input,.create-field textarea,.create-field select{height:32px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;color:#1d2129;background:#fff}
.create-field textarea{height:auto;padding:6px 8px;resize:vertical}
.create-field select{appearance:auto}
.create-props{display:flex;flex-direction:column;gap:8px}
.create-props__head{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#4e5969}
.create-props__add{height:26px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#165dff;font-size:12px;cursor:pointer}
.create-props__add:hover{border-color:#165dff}
.create-prop-row{display:grid;grid-template-columns:1.4fr 1.2fr 0.6fr auto auto;gap:8px;align-items:center}
.prop-name,.prop-type,.prop-len{height:30px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:12px;color:#1d2129;background:#fff}
.prop-type{appearance:auto}
.prop-required{display:flex;align-items:center;gap:4px;font-size:11px;color:#4e5969;white-space:nowrap}
.prop-required input{margin:0}
.prop-remove{width:24px;height:24px;border:0;border-radius:4px;background:transparent;color:#e54848;font-size:16px;cursor:pointer}
.prop-remove:hover{background:#fff3f3}
.create-ddl{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.create-ddl__label{font-size:11px;color:#74849b}
.create-ddl__pre{margin:0;padding:10px 12px;max-height:140px;overflow:auto;background:#0d1117;border-radius:6px;color:#c9d1d9;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;line-height:18px;white-space:pre-wrap;word-break:break-all}
</style>
