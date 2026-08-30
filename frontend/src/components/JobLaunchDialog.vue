<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  createSchedule,
  executeDefinition,
} from '../api/workflowOperations'
import type { SchemaDefinition } from '../api/schemaManagement'
import type { LlmConfig } from '../api/llmConfig'
import { useToast } from '../composables/use-toast'

const props = defineProps<{
  open: boolean
  schemas: SchemaDefinition[]
  llmConfigs: LlmConfig[]
}>()

const emit = defineEmits<{
  close: []
  launched: [payload: { mode: 'once' | 'recurring'; workflowDefinitionId: string }]
}>()

const { showToast } = useToast()

const selectedSchemaId = ref('')
const llmConfigId = ref('')
const executeMode = ref<'once' | 'recurring'>('once')
const frequency = ref('每天')
const executionTime = ref('02:00')
const since = ref('')
const domains = ref('')
const submitting = ref(false)
const notice = ref('')

const selectedSchema = computed(() =>
  props.schemas.find((s) => s.id === selectedSchemaId.value),
)

function reset() {
  selectedSchemaId.value = ''
  llmConfigId.value = ''
  executeMode.value = 'once'
  frequency.value = '每天'
  executionTime.value = '02:00'
  since.value = ''
  domains.value = ''
  notice.value = ''
}

watch(() => props.open, (open) => {
  if (open) reset()
})

watch(selectedSchemaId, (id) => {
  const schema = props.schemas.find((s) => s.id === id)
  llmConfigId.value = schema?.llmConfigId || ''
})

function buildCron(): string {
  const [h, m] = executionTime.value.split(':')
  const hour = Number(h) || 0
  const min = Number(m) || 0
  switch (frequency.value) {
    case '每12小时': return `${min} */12 * * *`
    case '每6小时': return `${min} */6 * * *`
    case '每周': return `${min} ${hour} * * 1`
    default: return `${min} ${hour} * * *`
  }
}

async function submit() {
  const schema = selectedSchema.value
  if (!schema) {
    showToast('请选择作业', 'warning')
    return
  }
  const definitionId = schema.script?.workflowDefinitionId
  if (!definitionId) {
    showToast('该作业未上传脚本或未注册工作流', 'warning')
    return
  }
  const payload: Record<string, unknown> = {}
  if (llmConfigId.value) payload.llmConfigId = llmConfigId.value
  if (since.value.trim()) payload.since = since.value.trim()
  const domainList = domains.value.split(/[,，\s]+/).filter(Boolean)
  if (domainList.length) payload.domains = domainList

  submitting.value = true
  notice.value = executeMode.value === 'once' ? '正在下发执行…' : '正在创建调度…'
  try {
    if (executeMode.value === 'once') {
      const execution = await executeDefinition(definitionId, payload)
      notice.value = `已下发，执行 ID：${execution.id}，状态：${execution.status}`
      emit('launched', { mode: 'once', workflowDefinitionId: definitionId })
    } else {
      const scheduleId = `job-${Date.now()}`
      const schedule = await createSchedule(definitionId, {
        id: scheduleId,
        cron: buildCron(),
        timezone: 'Asia/Shanghai',
        active: true,
        payload,
      })
      notice.value = `已创建调度：${schedule.id}（cron ${schedule.cron}）`
      emit('launched', { mode: 'recurring', workflowDefinitionId: definitionId })
    }
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '下发失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <button v-if="open" class="job-launch-mask" type="button" aria-label="关闭" @click="emit('close')" />
    <aside v-if="open" class="job-launch-dialog">
      <header>
        <div><span>作业运行</span><h2>启动作业</h2></div>
        <button type="button" @click="emit('close')">×</button>
      </header>
      <div class="job-launch-body">
        <label class="job-field">
          <span>作业（Schema）*</span>
          <select v-model="selectedSchemaId">
            <option value="">请选择</option>
            <option v-for="s in schemas" :key="s.id" :value="s.id">{{ s.label }}（{{ s.name }}）</option>
          </select>
          <small v-if="!schemas.length" class="muted">暂无已注册工作流的作业（请在 Schema 管理上传脚本）</small>
        </label>

        <label class="job-field">
          <span>大模型配置</span>
          <select v-model="llmConfigId">
            <option value="">使用全局默认</option>
            <option v-for="c in llmConfigs" :key="c.id" :value="c.id">{{ c.name }}（{{ c.model }}）{{ c.isDefault ? ' ★' : '' }}</option>
          </select>
          <small>默认带出 Schema 绑定配置，可临时覆盖</small>
        </label>

        <div class="job-field">
          <span>执行模式</span>
          <div class="job-radio-group">
            <label><input v-model="executeMode" type="radio" value="once" /> 执行一次</label>
            <label><input v-model="executeMode" type="radio" value="recurring" /> 定期执行</label>
          </div>
        </div>

        <div v-if="executeMode === 'recurring'" class="job-row">
          <label class="job-field">
            <span>频率</span>
            <select v-model="frequency">
              <option>每天</option>
              <option>每12小时</option>
              <option>每6小时</option>
              <option>每周</option>
            </select>
          </label>
          <label class="job-field">
            <span>执行时间</span>
            <input v-model="executionTime" type="time" />
          </label>
        </div>

        <label class="job-field">
          <span>增量游标 since（可空，空 = 全量）</span>
          <input v-model="since" placeholder="如 2026-08-01 00:00:00" />
        </label>

        <label class="job-field">
          <span>业务域范围（可空，逗号分隔）</span>
          <input v-model="domains" placeholder="如 论文域,人才域" />
        </label>
      </div>
      <p v-if="notice" class="job-launch-notice">{{ notice }}</p>
      <footer>
        <button type="button" @click="emit('close')">关闭</button>
        <button type="button" class="primary" :disabled="submitting || !selectedSchemaId" @click="submit">{{ submitting ? '下发中…' : '启动' }}</button>
      </footer>
    </aside>
  </Teleport>
</template>

<style scoped>
.job-launch-mask{position:fixed;inset:0;z-index:49;border:0;background:rgba(16,38,76,0.42);backdrop-filter:blur(2px);cursor:pointer}
.job-launch-dialog{position:fixed;z-index:50;top:50%;left:50%;width:min(560px,calc(100vw - 40px));max-height:88vh;display:flex;flex-direction:column;overflow:hidden;border-radius:10px;background:#fff;box-shadow:0 24px 70px rgba(28,58,107,0.3);transform:translate(-50%,-50%)}
.job-launch-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:16px 18px;border-bottom:1px solid #e3ebf6;background:linear-gradient(90deg,#eef5ff,#fff)}
.job-launch-dialog header span{color:#165dff;font-size:10px}
.job-launch-dialog h2{margin:4px 0 0;font-size:17px;color:#1d2129}
.job-launch-dialog header button{width:28px;height:28px;border:0;border-radius:5px;background:#f0f4fa;color:#4e5969;font-size:18px;cursor:pointer}
.job-launch-body{flex:1;min-height:0;overflow:auto;padding:16px 18px;display:flex;flex-direction:column;gap:12px}
.job-field{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#4e5969}
.job-field>span{color:#5d6e87;font-size:11px}
.job-field input,.job-field select{height:32px;padding:0 8px;border:1px solid #c9cdd4;border-radius:4px;font-size:13px;color:#1d2129;background:#fff}
.job-field small{color:#8191aa;font-size:10px;line-height:14px}
.job-field small.muted{color:#b54708}
.job-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.job-radio-group{display:flex;gap:16px;padding:6px 0}
.job-radio-group label{display:flex;align-items:center;gap:5px;font-size:13px;color:#344763;cursor:pointer}
.job-radio-group input{margin:0}
.job-launch-notice{margin:0;padding:10px 18px;border-top:1px solid #e3ebf6;background:#eef5ff;color:#315b95;font-size:11px;line-height:16px}
.job-launch-dialog>footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid #e3ebf6;background:#fff}
.job-launch-dialog footer button{height:33px;padding:0 16px;border:1px solid #c9cdd4;border-radius:5px;background:#fff;color:#4e5969;font-size:13px;cursor:pointer}
.job-launch-dialog footer .primary{border-color:#165dff;background:#165dff;color:#fff}
.job-launch-dialog footer button:disabled{opacity:.6;cursor:not-allowed}
</style>
