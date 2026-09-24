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
.schema-properties{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.schema-properties__chip{display:flex;align-items:center;gap:4px;min-width:0;padding:4px 8px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;font-size:12px;line-height:20px;white-space:nowrap}
.schema-properties__chip b{flex:0 1 auto;min-width:0;overflow:hidden;color:#4e5969;font-weight:500;text-overflow:ellipsis}
.schema-properties__chip b::after{content:":"}
.schema-properties__chip em{flex:1;min-width:0;overflow:hidden;color:#1d2129;font-style:normal;text-overflow:ellipsis}
.schema-properties__more{justify-self:start;padding:4px 8px;border:1px solid #bcd4f7;border-radius:4px;background:#eaf2ff;color:#165dff;font-size:12px;line-height:20px;cursor:pointer}
.schema-properties__more:hover{background:#dcebff}
.schema-properties__more:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
.schema-properties__empty{color:#c9cdd4;font-size:12px}
</style>
