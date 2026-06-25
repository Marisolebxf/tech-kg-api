<script setup lang="ts">
import type { ExpertProfile } from '../types'
import type { ColleagueInferenceResult } from '../types'

defineProps<{
  profile: ExpertProfile
  result: ColleagueInferenceResult
  resultMode: 'structured' | 'api'
}>()

const emit = defineEmits<{
  'update:resultMode': [value: 'structured' | 'api']
}>()
</script>

<template>
  <section class="kg-panel profile-card">
    <div class="kg-panel__header">
      <h2 class="kg-panel__title">结果详情</h2>
      <div class="profile-card__tabs">
        <button
          :class="{ 'is-active': resultMode === 'structured' }"
          type="button"
          @click="emit('update:resultMode', 'structured')"
        >
          结构化结果
        </button>
        <button
          :class="{ 'is-active': resultMode === 'api' }"
          type="button"
          @click="emit('update:resultMode', 'api')"
        >
          API结果示例
        </button>
      </div>
    </div>

    <dl v-if="resultMode === 'structured'" class="profile-card__table">
      <div>
        <dt>专家 A</dt>
        <dd>{{ result.expertA.name }}</dd>
      </div>
      <div>
        <dt>专家 A 职称</dt>
        <dd>{{ result.expertA.title }}</dd>
      </div>
      <div>
        <dt>专家 B</dt>
        <dd>{{ result.expertB.name }}</dd>
      </div>
      <div>
        <dt>专家 B 职称</dt>
        <dd>{{ result.expertB.title }}</dd>
      </div>
      <div>
        <dt>关系类型</dt>
        <dd>{{ result.relationType }}</dd>
      </div>
      <div>
        <dt>共同机构</dt>
        <dd>{{ result.organization }}</dd>
      </div>
      <div>
        <dt>共事时段</dt>
        <dd>{{ result.overlapPeriod }}</dd>
      </div>
      <div>
        <dt>协作成果</dt>
        <dd>
          <span class="profile-card__tag">论文 {{ result.collaborations.paper }}</span>
          <span class="profile-card__tag">专利 {{ result.collaborations.patent }}</span>
          <span class="profile-card__tag">项目 {{ result.collaborations.project }}</span>
        </dd>
      </div>
    </dl>
    <pre v-else class="profile-card__code">{
  "from": "{{ result.expertA.name }}",
  "to": "{{ result.expertB.name }}",
  "organization": "{{ result.organization }}",
  "period": {
    "start": "2018.03",
    "end": "2022.12"
  },
  "collaboration": {
    "paper": {{ result.collaborations.paper }},
    "patent": {{ result.collaborations.patent }},
    "project": {{ result.collaborations.project }}
  },
  "status": "success"
}</pre>
  </section>
</template>

<style scoped>
.profile-card {
  height: 100%;
  min-height: 540px;
}

.profile-card__tabs {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border-radius: var(--radius-sm);
  background: var(--surface-subtle);
}

.profile-card__tabs button {
  height: 28px;
  padding: 0 var(--space-12);
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
  font-size: 14px;
}

.profile-card__tabs button.is-active {
  color: var(--primary);
  background: var(--surface);
  font-weight: 500;
}

.profile-card__table {
  margin: 0;
}

.profile-card__table div {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  min-height: 44px;
  border-bottom: 1px solid var(--border);
}

.profile-card__table dt,
.profile-card__table dd {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0 var(--space-16);
  font-size: 14px;
  line-height: 22px;
}

.profile-card__table dt {
  justify-content: flex-end;
  border-right: 1px solid var(--border);
  color: var(--text-tertiary);
}

.profile-card__table dd {
  color: var(--text-primary);
}

.profile-card__tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  margin-right: var(--space-8);
  padding: 0 var(--space-8);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  color: var(--text-primary);
  font-size: 12px;
}

.profile-card__code {
  min-height: 488px;
  margin: 0;
  padding: var(--space-16) 24px;
  color: #52c41a;
  background: var(--surface);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 24px;
  white-space: pre-wrap;
}
</style>
