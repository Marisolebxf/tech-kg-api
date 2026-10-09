<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listMysqlDatasources, type MysqlDatasource } from '../../../api/mysqlDatasource'
import { useToast } from '../../../composables/use-toast'
import { emptySourceBindingRow, isSourceBindingComplete, type SourceBindingRow } from './sourceBindingRows'
import SourceBindingRowVue from './sourceBindingRow.vue'

// showAddButton 默认 true：Boolean prop 不给默认值时缺省为 false，
// 行级「来源表」弹窗会丢「＋ 绑定来源表」按钮（新建弹窗显式传 false 复用自己的加号）
const props = withDefaults(
  defineProps<{
    modelValue: SourceBindingRow[]
    showAddButton?: boolean
  }>(),
  { showAddButton: true },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: SourceBindingRow[]): void
}>()

const { showToast } = useToast()

const datasources = ref<MysqlDatasource[]>([])

onMounted(async () => {
  try {
    datasources.value = await listMysqlDatasources()
  } catch (error) {
    showToast(error instanceof Error ? error.message : '数据源列表加载失败', 'error')
  }
})

const addAttempted = ref(false)
const hasIncompleteRow = computed(() => props.modelValue.some(row => !isSourceBindingComplete(row)))

function addRow() {
  if (hasIncompleteRow.value) {
    addAttempted.value = true
    return
  }
  addAttempted.value = false
  emit('update:modelValue', [...props.modelValue, emptySourceBindingRow()])
}

function removeRow(index: number) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

function updateRow(index: number, value: SourceBindingRow) {
  const next = [...props.modelValue]
  next[index] = value
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="source-bindings">
    <div v-if="!modelValue.length" class="source-bindings__empty">
      尚未绑定来源表；绑定保存后到「图谱构建」页新建抽取任务，由平台按时间列水位分批读取并写入图谱。
    </div>
    <SourceBindingRowVue
      v-for="(binding, index) in modelValue"
      :key="index"
      :model-value="binding"
      :datasources="datasources"
      :removable="true"
      @update:model-value="(value) => updateRow(index, value)"
      @remove="removeRow(index)"
    />
    <p v-if="showAddButton && addAttempted && hasIncompleteRow" class="source-bindings__validation" role="alert">请填写完已有来源表的必填信息（数据源、数据库、来源表）后再添加。</p>
    <button v-if="showAddButton" type="button" class="source-bindings__add" @click="addRow">＋ 绑定来源表</button>
  </div>
</template>

<style scoped>
/* 行内五列有像素下限（行 min-width 720px），弹窗窄时整块横向拖动看全 */
.source-bindings{display:flex;flex-direction:column;gap:8px;overflow-x:auto}
.source-bindings__empty{padding:8px 16px;border:1px dashed #e5e6eb;border-radius:6px;color:#86909c;font-size:12px;line-height:20px}
.source-bindings__validation{margin:0;color:#b42318;font-size:14px;line-height:22px}
.source-bindings__add{align-self:flex-start;height:28px;padding:0 12px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#165dff;font-size:12px;cursor:pointer}
.source-bindings__add:hover{border-color:#165dff}
</style>
