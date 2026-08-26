<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BusinessServiceAlgorithmPanel from "./components/BusinessServiceAlgorithmPanel.vue";
import BusinessServiceContractPanel from "./components/BusinessServiceContractPanel.vue";
import { getServiceModule, serviceModules } from "./service-modules";

const route = useRoute();
const router = useRouter();
const activeView = ref<"test" | "developer">("test");
const selectedModuleKey = ref(String(route.name ?? "expert-direct"));
const viewOrder = ["test", "developer"] as const;

function handleViewTabKeydown(event: KeyboardEvent) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const current = viewOrder.indexOf(activeView.value);
  const next = event.key === "Home"
    ? 0
    : event.key === "End"
      ? viewOrder.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + viewOrder.length) % viewOrder.length;
  activeView.value = viewOrder[next];
  requestAnimationFrame(() => {
    document.getElementById(`business-view-tab-`)?.focus();
  });
}

onMounted(() => {
  const navigation = performance.getEntriesByType("navigation")[0] as
    | PerformanceNavigationTiming
    | undefined;
  if (navigation?.type === "reload" && route.name !== "expert-direct") {
    void router.replace({ name: "expert-direct" });
  }
});

const moduleInfo = computed(() =>
  getServiceModule(
    selectedModuleKey.value || String(route.name ?? "expert-direct"),
  ),
);
const requestJson = computed(() =>
  JSON.stringify(moduleInfo.value.requestExample, null, 2),
);
const responseJson = computed(() =>
  JSON.stringify(moduleInfo.value.responseExample, null, 2),
);
const curlSample = computed(
  () => `curl -X ${moduleInfo.value.method} "${moduleInfo.value.endpoint}" \\
  -H "Content-Type: application/json" \\
  -d '${requestJson.value.replaceAll("'", "\\'")}'`,
);

watch(
  () => route.name,
  (name) => {
    selectedModuleKey.value = String(name ?? "expert-direct");
  },
);
</script>

<template>
  <div class="business-service">
    <header class="business-service__toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'test' }"
          :id="`business-view-tab-test`"
          role="tab"
          :aria-selected="activeView === 'test'"
          :aria-controls="`business-view-panel-test`"
          :tabindex="activeView === 'test' ? 0 : -1"
          type="button"
          @click="activeView = 'test'"
          @keydown="handleViewTabKeydown"
        >
          算法测试
        </button>
        <button
          class="kg-tabs__item"
          :class="{ 'is-active': activeView === 'developer' }"
          :id="`business-view-tab-developer`"
          role="tab"
          :aria-selected="activeView === 'developer'"
          :aria-controls="`business-view-panel-developer`"
          :tabindex="activeView === 'developer' ? 0 : -1"
          type="button"
          @click="activeView = 'developer'"
          @keydown="handleViewTabKeydown"
        >
          开发者接口
        </button>
      </div>
    </header>

    <BusinessServiceAlgorithmPanel
      v-if="activeView === 'test'"
      id="business-view-panel-test"
      role="tabpanel"
      aria-labelledby="business-view-tab-test"
      :module-info="moduleInfo"
      :response-json="responseJson"
    />
    <BusinessServiceContractPanel
      v-else
      id="business-view-panel-developer"
      role="tabpanel"
      aria-labelledby="business-view-tab-developer"
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
  min-height: 640px;
  gap: 16px;
  min-width: 0;
  color: var(--text-primary);
}

.business-service__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 29px;
  padding: 0;
}
</style>
