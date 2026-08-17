<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFormValidation, type Rules } from '../composables/use-form-validation'
import FormField from './form-field.vue'

export type ConstructionActionKey = 'entity' | 'relation' | 'property' | 'batch-audit' | 'rule-import'

interface ActionConfig {
  title: string
  submitLabel: string
}

const props = defineProps<{
  open: boolean
  action: ConstructionActionKey | null
}>()

const emit = defineEmits<{
  close: []
  success: [title: string]
}>()

const isSubmitting = ref(false)

const actionMap: Record<ConstructionActionKey, ActionConfig> = {
  entity: { title: '新增实体', submitLabel: '保存实体' },
  relation: { title: '新增关系', submitLabel: '保存关系' },
  property: { title: '新增属性', submitLabel: '保存属性' },
  'batch-audit': { title: '批量审核', submitLabel: '提交审核' },
  'rule-import': { title: '导入规则', submitLabel: '开始导入' },
}

const config = computed(() => (props.action ? actionMap[props.action] : null))

const entityForm = ref({
  name: '华南智能芯片有限公司',
  type: '科技企业',
  alias: '',
  batch: 'KG-INC-20260706-01',
})

const relationForm = ref({
  source: '张明远',
  target: '李佳宁',
  relation: '论文合作',
  confidence: '0.90',
})

const propertyForm = ref({
  object: '张明远',
  name: '论文数量',
  value: '132',
})

const auditRows = ref([
  { id: '1', name: '张明远 / Zhang Mingyuan', type: '实体合并', checked: true },
  { id: '2', name: '张明远 — 李佳宁', type: '关系审核', checked: true },
  { id: '3', name: '论文数量 128 → 132', type: '属性更新', checked: false },
])

const ruleImportForm = ref({
  fileName: '',
  ruleType: '实体消歧',
  mode: '增量导入',
})

const isAllAuditChecked = computed({
  get() {
    return auditRows.value.length > 0 && auditRows.value.every((row) => row.checked)
  },
  set(checked: boolean) {
    auditRows.value = auditRows.value.map((row) => ({ ...row, checked }))
  },
})

const activeForm = computed<Record<string, unknown>>(() => {
  switch (props.action) {
    case 'entity': return entityForm.value
    case 'relation': return relationForm.value
    case 'property': return propertyForm.value
    case 'rule-import': return ruleImportForm.value
    default: return {}
  }
})

const rules = computed<Rules>(() => {
  switch (props.action) {
    case 'entity':
      return { name: { required: '请填写实体名称' } } as Rules
    case 'relation':
      return {
        source: { required: '请填写源实体' },
        target: { required: '请填写目标实体' },
        confidence: {
          required: '请填写置信度',
          pattern: { regex: /^(0|1|0?\.\d+)$/, message: '置信度必须是 0-1 之间的数字' },
        },
      } as Rules
    case 'property':
      return {
        object: { required: '请填写对象' },
        name: { required: '请填写属性名' },
        value: { required: '请填写属性值' },
      } as Rules
    case 'rule-import':
      return { fileName: { required: '请选择规则文件' } } as Rules
    default:
      return {} as Rules
  }
})

const { visibleError, validate, touch, clearErrors } = useFormValidation(activeForm, rules)

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) {
      isSubmitting.value = false
      clearErrors()
    }
  },
)

async function handleSubmit() {
  if (!config.value) return
  if (!validate()) return
  isSubmitting.value = true
  await new Promise((resolve) => window.setTimeout(resolve, 420))
  isSubmitting.value = false
  emit('success', config.value.title)
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  ruleImportForm.value.fileName = input.files?.[0]?.name ?? ''
  touch('fileName')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open && config && action" class="kg-modal" @click.self="emit('close')">
      <section class="kg-modal__panel construction-action-modal" role="dialog" aria-modal="true" :aria-label="config.title">
        <header class="kg-modal__header">
          <h2>{{ config.title }}</h2>
          <button type="button" aria-label="关闭" @click="emit('close')">×</button>
        </header>

        <form class="construction-action-form" @submit.prevent="handleSubmit">
          <div class="construction-action-form__body">
            <template v-if="action === 'entity'">
              <FormField label="实体名称" required :error="visibleError('name')">
                <input v-model="entityForm.name" @blur="touch('name')" />
              </FormField>
              <FormField label="实体类型">
                <select v-model="entityForm.type">
                  <option>科技专家</option>
                  <option>科技企业</option>
                  <option>机构团队</option>
                  <option>论文成果</option>
                </select>
              </FormField>
              <FormField label="别名">
                <input v-model="entityForm.alias" placeholder="可选" />
              </FormField>
              <FormField label="来源批次">
                <select v-model="entityForm.batch">
                  <option>KG-INC-20260706-01</option>
                  <option>KG-INC-20260706-02</option>
                </select>
              </FormField>
            </template>

            <template v-else-if="action === 'relation'">
              <FormField label="源实体" required :error="visibleError('source')">
                <input v-model="relationForm.source" @blur="touch('source')" />
              </FormField>
              <FormField label="目标实体" required :error="visibleError('target')">
                <input v-model="relationForm.target" @blur="touch('target')" />
              </FormField>
              <FormField label="关系类型">
                <select v-model="relationForm.relation">
                  <option>论文合作</option>
                  <option>同事关系</option>
                  <option>校友关系</option>
                  <option>企业关联</option>
                </select>
              </FormField>
              <FormField label="置信度" required :error="visibleError('confidence')" hint="0-1 之间的数字，例如 0.90">
                <input v-model="relationForm.confidence" @blur="touch('confidence')" />
              </FormField>
            </template>

            <template v-else-if="action === 'property'">
              <FormField label="对象" required :error="visibleError('object')">
                <input v-model="propertyForm.object" @blur="touch('object')" />
              </FormField>
              <FormField label="属性名" required :error="visibleError('name')">
                <input v-model="propertyForm.name" @blur="touch('name')" />
              </FormField>
              <FormField label="属性值" required :error="visibleError('value')">
                <input v-model="propertyForm.value" @blur="touch('value')" />
              </FormField>
            </template>

            <template v-else-if="action === 'batch-audit'">
              <table class="construction-action-table">
                <thead>
                  <tr>
                    <th>
                      <input v-model="isAllAuditChecked" type="checkbox" aria-label="全选" />
                    </th>
                    <th>对象</th>
                    <th>审核类型</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in auditRows" :key="row.id">
                    <td><input v-model="row.checked" type="checkbox" :aria-label="`选择 ${row.name}`" /></td>
                    <td>{{ row.name }}</td>
                    <td>{{ row.type }}</td>
                  </tr>
                </tbody>
              </table>
            </template>

            <template v-else>
              <FormField label="规则文件" required :error="visibleError('fileName')">
                <input type="file" accept=".json,.yaml,.yml,.csv" @change="handleFileChange" />
              </FormField>
              <FormField label="规则类型">
                <select v-model="ruleImportForm.ruleType">
                  <option>实体消歧</option>
                  <option>关系抽取</option>
                  <option>属性映射</option>
                </select>
              </FormField>
              <FormField label="导入方式">
                <select v-model="ruleImportForm.mode">
                  <option>增量导入</option>
                  <option>全量覆盖</option>
                </select>
              </FormField>
              <p v-if="ruleImportForm.fileName" class="construction-action-form__file">{{ ruleImportForm.fileName }}</p>
            </template>
          </div>

          <footer class="construction-action-form__actions">
            <button class="kg-button kg-button--secondary" type="button" @click="emit('close')">取消</button>
            <button class="kg-button" type="submit" :disabled="isSubmitting">{{ config.submitLabel }}</button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.kg-modal {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(16, 38, 76, 0.42);
  backdrop-filter: blur(2px);
}

.construction-action-modal {
  width: min(560px, 100%);
  max-height: min(80vh, 720px);
  overflow: hidden;
  border: 1px solid rgba(167, 201, 250, 0.96);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-panel);
}

.kg-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(90deg, rgba(22, 93, 255, 0.08), transparent 48%);
}

.kg-modal__header h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 26px;
}

.kg-modal__header button {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: var(--surface-subtle);
  color: var(--text-secondary);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.construction-action-form {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  max-height: calc(min(80vh, 720px) - 60px);
}

.construction-action-form__body {
  display: grid;
  gap: 14px;
  padding: 16px 18px;
  overflow: auto;
}

.construction-action-form label {
  display: grid;
  gap: 6px;
}

.construction-action-form label span {
  color: var(--text-secondary);
  font-size: 12px;
}

.construction-action-form input,
.construction-action-form select {
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
}

.construction-action-form input[type='file'] {
  height: auto;
  padding: 6px 0;
  border: 0;
}

.construction-action-form__file {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.construction-action-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 18px 16px;
  border-top: 1px solid var(--border);
}

.construction-action-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.construction-action-table th,
.construction-action-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.construction-action-table th {
  background: var(--surface-subtle);
  color: var(--text-secondary);
  font-weight: 500;
}

.construction-action-table th:first-child,
.construction-action-table td:first-child {
  width: 44px;
}
</style>
