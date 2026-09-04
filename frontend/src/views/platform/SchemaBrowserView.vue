<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { IconSearch } from '@arco-design/web-vue/es/icon'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github-dark.css'
import {
  addSchemaProperty,
  backfillSchemaHistory,
  createEntitySchema,
  createRelationSchema,
  deleteSchema,
  deleteSchemaProperty,
  getSchemaDetail,
  getScriptContent,
  getSchemaOverview,
  getSchemaTopology,
  listAllSchemas,
  replaceSchemaSources,
  schemaErrorMessage,
  triggerSchemaExtraction,
  verifyAndSaveScript,
  type EntitySchemaCreatePayload,
  type RelationSchemaCreatePayload,
  type SchemaDefinition,
  type SchemaOverview,
  type SchemaProperty,
  type SchemaScript,
} from '../../api/schemaManagement'
import { currentUserId as getCurrentUserId } from '../../api/currentUser'
import { graphSpace } from '../../config'
import { listGraphSpaces } from '../../api/graphSpace'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import {
  PROP_NAME_RULE,
  SCHEMA_DESC_RULE,
  SCHEMA_ENTITY_NAME_RULE,
  SCHEMA_LABEL_RULE,
  SCHEMA_RELATION_NAME_RULE,
  validateText,
} from '../../utils/textInput'
import KgGraphCanvas from '../../components/kg-graph-canvas.vue'
import type { GraphEdgeData, GraphNodeData } from '../../data/graph-presets'
import { useToast } from '../../composables/use-toast'
import {
  buildRequiredPropertyRows,
  emptyPropertyRow,
  PROPERTY_TYPES,
  sanitizeLengthInput,
  validateFixedLength,
  type PropertyDataType,
  type PropertyRow,
} from './schema-browser/propertyRows'
import SourceBindings from './schema-browser/sourceBindings.vue'
import {
  emptySourceBindingRow,
  toSourcePayload,
  type SourceBindingRow,
} from './schema-browser/sourceBindingRows'

hljs.registerLanguage('python', python)

type Entity = { id: string; name: string; label: string; level: '核心实体' | '支撑实体'; key: string; source: string; description: string; schema: SchemaDefinition }
type Relation = { id: string; name: string; label: string; source: string; target: string; basis: string; schema: SchemaDefinition }

type CreateForm = {
  graphSpace: string
  name: string
  label: string
  description: string
  sourceEntityId: string
  targetEntityId: string
  properties: PropertyRow[]
  sources: SourceBindingRow[]
}

const currentUserId = getCurrentUserId()

const activeTab = ref('标准实体')
// Schema 管理按图空间维度隔离：列表/拓扑/新建都以当前空间为准
const graphSpaces = ref<string[]>([])
const activeSpace = ref('')
const keyword = ref('')
// 版本记录（已隐藏）
// const schemaVersionMessage = ref('')
const tabs = ['标准实体', '关系']

const entities = ref<Entity[]>([])

const relations = ref<Relation[]>([])
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
const createFormRef = ref()
const createFormRules = {
  name: [
    { required: true, message: '请输入名称' },
    {
      validator: (value: string, callback: (error?: string) => void) => {
        const isRelation = isRelationTab()
        const error = validateText(
          isRelation ? '关系英文名' : '实体名',
          value || '',
          isRelation ? SCHEMA_RELATION_NAME_RULE : SCHEMA_ENTITY_NAME_RULE,
        )
        callback(error ?? undefined)
      },
    },
  ],
  label: [
    { required: true, message: '请输入中文名' },
    {
      validator: (value: string, callback: (error?: string) => void) =>
        callback(validateText('中文名', value || '', SCHEMA_LABEL_RULE) ?? undefined),
    },
  ],
  description: [
    {
      validator: (value: string, callback: (error?: string) => void) =>
        callback(value ? (validateText('说明', value, SCHEMA_DESC_RULE) ?? undefined) : undefined),
    },
  ],
  sourceEntityId: [{
    validator: (value: string, callback: (error?: string) => void) =>
      callback(!isRelationTab() || value ? undefined : '请选择起点实体'),
  }],
  targetEntityId: [{
    validator: (value: string, callback: (error?: string) => void) =>
      callback(!isRelationTab() || value ? undefined : '请选择终点实体'),
  }],
  properties: [{
    validator: (value: PropertyRow[], callback: (error?: string) => void) =>
      callback(value.some((property) => property.name.trim()) ? undefined : '请至少填写一个属性名称'),
  }],
}

function validatePropName(value: string, callback: (error?: string) => void) {
  callback(value.trim() ? (validateText('属性名', value, PROP_NAME_RULE) ?? undefined) : undefined)
}
const creating = ref(false)
const confirming = ref(false)
const scriptByRow = ref<Record<string, SchemaScript>>({})

// Schema 拓扑总览（实体 -关系-> 实体 元图谱）
const topologyNodes = ref<GraphNodeData[]>([])
const topologyEdges = ref<GraphEdgeData[]>([])

const ENTITY_TYPE_NODE_TYPES: Array<[RegExp, GraphNodeData['nodeType']]> = [
  [/专家|学者|人才/, 'expert'],
  [/论文|文献/, 'paper'],
  [/机构|高校|大学|院所/, 'org'],
  [/企业|公司/, 'company'],
  [/专利/, 'source'],
  [/项目|课题/, 'project'],
  [/事件|资讯/, 'event'],
  [/产业链|行业/, 'chain'],
]

function topologyNodeType(name: string): GraphNodeData['nodeType'] {
  for (const [pattern, type] of ENTITY_TYPE_NODE_TYPES) {
    if (pattern.test(name)) return type
  }
  return 'topic'
}

function applyTopology(data: {
  nodes: SchemaDefinition[]
  edges: Array<SchemaDefinition & { sourceSchemaId: string | null; targetSchemaId: string | null }>
}) {
  const nodeIdSet = new Set(data.nodes.map((node) => node.id))
  const angleStep = (Math.PI * 2) / Math.max(data.nodes.length, 1)
  topologyNodes.value = data.nodes.map((node, index) => ({
    id: node.id,
    label: node.label || node.name,
    nodeType: topologyNodeType(`${node.label}${node.name}`),
    x: 480 + Math.cos(angleStep * index) * 140,
    y: 270 + Math.sin(angleStep * index) * 100,
    radius: node.isCore ? 14 : 10,
    entityType: node.name,
    relations: node.kindLabel,
    evidence: node.description ? [node.description] : [],
  }))
  // 过滤端点缺失的孤儿关系（起点/终点实体 schema 已被删除）
  topologyEdges.value = data.edges
    .filter((edge) => edge.sourceSchemaId && edge.targetSchemaId
      && nodeIdSet.has(edge.sourceSchemaId) && nodeIdSet.has(edge.targetSchemaId))
    .map((edge) => ({
      id: edge.id,
      from: edge.sourceSchemaId as string,
      to: edge.targetSchemaId as string,
      label: edge.label || edge.name,
      category: '直接关系',
    }))
}

async function loadTopology() {
  try {
    applyTopology(await getSchemaTopology(activeSpace.value || undefined))
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
}

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

// 删除确认弹窗
const deleteModalOpen = ref(false)
const deleteTarget = ref<SchemaDefinition | null>(null)
const deleting = ref(false)

// 属性管理弹窗（行级「属性管理」）
const propertyModalOpen = ref(false)
const propertyTarget = ref<SchemaDefinition | null>(null)
const propertySaving = ref(false)
const propertyForm = ref<{ name: string; dataType: PropertyDataType; length: string; required: boolean }>({
  name: '',
  dataType: 'string',
  length: '64',
  required: false,
})
// 删除属性二次确认
const propertyDeleteTarget = ref<SchemaProperty | null>(null)
const propertyDeleteConfirmOpen = ref(false)
const propertyDeleting = ref(false)
// 变更成功后的「立即触发重新抽取」二次确认
const propertyExtractConfirmOpen = ref(false)

// 来源表管理弹窗（行级「来源表」）
const sourcesModalOpen = ref(false)
const sourcesTarget = ref<SchemaDefinition | null>(null)
const sourcesForm = ref<SourceBindingRow[]>([])
const sourcesSaving = ref(false)
const extracting = ref(false)

// 回填历史数据（清空来源水位全量重跑）；脚本落后于 Schema 时需强确认
const backfilling = ref(false)
const backfillConfirmOpen = ref(false)

async function requestBackfill() {
  const target = sourcesTarget.value
  if (!target || backfilling.value || extracting.value) return
  if (target.script?.stale) {
    backfillConfirmOpen.value = true
    return
  }
  await runBackfill(false)
}

async function runBackfill(force: boolean) {
  const target = sourcesTarget.value
  if (!target || backfilling.value) return
  backfilling.value = true
  try {
    const result = await backfillSchemaHistory(target.id, currentUserId, { force })
    showToast(
      `回填已触发（执行 ${result.executionId}，重置 ${result.watermarksCleared} 个来源水位），可在任务中心查看进度`,
      'success',
    )
    backfillConfirmOpen.value = false
    sourcesModalOpen.value = false
  } catch (error) {
    const message = schemaErrorMessage(error)
    // 列表数据可能过期：后端判定脚本已落后 → 升级为强确认
    if (!force && message.includes('回填可能无效')) {
      backfillConfirmOpen.value = true
      return
    }
    showToast(message, 'warning')
  } finally {
    backfilling.value = false
  }
}

async function triggerExtraction(schema: SchemaDefinition) {
  if (extracting.value) return null
  extracting.value = true
  try {
    const result = await triggerSchemaExtraction(schema.id, currentUserId)
    if (result.staleScript) {
      showToast(
        `抽取已触发（执行 ${result.executionId}），但当前脚本落后于 Schema ${result.staleBehind} 版：` +
          '新增属性不会被产出、已删属性不再写入，建议更新脚本后回填历史数据',
        'warning',
      )
    } else {
      showToast(`抽取已触发（执行 ${result.executionId}），可在任务中心查看进度`, 'success')
    }
    return result
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
    return null
  } finally {
    extracting.value = false
  }
}

async function confirmTriggerExtraction() {
  const target = propertyTarget.value
  propertyExtractConfirmOpen.value = false
  if (!target) return
  await triggerExtraction(target)
}

async function triggerExtractionFromSources() {
  const target = sourcesTarget.value
  if (!target || sourcesSaving.value) return
  const saved = await saveSources()
  if (saved) await triggerExtraction(sourcesTarget.value || target)
}

function openSourcesModal(schema: SchemaDefinition) {
  if (!schema.canManageProperties) {
    showToast(schema.isSystem ? '系统 Schema 仅 Schema 管理员可维护来源表' : '只有创建者或管理员可维护来源表', 'warning')
    return
  }
  sourcesTarget.value = schema
  sourcesForm.value = (schema.sources || []).map((s) => ({
    datasourceId: s.datasourceId,
    databaseName: s.databaseName,
    tableName: s.tableName,
    pkColumn: s.pkColumn,
    timeColumn: s.timeColumn,
  }))
  sourcesModalOpen.value = true
}

async function saveSources(): Promise<boolean> {
  const target = sourcesTarget.value
  if (!target || sourcesSaving.value) return false
  const payloads = sourcesForm.value
    .map((row) => toSourcePayload(row))
    .filter((item): item is NonNullable<typeof item> => item !== null)
  if (payloads.length !== sourcesForm.value.length) {
    showToast('存在未选择完整的来源表绑定（数据源/库/表均需选择）', 'warning')
    return false
  }
  sourcesSaving.value = true
  try {
    await replaceSchemaSources(target.id, payloads, currentUserId)
    showToast('来源表绑定已保存', 'success')
    sourcesModalOpen.value = false
    await loadSchemas()
    return true
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
    return false
  } finally {
    sourcesSaving.value = false
  }
}

function openPropertyModal(schema: SchemaDefinition) {
  if (!schema.canManageProperties) {
    showToast(schema.isSystem ? '系统 Schema 仅 Schema 管理员可维护属性' : '只有创建者或管理员可维护属性', 'warning')
    return
  }
  propertyTarget.value = schema
  propertyForm.value = { name: '', dataType: 'string', length: '64', required: false }
  propertyDeleteTarget.value = null
  propertyDeleteConfirmOpen.value = false
  propertyExtractConfirmOpen.value = false
  propertyModalOpen.value = true
}

function closePropertyModal() {
  propertyModalOpen.value = false
  propertyTarget.value = null
}

async function refreshPropertyTarget() {
  const target = propertyTarget.value
  if (!target) return
  try {
    propertyTarget.value = await getSchemaDetail(target.id, currentUserId)
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
  await loadSchemas().catch(() => undefined)
}

async function submitAddProperty() {
  const target = propertyTarget.value
  if (!target || propertySaving.value) return
  const name = propertyForm.value.name.trim()
  if (!name) {
    showToast('请填写属性名', 'warning')
    return
  }
  const propNameError = validateText('属性名', name, PROP_NAME_RULE)
  if (propNameError) {
    showToast(propNameError, 'warning')
    return
  }
  if (propertyForm.value.dataType === 'fixed_string') {
    const error = validateFixedLength(propertyForm.value.length)
    if (error) {
      showToast(error, 'warning')
      return
    }
  }
  const dataType =
    propertyForm.value.dataType === 'fixed_string'
      ? `fixed_string(${propertyForm.value.length})`
      : propertyForm.value.dataType
  propertySaving.value = true
  try {
    const result = await addSchemaProperty(
      target.id,
      { name, dataType, required: propertyForm.value.required, rule: '', category: 'core' },
      currentUserId,
    )
    if (result.ddlStatus === 'succeeded') {
      showToast(`属性已新增并执行图 DDL：${result.ddlStatement}`, 'success')
    } else {
      showToast(`属性已新增，但图 DDL 执行失败：${result.ddlError || '未知错误'}`, 'warning')
    }
    propertyForm.value = { name: '', dataType: 'string', length: '64', required: false }
    await refreshPropertyTarget()
    propertyExtractConfirmOpen.value = true
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    propertySaving.value = false
  }
}

function requestDeleteProperty(prop: SchemaProperty) {
  propertyDeleteTarget.value = prop
  propertyDeleteConfirmOpen.value = true
}

async function confirmDeleteProperty() {
  const target = propertyTarget.value
  const prop = propertyDeleteTarget.value
  if (!target || !prop || propertyDeleting.value) return
  propertyDeleting.value = true
  try {
    const result = await deleteSchemaProperty(target.id, prop.name, currentUserId)
    if (result.warnings?.length) {
      showToast(`属性 ${prop.name} 已删除，但存在引用警告：${result.warnings.join('；')}`, 'warning')
    } else {
      const ddlNote =
        result.ddlStatus === 'succeeded'
          ? '图库列及其全部数据已删除'
          : '图库未找到该列，仅删除目录记录'
      showToast(`属性 ${prop.name} 已删除（${ddlNote}）`, 'success')
    }
    propertyDeleteConfirmOpen.value = false
    propertyDeleteTarget.value = null
    await refreshPropertyTarget()
    propertyExtractConfirmOpen.value = true
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    propertyDeleting.value = false
  }
}

function openDeleteModal(schema: SchemaDefinition) {
  if (!schema.canDelete) {
    showToast(schema.isSystem ? '系统内置 Schema 不可删除' : '被关系引用的实体 Schema 不可删除', 'warning')
    return
  }
  deleteTarget.value = schema
  deleteModalOpen.value = true
}

async function confirmDelete() {
  const target = deleteTarget.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    await deleteSchema(target.id, currentUserId)
    showToast(`已删除 ${target.label || target.name}`, 'success')
    deleteModalOpen.value = false
    deleteTarget.value = null
    await Promise.all([loadSchemas(), loadTopology()])
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    deleting.value = false
  }
}

// 查看脚本弹窗
const viewModalOpen = ref(false)
const viewState = ref<'loading' | 'ready' | 'error'>('loading')
const viewFilename = ref('')
const viewContent = ref('')
const viewError = ref('')
const viewCodeRef = ref<HTMLElement | null>(null)

function emptyCreateForm(): CreateForm {
  return {
    graphSpace: activeSpace.value,
    name: '',
    label: '',
    description: '',
    sourceEntityId: '',
    targetEntityId: '',
    properties: buildRequiredPropertyRows(isRelationTab() ? 'relation' : 'entity'),
    sources: [],
  }
}

function isRelationTab(): boolean {
  return activeTab.value === '关系'
}

function addProperty() {
  createForm.value.properties.push(emptyPropertyRow())
}

function addSourceBinding() {
  createForm.value.sources.push(emptySourceBindingRow())
}

function removeProperty(index: number) {
  if (createForm.value.properties[index]?.locked) return
  createForm.value.properties.splice(index, 1)
}

function resolveDataType(row: PropertyRow): string {
  return row.dataType === 'fixed_string' ? `fixed_string(${row.length})` : row.dataType
}

function fixedLengthInvalid(row: PropertyRow): boolean {
  return row.dataType === 'fixed_string' && validateFixedLength(row.length) !== null
}

/** fixed_string 长度输入：即时净化（仅数字、≤64 字符），非法输入不会静默变成默认值 */
function onLengthInput(row: PropertyRow, event: Event) {
  const input = event.target as HTMLInputElement
  row.length = sanitizeLengthInput(input.value)
  input.value = row.length
}

const propertyLengthError = computed(() =>
  propertyForm.value.dataType === 'fixed_string' ? validateFixedLength(propertyForm.value.length) : null,
)
const propertyLengthInvalid = computed(() => propertyLengthError.value !== null)

function onPropertyLengthInput(event: Event) {
  const input = event.target as HTMLInputElement
  propertyForm.value.length = sanitizeLengthInput(input.value)
  input.value = propertyForm.value.length
}

/** 首个 fixed_string 长度校验错误文案（用于 toast）；全部合法返回 null */
function firstFixedLengthError(rows: PropertyRow[]): string | null {
  for (const [index, row] of rows.entries()) {
    if (row.dataType !== 'fixed_string') continue
    const error = validateFixedLength(row.length)
    if (error) return `第 ${index + 1} 个属性「${row.name || '未命名'}」：${error}`
  }
  return null
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
    schema,
  }
}

function applyDefinitions(definitions: SchemaDefinition[]) {
  const entitySchemas = definitions.filter((item) => item.kind === 'entity')
  entities.value = entitySchemas.map(mapEntity)
  relations.value = definitions
    .filter((item) => item.kind === 'relation')
    .map(mapRelation)
  scriptByRow.value = Object.fromEntries(
    definitions
      .filter((item) => item.script)
      .map((item) => [item.name, item.script as SchemaScript]),
  )
}

async function loadSchemas() {
  const [overviewData, definitions] = await Promise.all([
    getSchemaOverview(activeSpace.value || undefined),
    listAllSchemas(currentUserId, activeSpace.value || undefined),
  ])
  overview.value = overviewData
  applyDefinitions(definitions)
}

async function loadSpaces() {
  try {
    graphSpaces.value = await listGraphSpaces(currentUserId)
  } catch {
    graphSpaces.value = []
  }
  if (!activeSpace.value && graphSpaces.value.length) {
    // 构建期注入的 VITE_GRAPH_SPACE 优先（与部署环境默认空间一致），不在列表再回退首个
    const preferred = graphSpace
    activeSpace.value =
      preferred && graphSpaces.value.includes(preferred) ? preferred : graphSpaces.value[0]
  }
}

async function switchSpace(value: string | number | boolean | Record<string, unknown> | unknown[]) {
  const space = String(value ?? '')
  if (space === activeSpace.value) return
  // 清空（未选择）= 不按空间过滤，列出所有可见空间的 Schema
  activeSpace.value = space
  try {
    await Promise.all([loadSchemas(), loadTopology()])
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
}

function openCreate() {
  createForm.value = emptyCreateForm()
  confirming.value = false
  modalOpen.value = true
}

function schemaKey(name: string) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replaceAll('_', '-')
    .toLowerCase()
}

async function saveItem() {
  // arco form.validate() 校验失败时 reject（不是 resolve 错误对象）——必须捕获，
  // 否则静默中断（空表单点「预览并创建」无反应的根因）。
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  const f = createForm.value
  if (!f.graphSpace) {
    showToast('请选择图空间', 'warning')
    return
  }
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
  const lengthError = firstFixedLengthError(props)
  if (lengthError) {
    showToast(lengthError, 'warning')
    return
  }
  const relation = isRelationTab()
  if (relation && (!f.sourceEntityId || !f.targetEntityId)) {
    showToast('请选择起点和终点实体', 'warning')
    return
  }
  // 来源表绑定必须完整（FUNC-00435）：不完整的行直接阻止提交，而不是静默丢弃
  const sources = f.sources.map((row) => toSourcePayload(row))
  if (sources.some((item) => item === null)) {
    showToast('存在未选择完整的来源表绑定（数据源/库/表均需选择），请补全或删除该行', 'warning')
    return
  }

  if (!confirming.value) {
    confirming.value = true
    return
  }

  const properties = props.map((p) => ({
    name: p.name.trim(),
    dataType: resolveDataType(p),
    required: p.required,
    rule: '',
    category: p.locked ? ('required' as const) : ('core' as const),
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
        llmConfigId: null,
        graphSpace: f.graphSpace,
      }
      const result = await createRelationSchema(payload, currentUserId)
      toastCreateResult(result)
      await bindSourcesAfterCreate(result.id, f.sources)
    } else {
      const payload: EntitySchemaCreatePayload = {
        schemaKey: schemaKey(f.name),
        name: f.name.trim(),
        label: f.label.trim(),
        description: f.description || '',
        identityKey: '',
        properties,
        isCore: false,
        llmConfigId: null,
        graphSpace: f.graphSpace,
      }
      const result = await createEntitySchema(payload, currentUserId)
      toastCreateResult(result)
      await bindSourcesAfterCreate(result.id, f.sources)
    }
    modalOpen.value = false
    await loadSchemas()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    creating.value = false
  }
}

async function bindSourcesAfterCreate(schemaId: string, sources: SourceBindingRow[]) {
  if (!sources.length) return
  const payloads = sources
    .map((row) => toSourcePayload(row))
    .filter((item): item is NonNullable<typeof item> => item !== null)
  if (!payloads.length) return
  try {
    await replaceSchemaSources(schemaId, payloads, currentUserId)
    showToast('来源表绑定已保存', 'success')
  } catch (error) {
    showToast(
      `来源表绑定保存失败（${schemaErrorMessage(error)}），可稍后在行级「来源表」入口补绑`,
      'warning',
    )
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
    await loadSpaces()
    await loadSchemas()
    await loadTopology()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
})
const normalizedKeyword = computed(() => keyword.value.trim().toLowerCase())
const matches = (row: unknown) => !normalizedKeyword.value || Object.values(row as Record<string, unknown>).join(' ').toLowerCase().includes(normalizedKeyword.value)
const filteredEntities = computed(() => entities.value.filter(matches))
const filteredRelations = computed(() => relations.value.filter(matches))

// 列表属性 chip 展示（前 6 个 + 溢出展开明细）
const PROPERTY_CHIP_LIMIT = 6
const expandedPropertyRows = ref<Set<string>>(new Set())

function propertyChips(schema: SchemaDefinition): string[] {
  return schema.properties.slice(0, PROPERTY_CHIP_LIMIT).map((p) => `${p.name}:${p.dataType}`)
}

function propertyOverflow(schema: SchemaDefinition): number {
  return Math.max(schema.properties.length - PROPERTY_CHIP_LIMIT, 0)
}

function togglePropertyDetail(schemaId: string): void {
  const next = new Set(expandedPropertyRows.value)
  if (next.has(schemaId)) {
    next.delete(schemaId)
  } else {
    next.add(schemaId)
  }
  expandedPropertyRows.value = next
}
</script>

<template>
  <main class="schema-page">
    <section class="schema-shell schema-topology-shell" aria-label="Schema 拓扑总览">
      <div class="schema-toolbar">
        <div><strong>Schema 拓扑总览</strong><span>实体与关系的元图谱</span></div>
        <div class="schema-topology-legend" aria-label="图例">
          <span class="legend-item"><i class="legend-node"></i>实体 {{ overview.entityTypes }}</span>
          <span class="legend-item"><i class="legend-edge"></i>关系 {{ overview.relationTypes }}</span>
        </div>
      </div>
      <div class="schema-topology-canvas">
        <KgGraphCanvas
          v-if="topologyNodes.length"
          :nodes="topologyNodes"
          :edges="topologyEdges"
          show-edge-labels
          aria-label="Schema 实体关系拓扑"
        />
        <div v-else class="schema-topology-canvas__empty">暂无实体 Schema，新增后此处将展示实体 -关系-> 实体元图谱</div>
      </div>
    </section>

    <section class="schema-catalog">
      <nav class="schema-tabs" aria-label="Schema 类型切换">
        <div class="schema-tabs__items">
          <button v-for="tab in tabs" :key="tab" type="button" :class="{ active: activeTab === tab }" @click="activeTab=tab;keyword=''">{{ tab }}</button>
        </div>
        <div class="schema-toolbar__actions">
          <div class="space-picker">
            <span>图空间</span>
            <a-select
              id="schema-space-select"
              :model-value="activeSpace || undefined"
              class="schema-space-select"
              allow-clear
              placeholder="全部空间"
              :scrollbar="false"
              style="width: 170px"
              @change="switchSpace"
              @clear="switchSpace('')"
            >
              <a-option v-for="s in graphSpaces" :key="s" :value="s">{{ s }}</a-option>
            </a-select>
          </div>
          <a-input v-model="keyword" class="schema-search-input" :max-length="SEARCH_KEYWORD_MAX_LENGTH" :aria-label="`搜索${activeTab}`" :placeholder="`搜索${activeTab}`">
            <template #prefix><IconSearch /></template>
          </a-input>
          <button class="primary" type="button" @click="openCreate">＋ 增加</button>
        </div>
      </nav>
      <div class="schema-shell schema-table-shell">

      <div v-if="activeTab === '标准实体'" class="schema-table-wrap"><table><thead><tr><th>实体中文名</th><th>Schema 名称</th><th>说明</th><th>属性</th><th>操作</th></tr></thead><tbody><template v-for="row in filteredEntities" :key="row.id"><tr><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.description }}</td><td class="schema-props-cell"><div class="prop-chips"><span v-for="chip in propertyChips(row.schema)" :key="chip" class="prop-chip" :title="chip">{{ chip }}</span><button v-if="propertyOverflow(row.schema)" type="button" class="prop-chip prop-chip--more" title="展开属性明细" @click="togglePropertyDetail(row.id)">+{{ propertyOverflow(row.schema) }}</button></div></td><td class="schema-actions"><div class="schema-actions__inner"><button v-if="row.schema.canManageProperties" type="button" class="schema-action-link" :title="scriptByRow[row.name] ? '更换脚本' : '上传脚本'" @click="openUploadModal(row.id, row.name)">{{ scriptByRow[row.name] ? '更换脚本' : '上传脚本' }} →</button><span v-if="scriptByRow[row.name]?.stale" class="script-badge" :title="`脚本落后于 Schema ${scriptByRow[row.name].staleBehind} 版：新增/删除的属性不会生效，请更新脚本`">落后 {{ scriptByRow[row.name].staleBehind }} 版</span><span v-if="scriptByRow[row.name]?.lastRunStatus === 'failed'" class="script-badge script-badge--failed" :title="`上次运行失败：${scriptByRow[row.name].lastRunError || '未知错误'}`">上次失败</span><button v-if="scriptByRow[row.name]" type="button" class="schema-action-link" @click="openViewModal(row.id, row.name)">查看脚本 →</button><button type="button" class="schema-action-link" :disabled="!row.schema.canManageProperties" :title="row.schema.canManageProperties ? '维护来源表绑定（平台喂数抽取的读取源）' : (row.schema.isSystem ? '系统 Schema 仅管理员可维护来源表' : '只有创建者或管理员可维护来源表')" @click="openSourcesModal(row.schema)">来源表</button><button type="button" class="schema-action-link" :disabled="!row.schema.canManageProperties" :title="row.schema.canManageProperties ? '维护属性（新增 / 删除）' : (row.schema.isSystem ? '系统 Schema 仅管理员可维护属性' : '只有创建者或管理员可维护属性')" @click="openPropertyModal(row.schema)">属性管理</button><button type="button" class="schema-action-link schema-action-link--danger" :title="row.schema.canDelete ? '删除该 Schema' : (row.schema.isSystem ? '系统内置，不可删除' : '被关系引用，不可删除')" :disabled="!row.schema.canDelete" @click="openDeleteModal(row.schema)">删除</button></div></td></tr><tr v-if="expandedPropertyRows.has(row.id)" class="schema-prop-detail-row"><td :colspan="5"><div class="prop-detail"><span v-for="p in row.schema.properties" :key="p.name" class="prop-detail__item"><code>{{ p.name }}</code><em>{{ p.dataType }}</em><b v-if="p.required">必填</b><b v-if="p.locked" class="prop-detail__locked">🔒 公共</b></span></div></td></tr></template></tbody></table></div>

      <div v-else class="schema-table-wrap"><table><thead><tr><th>关系中文名</th><th>关系英文名</th><th>起点</th><th>终点</th><th>说明</th><th>属性</th><th>操作</th></tr></thead><tbody><template v-for="row in filteredRelations" :key="row.id"><tr><td><b>{{ row.label }}</b></td><td><code>{{ row.name }}</code></td><td>{{ row.source }}</td><td>{{ row.target }}</td><td>{{ row.basis }}</td><td class="schema-props-cell"><div class="prop-chips"><span v-for="chip in propertyChips(row.schema)" :key="chip" class="prop-chip" :title="chip">{{ chip }}</span><button v-if="propertyOverflow(row.schema)" type="button" class="prop-chip prop-chip--more" title="展开属性明细" @click="togglePropertyDetail(row.id)">+{{ propertyOverflow(row.schema) }}</button></div></td><td class="schema-actions"><div class="schema-actions__inner"><button v-if="row.schema.canManageProperties" type="button" class="schema-action-link" :title="scriptByRow[row.name] ? '更换脚本' : '上传脚本'" @click="openUploadModal(row.id, row.name)">{{ scriptByRow[row.name] ? '更换脚本' : '上传脚本' }} →</button><span v-if="scriptByRow[row.name]?.stale" class="script-badge" :title="`脚本落后于 Schema ${scriptByRow[row.name].staleBehind} 版：新增/删除的属性不会生效，请更新脚本`">落后 {{ scriptByRow[row.name].staleBehind }} 版</span><span v-if="scriptByRow[row.name]?.lastRunStatus === 'failed'" class="script-badge script-badge--failed" :title="`上次运行失败：${scriptByRow[row.name].lastRunError || '未知错误'}`">上次失败</span><button v-if="scriptByRow[row.name]" type="button" class="schema-action-link" @click="openViewModal(row.id, row.name)">查看脚本 →</button><button type="button" class="schema-action-link" :disabled="!row.schema.canManageProperties" :title="row.schema.canManageProperties ? '维护来源表绑定（平台喂数抽取的读取源）' : (row.schema.isSystem ? '系统 Schema 仅管理员可维护来源表' : '只有创建者或管理员可维护来源表')" @click="openSourcesModal(row.schema)">来源表</button><button type="button" class="schema-action-link" :disabled="!row.schema.canManageProperties" :title="row.schema.canManageProperties ? '维护属性（新增 / 删除）' : (row.schema.isSystem ? '系统 Schema 仅管理员可维护属性' : '只有创建者或管理员可维护属性')" @click="openPropertyModal(row.schema)">属性管理</button><button type="button" class="schema-action-link schema-action-link--danger" :title="row.schema.canDelete ? '删除该 Schema' : '系统内置，不可删除'" :disabled="!row.schema.canDelete" @click="openDeleteModal(row.schema)">删除</button></div></td></tr><tr v-if="expandedPropertyRows.has(row.id)" class="schema-prop-detail-row"><td :colspan="7"><div class="prop-detail"><span v-for="p in row.schema.properties" :key="p.name" class="prop-detail__item"><code>{{ p.name }}</code><em>{{ p.dataType }}</em><b v-if="p.required">必填</b><b v-if="p.locked" class="prop-detail__locked">🔒 公共</b></span></div></td></tr></template></tbody></table></div>

      <!-- 版本记录（已隐藏）
      <div v-else class="schema-table-wrap schema-version-table"><table><thead><tr><th>版本</th><th>状态</th><th>发布时间</th><th>实体范围</th><th>关系范围</th><th>变更内容</th><th>发布人</th><th>操作</th></tr></thead><tbody><tr v-for="row in schemaVersions" :key="row.version"><td><code>{{ row.version }}</code></td><td><span :class="row.status === '当前版本' ? 'core' : 'support'">{{ row.status }}</span></td><td>{{ row.time }}</td><td>{{ row.entities }}</td><td>{{ row.relations }}</td><td>{{ row.change }}</td><td>{{ row.publisher }}</td><td><div class="schema-version-actions"><button type="button" @click="schemaVersionMessage = `已打开 ${row.version} 的完整变更清单。`">变更详情</button><button v-if="row.status !== '当前版本'" class="danger" type="button" @click="schemaVersionMessage = `已创建回退至 ${row.version} 的申请，通过影响分析与审批后才会执行。`">申请回退</button></div></td></tr></tbody></table></div>
      -->
      </div>
    </section>

    <Teleport to="body">
      <div v-if="modalOpen" class="schema-modal schema-create-modal">
        <button class="schema-modal__mask" type="button" @click="modalOpen = false"></button>
        <aside class="schema-modal__panel schema-create-panel">
          <header><h2>新增{{ activeTab }}</h2><button type="button" @click="modalOpen = false">×</button></header>
          <a-form ref="createFormRef" :model="createForm" :rules="createFormRules" class="schema-modal__body schema-create-body" layout="vertical">
            <a-form-item class="create-field create-field--full" field="graphSpace" label="图空间" label-component="div" required>
              <a-select
                v-model="createForm.graphSpace"
                class="schema-create-select"
                placeholder="选择目标图空间"
                popup-container=".schema-create-modal"
                :scrollbar="false"
              >
                <a-option v-for="s in graphSpaces" :key="s" :value="s">{{ s }}</a-option>
              </a-select>
            </a-form-item>

            <div class="create-row">
              <a-form-item class="create-field" field="name" :label="isRelationTab() ? '关系英文名' : '实体名'" required>
                <input v-model="createForm.name" class="create-text-input" :maxlength="SCHEMA_ENTITY_NAME_RULE.max" :placeholder="isRelationTab() ? 'USES_TECHNOLOGY' : 'Gadget'" />
              </a-form-item>
              <a-form-item class="create-field" field="label" label="中文名" required>
                <input v-model="createForm.label" class="create-text-input" :maxlength="SCHEMA_LABEL_RULE.max" placeholder="如：技术" />
              </a-form-item>
            </div>

            <div v-if="isRelationTab()" class="create-row">
              <a-form-item class="create-field" field="sourceEntityId" label="起点实体" label-component="div" required>
                <a-select v-model="createForm.sourceEntityId" class="schema-select" placeholder="请选择" popup-container=".schema-create-modal" :scrollbar="false">
                  <a-option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}（{{ e.label }}）</a-option>
                  <template #empty>当前图空间暂无实体 Schema，请先新增实体</template>
                </a-select>
              </a-form-item>
              <a-form-item class="create-field" field="targetEntityId" label="终点实体" label-component="div" required>
                <a-select v-model="createForm.targetEntityId" class="schema-select" placeholder="请选择" popup-container=".schema-create-modal" :scrollbar="false">
                  <a-option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}（{{ e.label }}）</a-option>
                  <template #empty>当前图空间暂无实体 Schema，请先新增实体</template>
                </a-select>
              </a-form-item>
            </div>

            <a-form-item class="create-field create-field--full" field="description" label="说明">
              <a-textarea v-model="createForm.description" class="schema-description-textarea" :max-length="SCHEMA_DESC_RULE.max" show-word-limit :auto-size="{ minRows: 3, maxRows: 5 }" />
            </a-form-item>
            <a-form-item class="create-props" field="properties" required label-component="div">
              <template #label>
                <div class="create-props__head">
                  <span>属性列表</span>
                  <button type="button" class="create-props__add" @click.stop="addProperty">＋ 添加属性</button>
                </div>
              </template>
              <div class="create-prop-list">
                <div
                v-for="(p, i) in createForm.properties"
                :key="i"
                class="create-prop-row"
                :class="{ 'create-prop-row--has-length': p.dataType === 'fixed_string', 'create-prop-row--locked': p.locked }"
              >
                <a-form-item class="prop-name-field" :field="`properties.${i}.name`" :rules="[{ required: true, message: '请输入属性名称' }, { validator: validatePropName }]" hide-label>
                  <input v-model="p.name" :maxlength="PROP_NAME_RULE.max" placeholder="属性名" class="prop-name" :disabled="p.locked" :title="p.locked ? '公共必选属性，不可修改' : undefined" />
                </a-form-item>
                <template v-if="p.locked">
                  <span class="prop-locked-type">string</span>
                  <span class="prop-locked-required">必填 🔒</span>
                </template>
                <template v-else>
                  <a-select v-model="p.dataType" class="schema-select prop-type" popup-container=".schema-create-modal" :scrollbar="false">
                    <a-option v-for="t in PROPERTY_TYPES" :key="t" :value="t">{{ t }}</a-option>
                  </a-select>
                  <input v-if="p.dataType === 'fixed_string'" :value="p.length" type="text" inputmode="numeric" maxlength="64" class="prop-len" :class="{ 'prop-len--invalid': fixedLengthInvalid(p) }" :title="validateFixedLength(p.length) || undefined" placeholder="1~1024" @input="onLengthInput(p, $event)" />
                  <a-checkbox v-model="p.required" class="prop-required">必填</a-checkbox>
                  <button type="button" class="prop-remove" @click="removeProperty(i)" title="删除">×</button>
                </template>
                </div>
              </div>
            </a-form-item>

            <div class="create-sources">
              <div class="create-sources__head">
                <span>来源表（可选）</span>
                <button type="button" class="create-sources__add" @click="addSourceBinding">＋ 绑定来源表</button>
                <span class="create-sources__hint">绑定后可在行级触发「平台喂数」抽取：按时间列水位分批读取来源表 → 脚本转换 → 写入图谱</span>
              </div>
              <SourceBindings v-model="createForm.sources" :show-add-button="false" />
            </div>

            <div class="create-ddl">
              <span class="create-ddl__label">nGQL 预览（创建时将执行）</span>
              <pre class="create-ddl__pre">{{ createDdlPreview }}</pre>
              <p v-if="confirming" class="create-ddl__confirm">请确认上述 DDL 将在图空间执行，点击「确认创建」提交。</p>
            </div>
          </a-form>
          <footer>
            <button type="button" @click="modalOpen = false">取消</button>
            <button v-if="confirming" type="button" @click="confirming = false">返回修改</button>
            <button type="button" class="primary" :disabled="creating" @click="saveItem">{{ creating ? '创建中...' : confirming ? '确认创建' : '预览并创建' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="deleteModalOpen" class="schema-modal schema-delete-modal">
        <button class="schema-modal__mask" type="button" @click="deleteModalOpen = false"></button>
        <aside class="schema-modal__panel schema-delete-panel">
          <header><h2>删除 Schema</h2><button type="button" @click="deleteModalOpen = false">×</button></header>
          <div class="schema-modal__body">
            <p class="schema-delete-text">确认删除 <b>{{ deleteTarget?.label || deleteTarget?.name }}</b>（<code>{{ deleteTarget?.name }}</code>）？</p>
            <p class="schema-delete-note">将删除目录记录与关联脚本；如 DDL 已执行，图库中的 TAG/EDGE 不会被 DROP。</p>
          </div>
          <footer>
            <button type="button" @click="deleteModalOpen = false">取消</button>
            <button type="button" class="danger" :disabled="deleting" @click="confirmDelete">{{ deleting ? '删除中...' : '确认删除' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="propertyModalOpen" class="schema-modal property-modal">
        <button class="schema-modal__mask" type="button" @click="closePropertyModal"></button>
        <aside class="schema-modal__panel property-panel">
          <header><h2>属性管理 · {{ propertyTarget?.label || propertyTarget?.name }}</h2><button type="button" @click="closePropertyModal">×</button></header>
          <div class="schema-modal__body property-body">
            <div class="property-section">
              <div class="property-section__head"><strong>现有属性</strong><span>{{ propertyTarget?.properties.length || 0 }} 个</span></div>
              <div class="property-table">
                <div class="property-table__row property-table__row--head">
                  <span>属性名</span><span>类型</span><span>必填</span><span>操作</span>
                </div>
                <div v-for="p in propertyTarget?.properties || []" :key="p.name" class="property-table__row" :class="{ 'property-table__row--locked': p.locked }">
                  <span class="property-table__name"><code>{{ p.name }}</code><b v-if="p.locked" class="property-table__lock" title="公共必选属性，不可删除">🔒</b></span>
                  <span class="property-table__type">{{ p.dataType }}</span>
                  <span>{{ p.required ? '是' : '否' }}</span>
                  <span>
                    <button v-if="!p.locked" type="button" class="schema-action-link schema-action-link--danger" @click="requestDeleteProperty(p)">删除</button>
                    <span v-else class="property-table__locked-note">公共属性</span>
                  </span>
                </div>
              </div>
            </div>
            <div class="property-section">
              <div class="property-section__head"><strong>新增属性</strong><span>新增后在图库执行 ALTER ADD（可空列）</span></div>
              <div class="property-add-form">
                <input v-model="propertyForm.name" :maxlength="PROP_NAME_RULE.max" placeholder="属性名（字母/数字/下划线）" class="property-add-form__name" />
                <a-select v-model="propertyForm.dataType" class="property-add-form__type" popup-container=".property-modal" :scrollbar="false">
                  <a-option v-for="t in PROPERTY_TYPES" :key="t" :value="t">{{ t }}</a-option>
                </a-select>
                <input v-if="propertyForm.dataType === 'fixed_string'" :value="propertyForm.length" type="text" inputmode="numeric" maxlength="64" class="property-add-form__len" :class="{ 'property-add-form__len--invalid': propertyLengthInvalid }" :title="propertyLengthError || undefined" placeholder="1~1024" @input="onPropertyLengthInput" />
                <label class="property-add-form__required"><input v-model="propertyForm.required" type="checkbox" />必填</label>
                <button type="button" class="primary" :disabled="propertySaving" @click="submitAddProperty">{{ propertySaving ? '新增中...' : '＋ 新增属性' }}</button>
              </div>
            </div>
          </div>
          <footer>
            <button type="button" @click="closePropertyModal">关闭</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="propertyDeleteConfirmOpen && propertyDeleteTarget" class="schema-modal property-delete-modal">
        <button class="schema-modal__mask" type="button" @click="propertyDeleteConfirmOpen = false"></button>
        <aside class="schema-modal__panel schema-delete-panel">
          <header><h2>删除属性</h2><button type="button" @click="propertyDeleteConfirmOpen = false">×</button></header>
          <div class="schema-modal__body">
            <p class="schema-delete-text">确认删除属性 <b><code>{{ propertyDeleteTarget.name }}</code></b>（{{ propertyTarget?.label || propertyTarget?.name }}）？<b class="danger-text">此操作不可逆。</b></p>
            <p class="schema-delete-note">将删除图库中该属性列及其全部数据（ALTER ... DROP），并从 Schema 目录移除；如有运行中的抽取任务会被拦截，请先到任务中心停止。</p>
          </div>
          <footer>
            <button type="button" @click="propertyDeleteConfirmOpen = false">取消</button>
            <button type="button" class="danger" :disabled="propertyDeleting" @click="confirmDeleteProperty">{{ propertyDeleting ? '删除中...' : '确认删除（不可逆）' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="sourcesModalOpen" class="schema-modal sources-modal">
        <button class="schema-modal__mask" type="button" @click="sourcesModalOpen = false"></button>
        <aside class="schema-modal__panel sources-panel">
          <header><h2>来源表 · {{ sourcesTarget?.label || sourcesTarget?.name }}</h2><button type="button" @click="sourcesModalOpen = false">×</button></header>
          <div class="schema-modal__body">
            <p class="sources-note">绑定来源表后，可通过「触发抽取」让平台按各表独立的时间列水位分批读取行数据交给脚本转换并写入图谱；每张表可独立并行推进。「回填历史数据」会清空全部来源水位后全量重跑（新属性对历史数据的补齐需脚本先覆盖该属性）。</p>
            <SourceBindings v-model="sourcesForm" />
          </div>
          <footer>
            <button type="button" @click="sourcesModalOpen = false">取消</button>
            <button type="button" :disabled="sourcesSaving || extracting" @click="saveSources">{{ sourcesSaving ? '保存中...' : '仅保存绑定' }}</button>
            <button type="button" class="primary" :disabled="sourcesSaving || extracting" @click="triggerExtractionFromSources">{{ extracting ? '抽取中...' : '保存并触发抽取' }}</button>
            <button type="button" :disabled="sourcesSaving || extracting || backfilling" @click="requestBackfill">{{ backfilling ? '回填中...' : '回填历史数据' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="backfillConfirmOpen" class="schema-modal backfill-confirm-modal">
        <button class="schema-modal__mask" type="button" @click="backfillConfirmOpen = false"></button>
        <aside class="schema-modal__panel schema-delete-panel">
          <header><h2>回填历史数据</h2><button type="button" @click="backfillConfirmOpen = false">×</button></header>
          <div class="schema-modal__body">
            <p class="schema-delete-text">当前脚本未覆盖最新属性（落后 {{ sourcesTarget?.script?.staleBehind || 1 }} 版），回填可能无效。</p>
            <p class="schema-delete-note">脚本不产出新增属性，全量重跑后新列仍为 NULL。建议先更新脚本（更新后角标消失）再回填；确认仍要回填请点击「仍要回填」。</p>
          </div>
          <footer>
            <button type="button" @click="backfillConfirmOpen = false">取消</button>
            <button type="button" class="danger" :disabled="backfilling" @click="runBackfill(true)">{{ backfilling ? '回填中...' : '仍要回填' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="propertyExtractConfirmOpen" class="schema-modal property-extract-modal">
        <button class="schema-modal__mask" type="button" @click="propertyExtractConfirmOpen = false"></button>
        <aside class="schema-modal__panel schema-delete-panel">
          <header><h2>触发重新抽取</h2><button type="button" @click="propertyExtractConfirmOpen = false">×</button></header>
          <div class="schema-modal__body">
            <p class="schema-delete-text">Schema 属性已变更，是否立即触发重新抽取？</p>
            <p class="schema-delete-note">本次抽取按时间列水位只处理增量数据：新增属性对历史数据不生效（留 NULL）、已删属性不再写入。如需为历史数据补齐新属性，请到「来源表 → 回填历史数据」全量重跑。</p>
          </div>
          <footer>
            <button type="button" @click="propertyExtractConfirmOpen = false">稍后再说</button>
            <button type="button" class="primary" :disabled="extracting" @click="confirmTriggerExtraction">{{ extracting ? '触发中...' : '立即抽取' }}</button>
          </footer>
        </aside>
      </div>
    </Teleport>

    <input ref="uploadFileInput" type="file" accept=".py" hidden @change="onUploadFileChosen" />    <Teleport to="body">
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
.schema-page{display:flex;height:100%;min-height:0;overflow:hidden;padding-bottom:2px;color:#142443;flex-direction:column}.schema-flow{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));margin-bottom:12px;padding:12px;border:1px solid #c5d9f6;border-radius:8px;background:#fff}.schema-flow>div{position:relative;display:flex;align-items:center;gap:7px;min-width:0;padding:4px 15px 4px 5px}.schema-flow i{display:grid;flex:0 0 auto;place-items:center;width:23px;height:23px;border-radius:50%;background:#eaf2ff;color:#165dff;font-size:10px;font-style:normal}.schema-flow span{color:#40536f;font-size:10px;line-height:15px}.schema-flow b{position:absolute;right:2px;color:#9bb5d9}.schema-shell{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #bcd4f7;border-radius:9px;background:#fff;box-shadow:0 10px 24px rgba(48,105,194,.08);flex-direction:column}.schema-tabs{display:flex;flex:0 0 auto;overflow:auto;padding:0 12px;border-bottom:1px solid #dce8f8}.schema-tabs button{padding:12px 15px;border:0;border-bottom:2px solid transparent;background:transparent;color:#566985;white-space:nowrap;cursor:pointer}.schema-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.schema-toolbar{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:14px;padding:10px 13px;border-bottom:1px solid #e3ebf6;background:#f8fbff}.schema-toolbar>div{display:flex;align-items:center;gap:10px}.schema-toolbar strong{font-size:13px}.schema-toolbar>div span{color:#7b8ba3;font-size:10px}.schema-toolbar label{display:flex;align-items:center;gap:6px;width:270px;padding:0 9px;border:1px solid #c7d8ef;border-radius:5px;background:#fff}.schema-toolbar input{width:100%;height:30px;border:0;outline:0;font-size:11px}.schema-table-wrap{flex:1;min-height:0;max-height:none;overflow:auto}.schema-table-wrap table,.trace-layout table{width:100%;border-collapse:collapse;font-size:11px}.schema-table-wrap th,.schema-table-wrap td,.trace-layout td{padding:11px 13px;border-bottom:1px solid #e5edf8;text-align:left;line-height:17px;vertical-align:top}.schema-table-wrap th{position:sticky;z-index:2;top:0;background:#f1f6fc;color:#5e6f88;white-space:nowrap}.schema-table-wrap td{color:#344763}.schema-table-wrap td:nth-child(5),.schema-table-wrap td:nth-child(6){max-width:330px}.schema-table-wrap code,.trace-layout code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;white-space:nowrap}.core,.support,.evidence,.auto,.review{display:inline-flex;padding:2px 7px;border-radius:999px;background:#e9f8ef;color:#067647;font-size:9px;white-space:nowrap}.support{background:#f0f2f5;color:#5e6b7e}.evidence{background:#f0edff;color:#6941c6}.auto{white-space:normal}.review{background:#fff3df;color:#b54708;white-space:normal}.arrow{margin:0 5px;color:#8ba2c2}.candidate-layout{display:grid;flex:1;min-height:0;grid-template-columns:minmax(0,1fr) 245px}.candidate-layout>.schema-table-wrap{grid-column:1}.candidate-note{grid-column:1/-1;padding:10px 13px;border-bottom:1px solid #dce8f8;background:#f3f8ff}.candidate-note strong{font-size:12px}.candidate-note p{margin:3px 0 0;color:#657690;font-size:10px}.mention-fields{grid-column:2;grid-row:2;padding:13px;border-left:1px solid #e0e9f5;background:#fafcff}.mention-fields strong{display:block;margin-bottom:10px;font-size:12px}.mention-fields span{display:inline-flex;margin:0 5px 6px 0;padding:3px 6px;border-radius:4px;background:#edf4ff;color:#315b95;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}.trace-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:12px;background:#f8fbff}.trace-layout section{overflow:hidden;border:1px solid #d5e3f5;border-radius:7px;background:#fff}.trace-layout header{display:flex;align-items:flex-start;justify-content:space-between;padding:13px;border-bottom:1px solid #e3ebf6}.trace-layout h2{margin:0;font-size:13px}.trace-layout p{margin:3px 0 0;color:#7b899e;font-size:10px}.trace-layout header>span{color:#165dff;font-size:10px}.trace-layout table{display:block;max-height:390px;overflow:auto}.trace-layout tbody,.trace-layout tr{display:table;width:100%;table-layout:fixed}.trace-layout td:first-child{width:160px}@media(max-width:1250px){.schema-flow{grid-template-columns:repeat(4,1fr)}.schema-flow b{display:none}}@media(max-width:900px){.trace-layout{grid-template-columns:1fr}.candidate-layout{display:block}.mention-fields{border-top:1px solid #e0e9f5;border-left:0}}

/* 拓扑图例（替代原顶部统计卡片） */
.schema-topology-legend{display:flex;align-items:center;gap:16px}
.legend-item{display:inline-flex;align-items:center;gap:6px;color:#344763;font-size:11px;white-space:nowrap}
.legend-node{width:10px;height:10px;border-radius:50%;background:#165dff}
.legend-edge{position:relative;width:22px;height:0;border-top:2px solid #12b76a}

/* Layout refinements for wide management screens. */
.schema-page{box-sizing:border-box;padding:2px 2px 18px}

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
.schema-version-message{margin:0;padding:9px 13px;border-bottom:1px solid #b7d0f5;background:#eef5ff;color:#344f7a;font-size:11px}
.schema-version-table{max-height:470px}.schema-version-table td:nth-child(6){min-width:280px}.schema-version-actions{display:flex;gap:6px}.schema-version-actions button{padding:3px 7px;border:1px solid #bdd0ea;border-radius:4px;background:#fff;color:#165dff;font-size:9px;white-space:nowrap;cursor:pointer}.schema-version-actions button.danger{border-color:#f6b9b4;color:#b42318}

.schema-toolbar__actions{display:flex;align-items:center;gap:10px}
.schema-tabs>.schema-toolbar__actions{min-width:0;margin-left:auto}.schema-tabs .space-picker{flex:0 0 auto}
.space-picker{display:flex;align-items:center;gap:8px;font-size:12px;color:#4e5969}
.prop-len--invalid,.property-add-form__len--invalid{border-color:#e5484d!important;background:#fff3f3!important}
.schema-toolbar .primary{height:32px;padding:0 14px;border:0;border-radius:6px;background:#165dff;color:#fff;font-size:13px;cursor:pointer}
.schema-toolbar .primary:hover{background:#0e4ed8}
.schema-actions{white-space:nowrap}
.schema-actions__inner{display:flex;gap:8px;align-items:center}
.schema-action-link{border:0;background:transparent;color:#165dff;font-size:11px;line-height:17px;padding:0;cursor:pointer}
.schema-action-link:hover{text-decoration:underline}
.schema-action-link:disabled{color:#a9b4c6;cursor:not-allowed;text-decoration:none}
.schema-action-link--danger{color:#e5484d;padding-left:10px}
.schema-action-link--danger:hover:not(:disabled){color:#b42318}
.schema-props-cell{max-width:360px}
.prop-chips{display:flex;flex-wrap:wrap;gap:4px}
.prop-chip{display:inline-flex;max-width:160px;overflow:hidden;padding:1px 8px;border:1px solid #d6e2f5;border-radius:999px;background:#f4f8ff;color:#3a5686;font-size:11px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}
.prop-chip--more{border-color:#bcd4f7;background:#eaf2ff;color:#165dff;cursor:pointer}
.prop-chip--more:hover{background:#dcebff}
.schema-prop-detail-row>td{padding:8px 16px;background:#f9fbff}
.prop-detail{display:flex;flex-wrap:wrap;gap:8px 18px}
.prop-detail__item{display:inline-flex;align-items:center;gap:6px;color:#4e5969;font-size:12px;line-height:20px;white-space:nowrap}
.prop-detail__item code{padding:1px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px}
.prop-detail__item em{color:#86909c;font-size:11px;font-style:normal;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.prop-detail__item b{padding:0 6px;border-radius:999px;background:#f2f3f5;color:#4e5969;font-size:10px;font-weight:400}
.prop-detail__locked{background:#fff7e8;color:#b54708}
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
.schema-modal__panel footer button.danger{background:#e5484d;color:#fff;border-color:#e5484d}
.schema-modal__panel footer button:disabled{opacity:.6;cursor:not-allowed}

/* 删除确认弹窗 */
.schema-delete-panel{max-width:420px}
.schema-delete-text{margin:0;font-size:13px;line-height:22px;color:#1d2129}
.schema-delete-note{margin:0;font-size:11px;line-height:18px;color:#86909c}
.danger-text{color:#e5484d}

/* 脚本双信号角标：落后于 Schema / 上次运行失败 */
.script-badge{display:inline-flex;align-items:center;padding:1px 7px;border-radius:999px;background:#fff7e8;color:#b54708;font-size:10px;line-height:16px;white-space:nowrap}
.script-badge--failed{background:#fef3f2;color:#b42318}

/* 属性管理弹窗 */
.property-panel{width:min(640px,100%)}
.property-body{gap:18px}
.property-section{display:flex;flex-direction:column;gap:8px}
.property-section__head{display:flex;align-items:baseline;justify-content:space-between}
.property-section__head strong{font-size:13px;color:#1d2129}
.property-section__head span{font-size:11px;color:#86909c}
.property-table{display:flex;flex-direction:column;border:1px solid #e5e6eb;border-radius:6px;overflow:hidden}
.property-table__row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(90px,1fr) 60px 90px;gap:8px;align-items:center;padding:7px 12px;border-bottom:1px solid #f2f3f5;font-size:12px;color:#4e5969}
.property-table__row:last-child{border-bottom:0}
.property-table__row--head{background:#f7f8fa;font-size:11px;color:#86909c}
.property-table__row--locked{background:#fffbf4}
.property-table__name{display:flex;align-items:center;gap:6px;min-width:0}
.property-table__name code{overflow:hidden;padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px;text-overflow:ellipsis;white-space:nowrap}
.property-table__lock{font-size:11px;font-weight:400}
.property-table__type{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;color:#86909c}
.property-table__locked-note{font-size:11px;color:#b54708}
.property-add-form{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(110px,1fr) auto auto;gap:8px;align-items:center}
.property-add-form__name,.property-add-form__len{height:32px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;color:#1d2129;background:#fff}
.property-add-form__name{box-sizing:border-box;width:100%}
.property-add-form__len{width:72px;grid-column:3}
.property-add-form__type{min-width:0}
.property-add-form__type :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:13px;line-height:22px}
.property-add-form__required{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#4e5969;white-space:nowrap}
.property-add-form__required input{margin:0}
.property-add-form .primary{height:32px;padding:0 14px;border:0;border-radius:4px;background:#165dff;color:#fff;font-size:13px;cursor:pointer;white-space:nowrap}
.property-add-form .primary:hover{background:#0e4ed8}
.property-add-form .primary:disabled{opacity:.6;cursor:not-allowed}

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
.schema-create-body{max-height:72vh;gap:16px}
.create-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.create-field{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#4e5969}
.create-field--full{grid-column:1/-1}
.create-text-input,.create-field textarea,.create-field select{height:32px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;color:#1d2129;background:#fff}
.create-field textarea{height:auto;padding:6px 8px;resize:vertical}
.create-field select{appearance:auto}
.create-props{display:flex;flex-direction:column;gap:8px}
.create-props__head{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#4e5969}
.create-props__add,.create-sources__add{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:120px;min-width:120px;height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#165dff;font-size:12px;white-space:nowrap;cursor:pointer}
.create-props__add:hover,.create-sources__add:hover{border-color:#165dff}
.create-prop-row{display:grid;grid-template-columns:1.4fr 1.2fr 0.6fr auto auto;gap:8px;align-items:center}
.prop-name,.prop-type,.prop-len{height:30px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:12px;color:#1d2129;background:#fff}
.prop-type{appearance:auto}
.prop-required{display:flex;align-items:center;gap:4px;font-size:11px;color:#4e5969;white-space:nowrap}
.prop-required input{margin:0}
.prop-remove{width:24px;height:24px;border:0;border-radius:4px;background:transparent;color:#e54848;font-size:16px;cursor:pointer}
.prop-remove:hover{background:#fff3f3}
.create-ddl{display:flex;flex-direction:column;gap:8px;margin-top:0}
.create-ddl__label{font-size:11px;color:#74849b}
.create-ddl__pre{margin:0;padding:10px 12px;max-height:140px;overflow:auto;background:#0d1117;border-radius:6px;color:#c9d1d9;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;line-height:18px;white-space:pre-wrap;word-break:break-all}
.create-ddl__confirm{margin:6px 0 0;color:#b54708;font-size:11px;line-height:16px}
.create-sources{display:flex;flex-direction:column;gap:8px}
.create-sources__head{display:grid;align-items:center;grid-template-columns:minmax(0,1fr) auto;column-gap:8px;row-gap:4px;font-size:12px;color:#4e5969}
.create-sources__head>span:first-child,.create-ddl__label{color:#4e5969;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.create-sources__hint{grid-column:1/-1;color:#86909c;font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.sources-panel{width:min(760px,100%)}
.sources-note{margin:0;font-size:12px;line-height:20px;color:#86909c}
.schema-create-body>.create-field,.schema-create-body>.create-props,.create-row>.create-field{margin-bottom:0;gap:0}.schema-create-body>.create-props{gap:0}.create-ddl{margin-top:0;gap:8px}.create-ddl__confirm{margin:0}
</style>
<style scoped>
/* DESIGN_RULES: Schema management page contract. */
.schema-page{padding:0;color:#1d2129}
.schema-shell{border-color:#e5e6eb;border-radius:6px;box-shadow:none}
.schema-tabs{display:flex;min-height:48px;padding:8px 16px;align-items:center;justify-content:space-between;gap:16px}.schema-tabs__items{display:flex;align-self:stretch;overflow:auto}.schema-tabs button{height:32px;padding:0 16px;font-size:14px;line-height:22px;font-weight:400}.schema-tabs button.active{font-weight:500}
.schema-toolbar{min-height:48px;gap:16px;padding:8px 16px;background:#fff}.schema-toolbar>div,.schema-toolbar__actions{gap:16px}
.schema-toolbar strong{font-size:16px;line-height:24px;font-weight:600}.schema-toolbar>div span{font-size:12px;line-height:20px}
.schema-toolbar label{gap:8px;width:280px;height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px}.schema-toolbar input{height:30px;padding:0!important;font-size:14px;line-height:22px}
.schema-toolbar .primary,.schema-tabs .primary{height:32px;padding:0 16px;border:0;border-radius:4px;background:#165dff;color:#fff;font-size:14px;line-height:22px;white-space:nowrap;cursor:pointer}.schema-tabs .primary:hover{background:#4080ff}.schema-tabs .primary:active{background:#0e42d2}
.schema-table-wrap table,.trace-layout table{font-size:14px;line-height:22px}.schema-table-wrap th,.schema-table-wrap td,.trace-layout td{height:40px;padding:0 16px;line-height:22px;vertical-align:middle}
.schema-table-wrap th{background:#f7f8fa;color:#1d2129;font-weight:500}.schema-action-link{font-size:14px;line-height:22px}
.core,.support,.evidence,.auto,.review{gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}
.core::before,.support::before,.evidence::before,.auto::before,.review::before{display:block;flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
.trace-layout{gap:16px;padding:16px;background:#f7f8fa}.trace-card,.trace-layout section{border-color:#e5e6eb;border-radius:6px;box-shadow:none}
.trace-card>header{min-height:56px;padding:8px 16px;background:#f7f8fa}.trace-card h2{font-size:16px;line-height:24px;font-weight:600}.trace-card p,.trace-card dd,.trace-layout>aside span{font-size:12px;line-height:20px}
.schema-modal__panel{width:min(560px,100%)}.schema-create-panel{display:grid;box-sizing:border-box;width:min(640px,calc(100vw - 48px));height:auto;max-height:calc(100vh - 48px);overflow:hidden;grid-template-rows:56px minmax(0,1fr) 64px}.schema-modal__panel header{height:56px;box-sizing:border-box;padding:0 24px}.schema-modal__panel header h2{font-size:16px;line-height:24px}.schema-modal__panel header button{width:32px;height:32px}
.schema-modal__body{gap:16px;padding:24px}.schema-create-body{min-height:0;max-height:none;overflow-x:hidden;overflow-y:auto}.schema-modal__body label,.create-field{gap:8px;font-size:14px;line-height:22px}.create-row{gap:16px}
.create-row>.create-field{min-width:0}.create-row>.create-field :deep(.arco-form-item-wrapper-col),.create-row>.create-field :deep(.arco-form-item-content-wrapper),.create-row>.create-field :deep(.arco-form-item-content){box-sizing:border-box;width:100%;min-width:0}.create-text-input,.create-field textarea,.create-field select{box-sizing:border-box;width:100%;height:32px;padding:0 12px;font-size:14px;line-height:22px;appearance:none}
.create-field :deep(.arco-textarea-wrapper){box-sizing:border-box;width:100%;min-height:80px;border:1px solid #e5e6eb;border-radius:4px;background:#fff!important}.create-field :deep(.arco-textarea){box-sizing:border-box;width:100%;min-height:78px;padding:8px 12px 28px;background:#fff!important;color:#1d2129;font-size:14px;line-height:22px}.create-field :deep(.arco-textarea-word-limit){right:12px;bottom:6px;color:#86909c;font-size:12px;line-height:20px}.create-field :deep(.arco-textarea-wrapper:hover){border-color:#4080ff}.create-field :deep(.arco-textarea-wrapper.arco-textarea-focus){border-color:#165dff;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.create-props{gap:16px}.create-props :deep(.arco-form-item-label-col),.create-props :deep(.arco-form-item-label){box-sizing:border-box;width:100%}.create-props :deep(.arco-form-item-label){display:flex;align-items:center}.create-prop-list{display:grid;width:100%;gap:16px}.create-props :deep(.arco-form-item-content-flex){width:100%}.create-props__head{display:flex;width:100%;align-items:center;justify-content:space-between;font-size:14px;line-height:22px}.create-props__add{height:28px;font-size:14px}.create-prop-row{gap:8px}
.prop-name,.prop-type,.prop-len{height:32px;font-size:14px;appearance:none}.prop-required{font-size:14px;line-height:22px}
.create-prop-row{grid-template-columns:minmax(0,1.4fr) minmax(120px,1.2fr) auto 24px;align-items:center;column-gap:16px;row-gap:8px}
.create-prop-row--has-length{grid-template-columns:minmax(0,1.4fr) minmax(120px,1.2fr) 72px auto 24px}
.prop-name-field{grid-column:1;min-width:0;margin:0!important;align-self:center}
.prop-name-field :deep(.arco-form-item-wrapper-col),.prop-name-field :deep(.arco-form-item-content-wrapper),.prop-name-field :deep(.arco-form-item-content){box-sizing:border-box;width:100%;min-width:0}
.prop-name{box-sizing:border-box;width:100%;height:32px}
.prop-type{grid-column:2;box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0!important;border:0!important;background:transparent}
.prop-type :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:14px;line-height:22px}
.prop-type :deep(.arco-select-view-input){height:100%!important;min-height:0!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
.prop-type :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;outline:0!important;opacity:0!important;box-shadow:none!important;pointer-events:none!important}
:deep(.prop-type.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb!important;border-radius:4px;background:#fff!important}:deep(.prop-type.arco-select-view:hover){border-color:#c9cdd4!important}:deep(.prop-type.arco-select-view-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
:deep(.prop-type.arco-select-view) .arco-select-view-value,:deep(.prop-type.arco-select-view) .arco-select-view-input{background:#fff!important}
.prop-len{grid-column:3;box-sizing:border-box;width:72px;height:32px}
.prop-required{display:inline-flex!important;grid-column:3;flex-direction:row!important;align-items:center!important;justify-self:start;height:32px;margin:0!important;gap:8px!important;align-self:center;white-space:nowrap}
.create-prop-row--has-length .prop-required{grid-column:4}
.prop-remove{grid-column:4;justify-self:end;align-self:center}
.create-prop-row--has-length .prop-remove{grid-column:5}
.create-prop-row--locked .prop-name{background:#f7f8fa;color:#4e5969;cursor:not-allowed}
.prop-locked-type{grid-column:2;align-self:center;color:#86909c;font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.prop-locked-required{grid-column:3;align-self:center;color:#4e5969;font-size:12px;white-space:nowrap}
.schema-modal__panel footer{height:64px;box-sizing:border-box;gap:16px;padding:0 24px}.schema-create-panel footer{align-items:center;padding:16px 24px}.schema-modal__panel footer button{height:32px;padding:0 16px;font-size:14px;line-height:22px}
:is(.schema-llm-select){box-sizing:border-box;width:100%;min-width:0}
:is(.schema-llm-select) :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:14px;line-height:22px}
:is(.schema-llm-select) :deep(.arco-select-view-input){height:100%!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
:is(.schema-llm-select) :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;outline:0!important;opacity:0!important;pointer-events:none!important}
:is(.schema-llm-select) :deep(.arco-select-view-value){min-width:0;overflow:hidden;line-height:30px;text-overflow:ellipsis;white-space:nowrap}
:deep(.schema-llm-select.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb!important;border-radius:4px;background:#fff!important}:deep(.schema-llm-select.arco-select-view:hover){border-color:#c9cdd4!important}:deep(.schema-llm-select.arco-select-view-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
:deep(.schema-llm-select.arco-select-view) .arco-select-view-value,:deep(.schema-llm-select.arco-select-view) .arco-select-view-input{background:#fff!important}
:is(.schema-llm-select) :deep(.arco-select-view-focus){border-color:#165dff;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.schema-search-input.arco-input-wrapper{box-sizing:border-box;width:280px;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.schema-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.schema-search-input.arco-input-wrapper:focus-within,.schema-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.schema-search-input.arco-input-wrapper :deep(.arco-input-prefix){padding-right:8px;color:#4e5969}.schema-search-input.arco-input-focus :deep(.arco-input-prefix){color:#165dff}
.schema-search-input.arco-input-wrapper :deep(.arco-input-prefix svg){width:16px;height:16px;font-size:16px}
.schema-search-input.arco-input-wrapper :deep(.arco-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px;box-shadow:none!important;outline:none!important}
:is(.create-text-input,.prop-name,.prop-len){box-sizing:border-box;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#1d2129;font-size:14px;line-height:22px;outline:none;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}
:is(.create-text-input,.prop-name,.prop-len):hover{border-color:#4080ff}
:is(.create-text-input,.prop-name,.prop-len):focus{border-color:#165dff;outline:none;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
:is(.create-text-input,.prop-name,.prop-len):focus-visible{border-color:#165dff;outline:none;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
:deep(.schema-select.arco-select-view){display:inline-flex;box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;align-items:center}
:deep(.schema-select.arco-select-view:hover){border-color:#4080ff!important;background:#fff!important}
:deep(.schema-select.arco-select-view:focus-within),:deep(.schema-select.arco-select-view-focus){border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
:deep(.schema-select.arco-select-view .arco-select-view-input){width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
:deep(.schema-select.arco-select-view .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}
.schema-create-panel{font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;letter-spacing:0}
.schema-create-panel header h2{font-size:16px;line-height:24px;font-weight:600}.schema-create-panel header button{font-size:16px;line-height:16px;font-weight:400}
.schema-create-body,.schema-create-body :deep(.arco-form-item-label),.schema-create-body :deep(.arco-checkbox-label){font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.schema-create-body :is(.create-text-input,.prop-name,.prop-len),.schema-create-body :deep(.arco-textarea),.schema-create-body :deep(.arco-select-view-input),.schema-create-body :deep(.arco-select-view-value){font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.schema-create-body :deep(.arco-form-item-message),.schema-create-body :deep(.arco-textarea-word-limit){font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.schema-create-panel .create-props__head,.schema-create-panel .create-props__add,.schema-create-panel .create-sources__add,.schema-create-panel .prop-required{font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.schema-create-panel .prop-remove{font-size:16px;line-height:16px;font-weight:400}
.schema-create-panel .create-ddl__label{color:#4e5969;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}.schema-create-panel .create-ddl__confirm{font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.schema-create-panel .create-ddl__pre{font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.schema-create-panel footer button{font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
@media(max-width:900px){.schema-tabs{align-items:stretch;flex-direction:column}.schema-tabs__items{min-height:36px}.schema-toolbar__actions{justify-content:flex-end}.create-row{grid-template-columns:1fr}.create-field--full{grid-column:auto}}
.schema-create-body>.create-field,.create-row>.create-field{margin-bottom:0;gap:0}.schema-create-body>.create-props{margin-bottom:0}.create-ddl{margin-top:0;gap:8px}.create-ddl__confirm{margin:0}
/* Schema 拓扑总览 */
.schema-topology-shell{margin-bottom:16px;padding-bottom:0}
.schema-topology-canvas{height:260px;overflow:hidden;border-top:1px solid #e5e6eb;background: #fff;}
.schema-topology-canvas__empty{display:grid;place-items:center;height:100%;color:#86909c;font-size:12px}

/* Schema 管理页统一排版规范。 */
.schema-page,.schema-page :deep(*),.schema-modal,.schema-modal :deep(*){font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;letter-spacing:0}
.schema-page,.schema-modal{font-size:14px;line-height:22px;font-weight:400}
.schema-page :is(button,input,textarea,select),.schema-modal :is(button,input,textarea,select){font-family:inherit;letter-spacing:0}
.schema-toolbar strong,.trace-card h2,.trace-layout h2,.property-section__head strong,.schema-modal__panel header h2{font-size:16px;line-height:24px;font-weight:600}
.schema-tabs button,.schema-toolbar .primary,.schema-tabs .primary,.schema-action-link{font-size:14px;line-height:22px;font-weight:400}
.schema-tabs button.active{font-weight:500}
.space-picker,.space-picker>span{font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.schema-space-select :deep(.arco-select-view-input),.schema-space-select :deep(.arco-select-view-value),.schema-search-input :deep(.arco-input),.schema-llm-select :deep(.arco-select-view-input),.schema-llm-select :deep(.arco-select-view-value){font-size:14px!important;line-height:22px!important;font-weight:400;letter-spacing:0}
.schema-table-wrap table,.trace-layout table,.schema-table-wrap td,.trace-layout td{font-size:14px;line-height:22px;font-weight:400}
.schema-table-wrap th,.property-table__row--head{font-size:14px;line-height:22px;font-weight:500}
.schema-table-wrap td b{font-weight:400}
.legend-item,.schema-topology-canvas__empty,.schema-flow span,.schema-flow>header span,.candidate-note p,.mention-fields span,.trace-card p,.trace-card dd,.trace-card code,.trace-card>header b,.trace-layout header>span,.trace-layout>aside strong,.trace-layout>aside span{font-size:12px;line-height:20px;font-weight:400}
.prop-chip,.prop-detail__item,.prop-detail__item code,.prop-detail__item em,.prop-detail__item b,.script-badge{font-size:12px;line-height:20px;font-weight:400}
.schema-delete-text,.property-table__row,.property-table__name code,.property-table__lock,.property-table__type,.property-table__locked-note,.property-add-form__name,.property-add-form__len,.property-add-form__type :deep(.arco-select-view),.property-add-form__required,.property-add-form .primary,.upload-idle p,.upload-idle .primary,.upload-working__text strong,.upload-result strong,.view-loading,.view-error{font-size:14px;line-height:22px;font-weight:400}
.schema-delete-note,.property-section__head span,.upload-stage,.upload-message,.upload-result span,.upload-result__msg,.upload-result__issues,.script-pre code,.create-ddl__pre,.create-ddl__confirm,.create-sources__hint,.sources-note{font-size:12px;line-height:20px;font-weight:400}
.schema-modal__body label,.schema-modal__body input,.schema-modal__body textarea,.schema-modal__panel footer button,.create-field,.create-text-input,.create-field textarea,.create-field select,.create-props__head,.create-props__add,.prop-name,.prop-type,.prop-len,.prop-required{font-size:14px;line-height:22px;font-weight:400}
.schema-version-message{font-size:12px;line-height:20px;font-weight:400}
.schema-version-actions button{font-size:14px;line-height:22px;font-weight:400}
.candidate-note strong,.mention-fields strong,.schema-flow>header strong{font-size:16px;line-height:24px;font-weight:600}
.schema-flow li i,.trace-card>header i{font-size:12px;line-height:20px}

/* Schema 类型切换沿用科技专家同事关系页的摘要/实体分段按钮，并置于表格边框之外。 */
.schema-catalog{display:flex;flex:1;min-height:0;flex-direction:column;gap:12px}
.schema-table-shell{flex:1;min-height:0}
.schema-tabs{min-height:40px;padding:0;border-bottom:0;background:transparent;overflow:visible}
.schema-tabs__items{box-sizing:border-box;height:40px;padding:4px;border-radius:4px;background:#f2f3f5;align-self:auto;overflow:visible}
.schema-tabs__items button{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:88px;height:32px;padding:5px 16px;border:0;border-radius:4px;background:transparent;color:#4e5969;text-align:center}
.schema-tabs__items button+button{border-left:1px solid #c9cdd4}
.schema-tabs__items button.active{border-left-color:transparent;background:#fff;color:#165dff;font-weight:500}
.schema-tabs__items button.active+button{border-left-color:transparent}
.schema-tabs__items button:hover:not(.active){background:#fff;color:#165dff}
.schema-tabs__items button:focus-visible{outline:2px solid rgba(22,93,255,.28);outline-offset:1px}

/* 新增 Schema：图空间下拉框对齐“新建任务”的任务类型控件。 */
:deep(.schema-create-select.arco-select-view){display:inline-flex;box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;align-items:center}
:deep(.schema-create-select.arco-select-view:hover){border-color:#4080ff!important;background:#fff!important}
:deep(.schema-create-select.arco-select-view:focus-within),:deep(.schema-create-select.arco-select-view-focus){border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
:deep(.schema-create-select.arco-select-view .arco-select-view-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
:deep(.schema-create-select.arco-select-view .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important;pointer-events:none!important}
:deep(.schema-create-select.arco-select-view .arco-select-view-value),:deep(.schema-create-select.arco-select-view .arco-select-view-placeholder){min-width:0;overflow:hidden;background:transparent!important;font-size:14px;line-height:30px;text-overflow:ellipsis;white-space:nowrap}

/* 新增 Schema：说明文本框对齐“新建配置”的说明控件。 */
:deep(.schema-description-textarea.arco-textarea-wrapper){box-sizing:border-box;width:100%;height:auto;min-height:80px;max-height:none;border:1px solid #e5e6eb;border-radius:4px;background:#fff!important;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}
</style>
<style>
.app-workspace .schema-toolbar__actions .schema-search-input.arco-input-wrapper .arco-input{height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;outline:none!important}
.app-workspace .schema-tabs #schema-space-select.schema-space-select.arco-select-view{display:inline-flex;box-sizing:border-box;align-items:center;height:32px;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.app-workspace .schema-tabs #schema-space-select.schema-space-select.arco-select-view:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .schema-tabs #schema-space-select.schema-space-select.arco-select-view:focus-within,.app-workspace .schema-tabs #schema-space-select.schema-space-select.arco-select-view-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .schema-tabs #schema-space-select input.arco-select-view-input{box-sizing:border-box;width:100%;height:30px!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .schema-tabs #schema-space-select .arco-select-view-input-hidden{position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}
.app-workspace .schema-tabs #schema-space-select .arco-select-view-value{min-width:0;overflow:hidden;line-height:30px;text-overflow:ellipsis;white-space:nowrap}
.app-workspace .schema-tabs #schema-space-select :is(.arco-select-view-input,.arco-select-view-value){background:transparent!important}
</style>
