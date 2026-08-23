<script setup lang="ts">
import { IconFullscreen, IconMinus, IconPlus } from '@arco-design/web-vue/es/icon'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import type { GraphEdgeData, GraphNodeData } from '../data/graph-presets'

const props = withDefaults(
  defineProps<{
    nodes: GraphNodeData[]
    edges: GraphEdgeData[]
    activeCategories?: string[] | null
    selectedNodeId?: string | null
    selectedEdgeId?: string | null
    ariaLabel?: string
    nodeShape?: 'rect' | 'circle'
  }>(),
  {
    activeCategories: null,
    selectedNodeId: null,
    selectedEdgeId: null,
    ariaLabel: '知识图谱',
    nodeShape: 'rect',
  },
)

const emit = defineEmits<{
  selectNode: [node: GraphNodeData]
  selectEdge: [edge: GraphEdgeData]
}>()

const viewBox = '0 0 760 430'
const minScale = 0.6
const maxScale = 2.2
const scaleStep = 0.1
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const containerRef = ref<HTMLElement | null>(null)

const transform = computed(() => `translate(${panX.value} ${panY.value}) scale(${scale.value})`)

const edgeToneMap: Record<string, string> = {
  论文合作: 'is-primary',
  同事: 'is-green',
  校友: 'is-green',
  企业关联: 'is-orange',
  产业事件: 'is-purple',
  直接关系: 'is-primary',
  间接关系: 'is-purple',
}

function isEdgeActive(edge: GraphEdgeData) {
  if (!props.activeCategories?.length) return true
  return props.activeCategories.some(
    (category) => edge.category === category || edge.label.includes(category),
  )
}

function edgeClass(edge: GraphEdgeData) {
  const classes = ['platform-network-line']
  if (!isEdgeActive(edge)) classes.push('is-dimmed')
  else classes.push(edgeToneMap[edge.category] ?? 'is-primary')
  if (props.selectedEdgeId === edge.id) classes.push('is-selected')
  return classes.join(' ')
}

function nodeClass(
  node: GraphNodeData,
) {
  const classes = [
    'platform-node',
    `is-${node.nodeType}`,
  ]
  if (props.nodeShape === 'circle') classes.push('is-solid-circle')

  /*
   * 中心节点只负责加粗、加大，
   * 不再改变实体类型颜色。
   */
  if (node.level === 0) {
    classes.push(
      'platform-node--center',
    )
  }

  if (
    props.selectedNodeId
    === node.id
  ) {
    classes.push('is-selected')
  }

  return classes.join(' ')
}

function nodeWidth(node: GraphNodeData) {
  const preferred = Math.max(104, node.label.length * 11 + 28)
  return Math.min(node.level === 0 ? 164 : 144, preferred)
}

function nodeHeight(node: GraphNodeData) {
  return node.level === 0 ? 54 : 46
}

function nodeBoundaryOffset(node: GraphNodeData, dx: number, dy: number, gap = 0) {
  if (props.nodeShape === 'circle') {
    const length = Math.hypot(dx, dy) || 1
    const radius = (node.level === 0 ? 30 : 23) + gap
    return { x: (dx / length) * radius, y: (dy / length) * radius }
  }
  const halfWidth = nodeWidth(node) / 2 + gap
  const halfHeight = nodeHeight(node) / 2 + gap
  const factor = 1 / Math.max(Math.abs(dx) / halfWidth, Math.abs(dy) / halfHeight, 0.0001)
  return { x: dx * factor, y: dy * factor }
}

function getNodeById(id: string) {
  return props.nodes.find((node) => node.id === id)
}

function getLineCoords(edge: GraphEdgeData) {
  const from = getNodeById(edge.from)
  const to = getNodeById(edge.to)
  if (!from || !to) return null
  const dx = to.x - from.x
  const dy = to.y - from.y
  const sourceOffset = nodeBoundaryOffset(from, dx, dy, 2)
  const targetOffset = nodeBoundaryOffset(to, -dx, -dy, 7)
  return {
    x1: from.x + sourceOffset.x,
    y1: from.y + sourceOffset.y,
    x2: to.x + targetOffset.x,
    y2: to.y + targetOffset.y,
  }
}

function getEdgeLabelCoords(edge: GraphEdgeData) {
  const coords = getLineCoords(edge)
  if (!coords) return null
  return {
    x: (coords.x1 + coords.x2) / 2,
    y: (coords.y1 + coords.y2) / 2 - 5,
  }
}

function handleWheel(event: WheelEvent) {
  event.preventDefault()
  const delta = event.deltaY > 0 ? -0.08 : 0.08
  scale.value = Math.min(maxScale, Math.max(minScale, scale.value + delta))
}

function zoomIn() {
  scale.value = Math.min(maxScale, Number((scale.value + scaleStep).toFixed(2)))
}

function zoomOut() {
  scale.value = Math.max(minScale, Number((scale.value - scaleStep).toFixed(2)))
}

function handlePointerDown(event: PointerEvent) {
  if ((event.target as Element).closest('.platform-node')) return
  if ((event.target as Element).closest('.platform-network-line, .platform-network-hit-area')) return
  isPanning.value = true
  panStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: panX.value,
    panY: panY.value,
  }
  containerRef.value?.setPointerCapture(event.pointerId)
}

function handlePointerMove(event: PointerEvent) {
  if (!isPanning.value) return
  panX.value = panStart.value.panX + (event.clientX - panStart.value.x)
  panY.value = panStart.value.panY + (event.clientY - panStart.value.y)
}

function handlePointerUp(event: PointerEvent) {
  isPanning.value = false
  containerRef.value?.releasePointerCapture(event.pointerId)
}

function handleNodeClick(node: GraphNodeData) {
  emit('selectNode', node)
}

function handleEdgeClick(edge: GraphEdgeData) {
  if (!isEdgeActive(edge)) return
  emit('selectEdge', edge)
}

function resetView() {
  scale.value = 1
  panX.value = 0
  panY.value = 0
}

onMounted(() => {
  containerRef.value?.addEventListener('wheel', handleWheel, { passive: false })
})

onUnmounted(() => {
  containerRef.value?.removeEventListener('wheel', handleWheel)
})
</script>

<template>
  <div ref="containerRef" class="kg-graph-viewport">
    <svg
      class="kg-graph-canvas platform-svg"
      :viewBox="viewBox"
      role="img"
      :aria-label="ariaLabel"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="handlePointerUp"
      @pointerleave="handlePointerUp"
    >
      <defs>
        <marker id="kg-graph-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 8 4 L 0 8 z" />
        </marker>
      </defs>
      <g :transform="transform">
        <g class="platform-network-lines">
          <line
            v-for="edge in edges"
            :key="`${edge.id}-base`"
            :x1="getLineCoords(edge)?.x1"
            :y1="getLineCoords(edge)?.y1"
            :x2="getLineCoords(edge)?.x2"
            :y2="getLineCoords(edge)?.y2"
            :class="{ 'is-dimmed': !isEdgeActive(edge) }"
          />
        </g>
        <template v-for="edge in edges" :key="edge.id">
          <line
            v-if="getLineCoords(edge)"
            :class="edgeClass(edge)"
            :x1="getLineCoords(edge)!.x1"
            :y1="getLineCoords(edge)!.y1"
            :x2="getLineCoords(edge)!.x2"
            :y2="getLineCoords(edge)!.y2"
            :marker-end="nodeShape === 'circle' ? undefined : 'url(#kg-graph-arrow)'"
            @click.stop="handleEdgeClick(edge)"
          />
          <line
            v-if="getLineCoords(edge)"
            class="platform-network-hit-area"
            :x1="getLineCoords(edge)!.x1"
            :y1="getLineCoords(edge)!.y1"
            :x2="getLineCoords(edge)!.x2"
            :y2="getLineCoords(edge)!.y2"
            @click.stop="handleEdgeClick(edge)"
          />
          <text
            v-if="getEdgeLabelCoords(edge)"
            class="platform-network-label"
            :class="{ 'is-selected': selectedEdgeId === edge.id, 'is-dimmed': !isEdgeActive(edge) }"
            :x="getEdgeLabelCoords(edge)!.x"
            :y="getEdgeLabelCoords(edge)!.y"
          >{{ edge.label }}</text>
        </template>
        <g
          v-for="node in nodes"
          :key="node.id"
          :class="nodeClass(node)"
          :transform="`translate(${node.x} ${node.y})`"
          @click.stop="handleNodeClick(node)"
        >
          <title>{{ node.label }}｜{{ node.entityType }}｜{{ node.relations }}</title>
          <circle
            v-if="nodeShape === 'circle'"
            class="node-shape"
            :r="node.level === 0 ? 30 : 23"
          />
          <rect
            v-else
            class="node-shape"
            :x="-nodeWidth(node) / 2"
            :y="-nodeHeight(node) / 2"
            :width="nodeWidth(node)"
            :height="nodeHeight(node)"
            rx="4"
          />
          <text
            class="platform-node__title"
            :y="nodeShape === 'circle' ? (node.level === 0 ? 44 : 37) : -5"
          >{{ node.label }}</text>
          <text
            v-if="nodeShape !== 'circle'"
            class="platform-node__meta"
            y="13"
          >{{ node.entityType }}</text>
        </g>
      </g>
    </svg>
    <div class="kg-graph-map-controls" aria-label="图谱视图控制">
      <a-tooltip content="缩小" position="top">
        <button
          class="kg-graph-map-controls__button"
          type="button"
          aria-label="缩小图谱"
          :disabled="scale <= minScale"
          @click="zoomOut"
        >
          <IconMinus />
        </button>
      </a-tooltip>
      <a-slider
        v-model="scale"
        class="kg-graph-map-controls__slider"
        :min="minScale"
        :max="maxScale"
        :step="0.05"
        :show-tooltip="false"
        aria-label="图谱缩放比例"
      />
      <a-tooltip content="放大" position="top">
        <button
          class="kg-graph-map-controls__button"
          type="button"
          aria-label="放大图谱"
          :disabled="scale >= maxScale"
          @click="zoomIn"
        >
          <IconPlus />
        </button>
      </a-tooltip>
      <span class="kg-graph-map-controls__divider" aria-hidden="true"></span>
      <a-tooltip content="恢复初始视图" position="top">
        <button
          class="kg-graph-map-controls__button"
          type="button"
          aria-label="恢复图谱初始视图"
          @click="resetView"
        >
          <IconFullscreen />
        </button>
      </a-tooltip>
    </div>
  </div>
</template>

<style scoped>
.kg-graph-viewport {
  position: relative;
  height: 100%;
  min-height: 340px;
  overflow: hidden;
}

.kg-graph-map-controls {
  position: absolute;
  z-index: 3;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  width: max-content;
  max-width: calc(100% - 32px);
  min-height: 40px;
  padding: 6px 8px;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 4px 16px rgba(29, 33, 41, 0.12);
  backdrop-filter: blur(6px);
}

.kg-graph-map-controls__divider {
  flex: none;
  width: 1px;
  height: 20px;
  margin: 0 2px;
  background: #e5e6eb;
}

.kg-graph-map-controls__button {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #4e5969;
  font-size: 16px;
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.kg-graph-map-controls__button:hover:not(:disabled) {
  background: #f2f3f5;
  color: #165dff;
}

.kg-graph-map-controls__button:focus-visible {
  outline: 2px solid rgba(22, 93, 255, 0.28);
  outline-offset: 1px;
}

.kg-graph-map-controls__button:disabled {
  color: #c9cdd4;
  cursor: not-allowed;
}

.kg-graph-map-controls__slider {
  width: 104px;
  margin: 0 2px;
}

.kg-graph-map-controls__slider :deep(.arco-slider-bar) {
  background: #165dff;
}

.kg-graph-map-controls__slider :deep(.arco-slider-btn) {
  top: 50%;
  transform: translate(-50%, -50%);
}

.platform-svg {
  height: 100%;
  width: 100%;
  min-height: 0;
  display: block;
  cursor: grab;
  touch-action: none;
  background-color: #fff;
  background-image: radial-gradient(circle, #e5e6eb 0.7px, transparent 0.8px);
  background-size: 16px 16px;
}

.platform-svg:active {
  cursor: grabbing;
}

.platform-network-lines line {
  stroke: rgba(148, 163, 184, 0.28);
  stroke-width: 0.9;
}

.platform-network-lines line.is-dimmed {
  opacity: 0.18;
}

.platform-network-line {
  stroke: #a9b4c5;
  stroke-width: 1.15;
  cursor: pointer;
}

.platform-svg marker path {
  fill: #a9b4c5;
}

.platform-network-line.is-dimmed {
  opacity: 0.18;
  cursor: default;
}

.platform-network-line.is-selected {
  stroke: #165dff;
  stroke-width: 2;
  filter: drop-shadow(0 0 4px rgba(22, 93, 255, 0.22));
}

.platform-network-line.is-primary,
.platform-network-line.is-green,
.platform-network-line.is-orange,
.platform-network-line.is-purple {
  stroke: #a9b4c5;
}

.platform-network-label {
  fill: #6b778c;
  font-size: 9px;
  font-weight: 400;
  text-anchor: middle;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.96);
  stroke-width: 4px;
  stroke-linejoin: round;
  pointer-events: none;
}

.platform-network-label.is-selected {
  fill: #165dff;
  font-weight: 600;
}

.platform-network-label.is-dimmed {
  opacity: 0.18;
}

.platform-network-hit-area {
  stroke: transparent;
  stroke-width: 18;
  cursor: pointer;
  pointer-events: stroke;
}

.platform-node {
  cursor: pointer;
}

.platform-node .node-shape {
  fill: #eef5ff;
  stroke: #8fb9ef;
  stroke-width: 1;
  filter: drop-shadow(0 2px 4px rgba(29, 33, 41, 0.08));
  transition: stroke-width 0.15s ease, filter 0.15s ease, transform 0.15s ease;
}

.platform-node--main .node-shape,
.platform-node.is-main .node-shape,
.platform-node.is-expert .node-shape {
  fill: #eef5ff;
  stroke: #8fb9ef;
}
.platform-node.is-org .node-shape,
.platform-node.is-company .node-shape {
  fill: #effaf1;
  stroke: #8fd49b;
}
.platform-node.is-paper .node-shape {
  fill: #f7f1ff;
  stroke: #c5a2ec;
}
.platform-node.is-project .node-shape {
  fill: #fff7e8;
  stroke: #e8c27a;
}
.platform-node.is-event .node-shape {
  fill: #fff0f6;
  stroke: #e9a4c0;
}
.platform-node.is-topic .node-shape {
  fill: #f1f3ff;
  stroke: #9ca8ed;
}

.platform-node.is-selected .node-shape {
  stroke: #165dff;
  stroke-width: 1.8;
  filter: drop-shadow(0 0 7px rgba(22, 93, 255, 0.2));
}

.platform-node text {
  text-anchor: middle;
  dominant-baseline: middle;
  pointer-events: none;
}

.platform-node__title {
  fill: #1d2129;
  font-size: 11px;
  font-weight: 600;
}

.platform-node__meta {
  fill: #86909c;
  font-size: 9px;
  font-weight: 400;
}

.platform-node.is-expert .platform-node__title,
.platform-node.is-main .platform-node__title {
  fill: #2458a6;
}

.platform-node.is-org .platform-node__title,
.platform-node.is-company .platform-node__title {
  fill: #218a39;
}

.platform-node.is-paper .platform-node__title {
  fill: #7a35b8;
}

.platform-node.is-project .platform-node__title {
  fill: #b56b00;
}

.platform-node.is-event .platform-node__title {
  fill: #b93d72;
}

.platform-node.is-topic .platform-node__title {
  fill: #4a5cc4;
}

.platform-node--center .node-shape {
  fill: #f7f1ff;
  stroke: #b68adf;
  stroke-width: 1.5;
  filter: drop-shadow(0 3px 7px rgba(122, 53, 184, 0.14));
}

.platform-node--center .platform-node__title {
  fill: #7a35b8;
}

.platform-node.is-solid-circle .node-shape {
  stroke: #fff;
  stroke-width: 2;
  filter: drop-shadow(0 2px 4px rgba(29, 33, 41, 0.16));
}

.platform-node.is-solid-circle.is-main .node-shape,
.platform-node.is-solid-circle.is-expert .node-shape { fill: #2489e8; }
.platform-node.is-solid-circle.is-org .node-shape,
.platform-node.is-solid-circle.is-company .node-shape { fill: #38c908; }
.platform-node.is-solid-circle.is-paper .node-shape,
.platform-node.is-solid-circle.is-topic .node-shape { fill: #7426d8; }
.platform-node.is-solid-circle.is-project .node-shape { fill: #ffa916; }
.platform-node.is-solid-circle.is-event .node-shape { fill: #ef2194; }

.platform-node.is-solid-circle .platform-node__title {
  fill: #5f6b7a;
  font-size: 11px;
  font-weight: 500;
}

.platform-node.is-solid-circle.platform-node--center .platform-node__title {
  fill: #1d2129;
  font-size: 12px;
  font-weight: 700;
}

</style>
