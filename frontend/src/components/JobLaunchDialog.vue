<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { createJob } from '../api/workflowOperations'
import { listAllSchemas, type SchemaDefinition } from '../api/schemaManagement'
import { currentUserId as getCurrentUserId } from '../api/currentUser'
import { currentGraphSpace } from '../api/currentGraphSpace'
import { useToast } from '../composables/use-toast'
import { buildScheduleCron, describeCron, type ScheduleFrequency } from '../utils/cronSchedule'
import {
  JOB_NAME_RULE,
  SINCE_RULE,
  validateText,
} from '../utils/textInput'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  created: [jobId: string]
}>()

const { showToast } = useToast()

const name = ref('')
const runNow = ref(true)

// 数据抽取任务（唯一类型）：选 Schema（须已传脚本且绑定来源表），平台分批并发喂数转换
const extractSchemaId = ref('')
const extractBatchSize = ref<number | null>(null)
const extractSchemas = ref<SchemaDefinition[]>([])
const schemasLoading = ref(false)

// 图空间跟随右上角全局选择器（弹窗内不再单独选择）。
// 大模型/Embedding/MySQL 数据源/数据库四项已下线：抽取读源走 Schema 来源绑定，
// 脚本 ctx 资源缺省回落 env 默认（temporal_workflows._resolve_resources）
const graphSpace = computed(() => currentGraphSpace())
const since = ref('')

const executeMode = ref<'once' | 'recurring'>('once')
const frequency = ref<ScheduleFrequency>('每天')
const executionTime = ref('02:00')
const weekday = ref(1)

/** 预览与提交共用同一生成函数，所见即所得 */
const schedulePreview = computed(() =>
  describeCron(buildScheduleCron(frequency.value, executionTime.value, weekday.value)),
)

const submitting = ref(false)

const nameError = computed(() => validateText('任务名称', name.value, JOB_NAME_RULE))
const sinceError = computed(() =>
  since.value.trim() ? validateText('增量游标', since.value, SINCE_RULE) : null,
)

const canSubmit = computed(() =>
  Boolean(name.value.trim() && extractSchemaId.value)
  && !nameError.value && !sinceError.value,
)

async function loadExtractSchemas(force = false) {
  if (schemasLoading.value) return
  if (!force && extractSchemas.value.length) return
  schemasLoading.value = true
  try {
    // M4 图空间联动：下拉只列所选空间绑定的可抽取 schema，随空间切换重查；
    // script.available=false 是目录占位（如系统 Schema 种子，S3 无脚本本体）——选了必失败，直接排除
    const all = await listAllSchemas(getCurrentUserId(), graphSpace.value || undefined)
    extractSchemas.value = all.filter(
      (s) => s.script && (s.sources?.length ?? 0) > 0 && s.script.available !== false,
    )
  } catch {
    extractSchemas.value = []
  } finally {
    schemasLoading.value = false
  }
}

function reset() {
  name.value = ''
  extractSchemaId.value = ''
  extractBatchSize.value = null
  runNow.value = true
  since.value = ''
  executeMode.value = 'once'
  frequency.value = '每天'
  executionTime.value = '02:00'
  weekday.value = 1
}

watch(() => props.open, (open) => {
  if (open) {
    reset()
    loadExtractSchemas()
  }
})

watch(graphSpace, () => {
  // 换空间后原选择不再属于该空间：清空并按新空间重查
  extractSchemaId.value = ''
  loadExtractSchemas(true)
})

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    const job = await createJob({
      name: name.value.trim(),
      taskType: 'extract',
      schemaId: extractSchemaId.value,
      batchSize: extractBatchSize.value || undefined,
      schedule: executeMode.value === 'recurring'
        ? { kind: 'cron', cron: buildScheduleCron(frequency.value, executionTime.value, weekday.value), timezone: 'Asia/Shanghai' }
        : { kind: 'once' },
      runNow: executeMode.value === 'once' && runNow.value,
      graphSpace: graphSpace.value || undefined,
      since: since.value.trim() || undefined,
    })
    showToast(`任务「${job.name}」已创建${runNow.value && executeMode.value === 'once' ? '并触发执行' : ''}`, 'success')
    emit('created', job.id)
    emit('close')
  } catch (error) {
    showToast(error instanceof Error ? error.message : '创建任务失败', 'warning')
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
        <h2>新建任务</h2>
        <button type="button" aria-label="关闭弹窗" title="关闭" @click="emit('close')">×</button>
      </header>
      <div class="job-launch-body">
        <div class="job-basics">
          <label class="job-field">
            <span>任务名称</span>
            <input aria-label="如：论文-专家抽取" v-model="name" :maxlength="JOB_NAME_RULE.max" placeholder="如：论文-专家抽取" />
            <small v-if="nameError" class="field-error">{{ nameError }}</small>
          </label>
          <div class="job-field">
            <div class="job-field__label-row">
              <span>任务类型</span>
              <small
                v-if="!schemasLoading && !extractSchemas.length"
                class="muted-warn"
                role="status"
              >暂无可抽取 Schema——请先在 Schema 管理页上传抽取脚本并绑定来源表</small>
            </div>
            <div class="job-type-static">数据抽取</div>
          </div>
        </div>

        <div class="job-row">
          <!-- label 会把点击转发给 a-select 内部 input 造成"开→关"双切换，包 a-select 的字段一律用 div -->
          <div class="job-field">
            <span>目标 Schema（已传脚本并绑定来源表）</span>
            <a-select v-model="extractSchemaId" class="job-select" :loading="schemasLoading" placeholder="选择要抽取的实体/关系" allow-search allow-clear>
              <a-option v-for="s in extractSchemas" :key="s.id" :value="s.id">{{ s.label }}（{{ s.kind === 'entity' ? '实体' : '关系' }} · {{ s.name }}）</a-option>
            </a-select>
          </div>
          <label class="job-field">
            <span>批大小（默认 500）</span>
            <input aria-label="500" v-model.number="extractBatchSize" type="number" min="1" max="5000" placeholder="500" />
          </label>
        </div>

        <label class="job-field">
          <span>增量游标 since（可空）</span>
          <input aria-label="如 2026-08-01 00:00:00" v-model="since" :maxlength="SINCE_RULE.max" placeholder="如 2026-08-01 00:00:00" />
          <small v-if="sinceError" class="field-error">{{ sinceError }}</small>
        </label>

        <div class="job-field-group">
          <div class="job-row">
            <div class="job-field">
              <span>执行模式</span>
              <a-radio-group v-model="executeMode" aria-label="执行模式">
                <a-radio value="once">一次性</a-radio>
                <a-radio value="recurring">周期性</a-radio>
              </a-radio-group>
            </div>
            <template v-if="executeMode === 'recurring'">
              <div class="job-field">
                <span>频率</span>
                <a-select v-model="frequency" class="job-select" aria-label="频率" :options="['每天', '每12小时', '每6小时', '每周']" />
              </div>
              <div v-if="frequency === '每周'" class="job-field">
                <span>星期</span>
                <a-select v-model="weekday" class="job-select" aria-label="星期">
                  <a-option :value="1">周一</a-option>
                  <a-option :value="2">周二</a-option>
                  <a-option :value="3">周三</a-option>
                  <a-option :value="4">周四</a-option>
                  <a-option :value="5">周五</a-option>
                  <a-option :value="6">周六</a-option>
                  <a-option :value="0">周日</a-option>
                </a-select>
              </div>
              <label class="job-field">
                <span>首次执行时间</span>
                <input aria-label="executionTime" v-model="executionTime" type="time" />
              </label>
            </template>
            <div v-else class="job-field checkbox-field">
              <a-checkbox v-model="runNow" aria-label="创建后立即执行">创建后立即执行</a-checkbox>
            </div>
          </div>
          <p v-if="executeMode === 'recurring'" class="schedule-preview">
            执行计划：<strong>{{ schedulePreview }}</strong><span class="cron-hint">（首次执行时间即第一次触发，之后按频率顺延）</span>
          </p>
        </div>
      </div>
      <footer>
        <button type="button" @click="emit('close')">取消</button>
        <button type="button" class="primary" :disabled="!canSubmit || submitting" @click="submit">{{ submitting ? '创建中…' : '创建任务' }}</button>
      </footer>
    </aside>
  </Teleport>
</template>

<style scoped>
.job-launch-mask{position:fixed;inset:0;z-index:49;border:0;background:rgba(16,38,76,0.42);backdrop-filter:blur(2px);cursor:pointer}
.job-launch-dialog{position:fixed;z-index:50;top:50%;left:50%;width:min(720px,calc(100vw - 48px));max-height:calc(100vh - 48px);display:flex;flex-direction:column;overflow:hidden;border-radius:8px;background:#fff;box-shadow:0 24px 70px rgba(28,58,107,0.3);font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;transform:translate(-50%,-50%)}
.job-launch-dialog :deep(*){font-family:inherit;letter-spacing:0}
.job-launch-dialog>header{display:flex;box-sizing:border-box;flex:0 0 56px;height:56px;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid #e5e6eb;background:#fff}
.job-launch-dialog h2{margin:0;color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.job-launch-dialog header button{display:grid;box-sizing:border-box;width:32px;height:32px;padding:0;border:0;border-radius:4px;background:#fff;color:#4e5969;font-size:18px;line-height:18px;cursor:pointer;place-items:center}
.job-launch-body{flex:1;min-height:0;box-sizing:border-box;overflow-x:hidden;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:16px}
.job-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.job-row:has(> :nth-child(3)){grid-template-columns:1fr 1fr 1fr}
.job-basics{display:grid;gap:16px}
.job-field{display:flex;min-width:0;flex-direction:column;gap:8px;color:#4e5969;font-size:14px;line-height:22px}
.job-field>span{color:#4e5969;font-size:14px;line-height:22px}
.job-field__label-row{display:flex;min-width:0;align-items:center;gap:8px;flex-wrap:wrap}.job-field__label-row>span{flex:0 0 auto;color:#4e5969;font-size:14px;line-height:22px}.job-field__label-row>.muted-warn{color:#ff7d00!important}
.job-field>input:not([type="file"]){box-sizing:border-box;width:100%;height:32px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#1d2129;font-size:14px;line-height:14px;outline:0;box-shadow:none}
.job-field>input:not([type="file"]):hover{border-color:#4080ff}
.job-field>input:not([type="file"]):focus,.job-field>input:not([type="file"]):focus-visible{border-color:#004ecc;outline:0;box-shadow:0 0 0 2px rgba(0,78,204,.1)}
.job-type-static{box-sizing:border-box;display:flex;align-items:center;height:32px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;color:#1d2129;font-size:14px;line-height:22px}
:deep(.job-select.arco-select-view){display:inline-flex;box-sizing:border-box;width:100%;min-width:0;height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;align-items:center}
:deep(.job-select.arco-select-view:hover){border-color:#4080ff!important;background:#fff!important}
:deep(.job-select.arco-select-view:focus-within),:deep(.job-select.arco-select-view-focus){border-color:#004ecc;background:#fff!important;box-shadow:0 0 0 2px rgba(0,78,204,.1)!important}
:deep(.job-select.arco-select-view .arco-select-view-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
:deep(.job-select.arco-select-view .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important;pointer-events:none!important}
:deep(.job-select.arco-select-view .arco-select-view-value),:deep(.job-select.arco-select-view .arco-select-view-placeholder){min-width:0;overflow:hidden;background:transparent!important;font-size:14px;line-height:22px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.job-field.checkbox-field{justify-content:flex-end}
.job-field-group{display:flex;min-width:0;gap:16px;flex-direction:column}
.job-launch-dialog>footer{display:flex;box-sizing:border-box;flex:0 0 64px;height:64px;align-items:center;justify-content:flex-end;gap:16px;padding:16px 24px;border-top:1px solid #e3ebf6;background:#fff}
.job-launch-dialog footer button{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:14px;font-weight:400;cursor:pointer}
.job-launch-dialog footer .primary{border-color:#004ecc;background:#004ecc;color:#fff}
.job-launch-dialog footer button:disabled{opacity:.5;cursor:not-allowed}
.muted-warn{margin:0;color:#ff7d00;font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.schedule-preview{margin:0;color:#4e5969;font-size:12px;line-height:20px}
.field-error{color:#e4322d;font-size:12px;line-height:18px}
.schedule-preview strong{color:#004ecc;font-weight:600}
.schedule-preview .cron-hint{color:#86909c}
</style>
