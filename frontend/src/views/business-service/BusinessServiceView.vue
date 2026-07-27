<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import BusinessServiceAlgorithmPanel from './components/BusinessServiceAlgorithmPanel.vue'
import BusinessServiceContractPanel from './components/BusinessServiceContractPanel.vue'
import { getServiceModule, serviceModules } from './service-modules'

const route = useRoute()
const activeView = ref<'test' | 'developer'>('test')
const selectedModuleKey = ref(String(route.name ?? 'expert-direct'))

const moduleInfo = computed(() => getServiceModule(selectedModuleKey.value || String(route.name ?? 'expert-direct')))
const requestJson = computed(() => JSON.stringify(moduleInfo.value.requestExample, null, 2))
const responseJson = computed(() => JSON.stringify(moduleInfo.value.responseExample, null, 2))
const curlSample = computed(
  () => `curl -X ${moduleInfo.value.method} "https://api.example.com${moduleInfo.value.endpoint}" \\
  -H "Content-Type: application/json" \\
  -d '${requestJson.value.replaceAll("'", "\\'")}'`,
)

watch(
  () => route.name,
  (name) => {
    selectedModuleKey.value = String(name ?? 'expert-direct')
  },
)
</script>

<template>
  <div class="business-service">
    <header class="business-service__toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'test' }"
          type="button"
          @click="activeView = 'test'"
        >
          算法测试
        </button>
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'developer' }"
          type="button"
          @click="activeView = 'developer'"
        >
          开发者接口
        </button>
      </div>
    </header>

    <BusinessServiceAlgorithmPanel
      v-if="activeView === 'test'"
      :module-info="moduleInfo"
      :modules="serviceModules"
      :response-json="responseJson"
      @select-module="selectedModuleKey = $event"
    />
    <BusinessServiceContractPanel
      v-else
      :module-info="moduleInfo"
      :modules="serviceModules"
      :curl-sample="curlSample"
      @select-module="selectedModuleKey = $event"
    />
  </div>
</template>

<style scoped>
.business-service {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 10px;
  min-width: 0;
  color: var(--text-primary);
}

.business-service__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 0 14px;
}

</style>
