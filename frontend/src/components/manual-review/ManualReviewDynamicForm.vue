<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
type Section={type:string;source?:string;target?:string;field?:string;options?:string[]}
const props=defineProps<{ sections:Section[]; data:Record<string,unknown> }>()
const emit=defineEmits<{ change:[value:Record<string,unknown>] }>()
const value=reactive({ mappingsJson:'', fieldsJson:'', runtimeJson:'', mergeMaster:'', entityVerdict:'', targetEntityId:'', evidence:[] as unknown[] })
watch(value,()=>emit('change',{...value}),{deep:true})
const json=(v:unknown)=>JSON.stringify(v??{},null,2)
const candidate=computed(()=>props.data.candidate as Record<string,unknown>|undefined)
const evidence=computed(()=>(props.data.evidence as unknown[]|undefined)??[])
const supported=new Set(['mapping-table','field-editor','record-merge','entity-comparison','evidence-list','attribute-comparison','runtime-config','raw-json-readonly'])
const toggleEvidence=(item:unknown,event:Event)=>{ const checked=(event.target as HTMLInputElement).checked; value.evidence=checked?[...value.evidence,item]:value.evidence.filter((entry)=>entry!==item) }
</script>
<template>
  <div class="dynamic-form">
    <section v-for="(section,index) in sections" :key="`${section.type}-${index}`" class="dynamic-section">
      <template v-if="section.type==='mapping-table'">
        <h3>字段/字典映射</h3><textarea v-model="value.mappingsJson" placeholder='[{"source":"源字段","target":"目标字段"}]' />
      </template>
      <template v-else-if="section.type==='field-editor'">
        <h3>缺失字段补录</h3><pre>{{ json(candidate?.missingFields) }}</pre><textarea v-model="value.fieldsJson" placeholder='{"field":"人工值"}' />
      </template>
      <template v-else-if="section.type==='record-merge'">
        <h3>重复记录定主</h3><pre>{{ json(candidate?.records) }}</pre><input v-model="value.mergeMaster" placeholder="主记录 ID" />
      </template>
      <template v-else-if="section.type==='entity-comparison'">
        <h3>候选与存量实体</h3><div class="compare"><pre>{{ json(candidate) }}</pre><pre>{{ json(candidate?.existingCandidates) }}</pre></div>
        <select v-model="value.entityVerdict"><option value="merge">合并</option><option value="create">新建</option><option value="retype">改类型</option><option value="reject">驳回</option></select>
        <input v-model="value.targetEntityId" placeholder="目标实体 ID（合并时必填）" />
      </template>
      <template v-else-if="section.type==='evidence-list'">
        <h3>关系证据</h3><label v-for="(item,i) in evidence" :key="i"><input type="checkbox" @change="toggleEvidence(item,$event)" /> <code>{{ json(item) }}</code></label>
      </template>
      <template v-else-if="section.type==='attribute-comparison'">
        <h3>属性来源对照</h3><pre>{{ json(candidate?.conflicts) }}</pre><textarea v-model="value.fieldsJson" placeholder='{"属性":"最终值"}' />
      </template>
      <template v-else-if="section.type==='runtime-config'">
        <h3>运行配置</h3><pre>{{ json(candidate?.runtime) }}</pre><textarea v-model="value.runtimeJson" placeholder='{"model":"...","timeoutSeconds":60}' />
      </template>
      <template v-else-if="section.type==='raw-json-readonly' || !supported.has(section.type)">
        <h3>只读异常数据</h3><p v-if="!supported.has(section.type)" class="warning">未知安全组件 {{ section.type }}，仅允许查看并升级治理员。</p><pre>{{ json(data) }}</pre>
      </template>
    </section>
  </div>
</template>
<style scoped>
.dynamic-form{display:grid;gap:12px}.dynamic-section{padding:14px;border:1px solid #dce8f8;border-radius:8px;background:#fff}.dynamic-section h3{margin:0 0 10px}.dynamic-section textarea{box-sizing:border-box;width:100%;min-height:100px;padding:9px;border:1px solid #bdd0ea;border-radius:6px}.dynamic-section input,.dynamic-section select{min-height:34px;margin:5px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px}.dynamic-section pre{overflow:auto;max-height:260px;padding:10px;background:#f6f8fb;white-space:pre-wrap}.compare{display:grid;grid-template-columns:1fr 1fr;gap:10px}.dynamic-section label{display:flex;gap:8px;margin:7px 0}.warning{color:#b54708}@media(max-width:800px){.compare{grid-template-columns:1fr}}
</style>
