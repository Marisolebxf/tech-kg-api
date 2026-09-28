<script setup lang="ts">
import { computed } from 'vue'
import { Popover as APopover } from '@arco-design/web-vue'

import type { SchemaDefinition } from '../../../api/schemaManagement'

const PROPERTY_PREVIEW_LIMIT = 4

const props = defineProps<{
  schema: SchemaDefinition
}>()

const visibleProperties = computed(() =>
  props.schema.properties.slice(0, PROPERTY_PREVIEW_LIMIT),
)

const hiddenProperties = computed(() =>
  props.schema.properties.slice(PROPERTY_PREVIEW_LIMIT),
)
</script>

<template>
  <div class="schema-properties">
    <span
      v-for="property in visibleProperties"
      :key="property.name"
      class="schema-properties__chip"
      :title="`${property.name}: ${property.dataType}`"
    >
      <b>{{ property.name }}</b>
      <em>{{ property.dataType }}</em>
    </span>

    <APopover
      v-if="hiddenProperties.length"
      :trigger="['hover', 'click']"
      position="bl"
      content-class="schema-property-popover"
    >
      <button
        type="button"
        class="schema-properties__more"
        :aria-label="`查看其余 ${hiddenProperties.length} 个属性`"
      >
        +{{ hiddenProperties.length }}
      </button>
      <template #content>
        <div class="schema-property-popover__content">
          <p class="schema-property-popover__title">其他属性（{{ hiddenProperties.length }}）</p>
          <div class="schema-property-popover__grid">
            <span
              v-for="property in hiddenProperties"
              :key="property.name"
              class="schema-property-popover__item"
              :title="`${property.name}: ${property.dataType}`"
            >
              <b>{{ property.name }}</b>
              <em>{{ property.dataType }}</em>
            </span>
          </div>
        </div>
      </template>
    </APopover>

    <span v-if="!schema.properties.length" class="schema-properties__empty">—</span>
  </div>
</template>

<style scoped>
.schema-properties{display:flex;align-items:center;gap:8px;flex-wrap:wrap;--schema-property-fill:#f2f3f5}
.schema-properties__chip{display:inline-flex;flex:0 1 auto;align-items:center;gap:4px;max-width:100%;min-width:0;padding:4px 8px;border:0;border-radius:4px;background:var(--schema-property-fill);font-size:12px;line-height:20px;white-space:nowrap}
.schema-properties__chip b{flex:0 1 auto;min-width:0;overflow:hidden;color:#4e5969;font-weight:500;text-overflow:ellipsis}
.schema-properties__chip b::after{content:":"}
.schema-properties__chip em{flex:1;min-width:0;overflow:hidden;color:#1d2129;font-style:normal;text-overflow:ellipsis}
.schema-properties__more{flex:0 0 auto;padding:4px 8px;border:0;border-radius:4px;background:var(--schema-property-fill);color:#165dff;font-size:12px;line-height:20px;cursor:pointer}
.schema-properties__more:hover{background:#e5e6eb}
.schema-properties__more:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
.schema-properties__empty{color:#c9cdd4;font-size:12px}
</style>
