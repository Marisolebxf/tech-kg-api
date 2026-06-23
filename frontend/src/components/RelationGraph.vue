<script setup lang="ts">
import { computed } from 'vue'
import type { RelationGraph } from '../types/directRelation'

const props = defineProps<{
  graph: RelationGraph
}>()

function pathForEdge(edge: RelationGraph['edges'][number]) {
  if (edge.c1 && edge.c2) {
    return `M ${edge.from_[0]} ${edge.from_[1]} C ${edge.c1[0]} ${edge.c1[1]}, ${edge.c2[0]} ${edge.c2[1]}, ${edge.to[0]} ${edge.to[1]}`
  }
  return `M ${edge.from_[0]} ${edge.from_[1]} L ${edge.to[0]} ${edge.to[1]}`
}

const svgHeight = computed(() => props.graph.height)
</script>

<template>
  <div class="graph-shell">
    <svg :viewBox="`0 0 ${graph.width} ${svgHeight}`" class="graph-canvas" role="img" aria-label="关系图谱">
      <defs>
        <linearGradient id="graph-node-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="#f8fbff" />
          <stop offset="100%" stop-color="#ffffff" />
        </linearGradient>
        <marker id="graph-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#8f52db" />
        </marker>
      </defs>

      <g v-for="edge in graph.edges" :key="`${edge.label}-${edge.label_x}-${edge.label_y}`">
        <path
          :d="pathForEdge(edge)"
          :stroke="edge.stroke"
          :stroke-width="edge.width"
          fill="none"
          :marker-end="'url(#graph-arrow)'"
        />
        <text :x="edge.label_x" :y="edge.label_y" class="graph-edge-label" :fill="edge.label_color || '#8f52db'">
          {{ edge.label }}
        </text>
      </g>

      <g v-for="node in graph.nodes" :key="node.id" :transform="`translate(${node.x}, ${node.y})`">
        <rect
          :x="node.kind === 'institution' ? -160 : -110"
          :y="node.kind === 'institution' ? -42 : -40"
          :width="node.kind === 'institution' ? 320 : 220"
          :height="node.kind === 'institution' ? 84 : 80"
          rx="14"
          :class="['graph-node', `graph-node--${node.kind}`]"
        />
        <text class="graph-node-icon" x="0" y="-12" text-anchor="middle">{{ node.icon }}</text>
        <text class="graph-node-title" x="0" y="12" text-anchor="middle">{{ node.title }}</text>
        <text class="graph-node-subtitle" x="0" y="34" text-anchor="middle">{{ node.subtitle }}</text>
      </g>
    </svg>
  </div>
</template>
