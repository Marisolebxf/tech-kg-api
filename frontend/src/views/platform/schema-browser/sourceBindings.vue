<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listMysqlDatasources, type MysqlDatasource } from '../../../api/mysqlDatasource'
import { useToast } from '../../../composables/use-toast'
import { emptySourceBindingRow, type SourceBindingRow } from './sourceBindingRows'
import SourceBindingRowVue from './sourceBindingRow.vue'

const props = defineProps<{
  modelValue: SourceBindingRow[]
  showAddButton?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SourceBindingRow[]): void
}>()

const { showToast } = useToast()

const datasources = ref<MysqlDatasource[]>([])

onMounted(async () => {
  try {
    datasources.value = await listMysqlDatasources()
  } catch (error) {
    showToast(error instanceof Error ? error.message : '数据源列表加载失败', 'warning')
  }
})

function addRow() {
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
      尚未绑定来源表；绑定后可通过「触发抽取」由平台按时间列水位分批读取并写入图谱。
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
    <button v-if="showAddButton !== false" type="button" class="source-bindings__add" @click="addRow">＋ 绑定来源表</button>
  </div>
</template>

<style scoped>
.source-bindings{display:flex;flex-direction:column;gap:8px}
.source-bindings__empty{padding:8px 16px;border:1px dashed #e5e6eb;border-radius:6px;color:#86909c;font-size:12px;line-height:20px}
.source-bindings__add{align-self:flex-start;height:28px;padding:0 12px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#165dff;font-size:12px;cursor:pointer}
.source-bindings__add:hover{border-color:#165dff}
</style>
