<script setup lang="ts">
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
    showEdgeLabelButton?: boolean
  }>(),
  {
    activeCategories: null,
    selectedNodeId: null,
    selectedEdgeId: null,
    ariaLabel: '知识图谱',
    showEdgeLabelButton: false,
  },
)

const emit = defineEmits<{
  selectNode: [node: GraphNodeData]
  selectEdge: [edge: GraphEdgeData]
}>()

const viewBox = '0 0 760 430'
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const containerRef = ref<HTMLElement | null>(null)

const transform = computed(() => `translate(${panX.value} ${panY.value}) scale(${scale.value})`)

const edgeToneMap:
  Record<string, string> = {
    论文合作:
      'is-primary',

    同事关系:
      'is-green',

    校友关系:
      'is-green',

    企业关联:
      'is-orange',

    产业事件:
      'is-purple',

    直接关系:
      'is-primary',

    间接关系:
      'is-purple',
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

function nodeRadius(
  node: GraphNodeData,
) {
  if (node.level === 0) {
    return node.radius ?? 16
  }

  return Math.min(
    node.radius ?? 12,
    13,
  )
}

function nodeShape(_node: GraphNodeData) {
  return 'circle'
}

function polygonPoints(node: GraphNodeData) {
  const radius = nodeRadius(node)
  if (nodeShape(node) === 'diamond') {
    return `0,${-radius} ${radius},0 0,${radius} ${-radius},0`
  }
  return [
    `${-radius * 0.86},${-radius * 0.5}`,
    `0,${-radius}`,
    `${radius * 0.86},${-radius * 0.5}`,
    `${radius * 0.86},${radius * 0.5}`,
    `0,${radius}`,
    `${-radius * 0.86},${radius * 0.5}`,
  ].join(' ')
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
  const distance = Math.hypot(dx, dy) || 1
  const unitX = dx / distance
  const unitY = dy / distance
  const sourceOffset = nodeRadius(from) + 3
  const targetOffset = nodeRadius(to) + 7
  return {
    x1: from.x + unitX * sourceOffset,
    y1: from.y + unitY * sourceOffset,
    x2: to.x - unitX * targetOffset,
    y2: to.y - unitY * targetOffset,
  }
}

function handleWheel(event: WheelEvent) {
  event.preventDefault()
  const delta = event.deltaY > 0 ? -0.08 : 0.08
  scale.value = Math.min(2.2, Math.max(0.6, scale.value + delta))
}

function handlePointerDown(event: PointerEvent) {
  if ((event.target as Element).closest('.platform-node')) return
  if ((event.target as Element).closest('.platform-network-line, .platform-network-hit-area')) return
  if ((event.target as Element).closest('.edge-label-button')) return
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

/**
 * 边上的"增加标签"按钮：每条边可挂一个用户自定义标签，
 * 初始展示"增加标签"，点击后弹窗输入，确认后按钮展示新标签。
 *
 * 状态仅保留在前端，不持久化、不上行后端。
 */
const edgeLabels = ref(new Map<string, string>())
const labelDialogState = ref<{ edgeId: string; input: string } | null>(null)

function getEdgeLabel(edge: GraphEdgeData) {
  return edgeLabels.value.get(edge.id) ?? ''
}

function edgeMidpoint(edge: GraphEdgeData) {
  const coords = getLineCoords(edge)
  if (!coords) return null
  return { x: (coords.x1 + coords.x2) / 2, y: (coords.y1 + coords.y2) / 2 }
}

function edgeButtonText(edge: GraphEdgeData) {
  return getEdgeLabel(edge) || '增加标签'
}

function edgeButtonWidth(edge: GraphEdgeData) {
  const text = edgeButtonText(edge)
  let w = 0
  for (const ch of text) {
    w += /[一-鿿]/.test(ch) ? 12 : 7
  }
  return Math.max(64, w + 18)
}

function openLabelDialog(edge: GraphEdgeData) {
  labelDialogState.value = {
    edgeId: edge.id,
    input: getEdgeLabel(edge),
  }
}

function confirmLabelDialog() {
  const state = labelDialogState.value
  if (!state) return
  const trimmed = state.input.trim()
  if (trimmed) {
    edgeLabels.value.set(state.edgeId, trimmed)
  } else {
    edgeLabels.value.delete(state.edgeId)
  }
  labelDialogState.value = null
}

function cancelLabelDialog() {
  labelDialogState.value = null
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
    <div class="kg-graph-toolbar">
      <button type="button" @click="scale = Math.min(2.2, scale + 0.15)">放大</button>
      <button type="button" @click="scale = Math.max(0.6, scale - 0.15)">缩小</button>
      <button type="button" @click="resetView">重置</button>
    </div>
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
          <g
            v-if="showEdgeLabelButton && edgeMidpoint(edge)"
            :transform="`translate(${edgeMidpoint(edge)!.x} ${edgeMidpoint(edge)!.y})`"
            class="edge-label-button"
            :class="{ 'is-labeled': !!getEdgeLabel(edge) }"
            @click.stop="openLabelDialog(edge)"
          >
            <rect
              :x="-edgeButtonWidth(edge) / 2"
              y="-11"
              :width="edgeButtonWidth(edge)"
              height="22"
              rx="11"
            />
            <text>{{ edgeButtonText(edge) }}</text>
          </g>
        </template>
        <g
          v-for="node in nodes"
          :key="node.id"
          :class="nodeClass(node)"
          :transform="`translate(${node.x} ${node.y})`"
          @click.stop="handleNodeClick(node)"
        >
          <title>{{ node.label }}｜{{ node.entityType }}｜{{ node.relations }}</title>
          <circle v-if="nodeShape(node) === 'circle'" class="node-shape" :r="nodeRadius(node)" />
          <rect
            v-else-if="nodeShape(node) === 'rect'"
            class="node-shape"
            :x="-nodeRadius(node)"
            :y="-nodeRadius(node)"
            :width="nodeRadius(node) * 2"
            :height="nodeRadius(node) * 2"
            rx="8"
          />
          <rect
            v-else-if="nodeShape(node) === 'pill'"
            class="node-shape"
            :x="-nodeRadius(node) * 1.15"
            :y="-nodeRadius(node) * 0.72"
            :width="nodeRadius(node) * 2.3"
            :height="nodeRadius(node) * 1.44"
            rx="12"
          />
          <polygon v-else class="node-shape" :points="polygonPoints(node)" />
          <text>{{ node.label }}</text>
        </g>
      </g>
    </svg>
    <div
      v-if="labelDialogState"
      class="edge-label-modal"
      @click.self="cancelLabelDialog"
    >
      <section class="edge-label-modal__panel" role="dialog" aria-modal="true" aria-label="输入边标签">
        <header class="edge-label-modal__header">
          <h2>请输入标签</h2>
          <button type="button" aria-label="关闭" @click="cancelLabelDialog">×</button>
        </header>
        <div class="edge-label-modal__body">
          <input
            v-model="labelDialogState.input"
            type="text"
            placeholder="请输入标签内容"
            maxlength="20"
            @keyup.enter="confirmLabelDialog"
          />
        </div>
        <footer class="edge-label-modal__actions">
          <button type="button" class="is-ghost" @click="cancelLabelDialog">取消</button>
          <button type="button" class="is-primary" @click="confirmLabelDialog">增加标签</button>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.kg-graph-viewport {
  display: flex;
  flex-direction: column;
  height: calc(100% - 45px);
  min-height: 340px;
}

.kg-graph-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(191, 215, 250, 0.96);
  background: rgba(248, 252, 255, 0.92);
}

.kg-graph-toolbar button {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
}

.kg-graph-toolbar span {
  margin-left: auto;
  color: var(--text-tertiary);
  font-size: 12px;
}

.platform-svg {
  flex: 1;
  width: 100%;
  min-height: 0;
  display: block;
  cursor: grab;
  touch-action: none;
  background:
    linear-gradient(#e8f1ff 1px, transparent 1px),
    linear-gradient(90deg, #e8f1ff 1px, transparent 1px),
    radial-gradient(circle at 22% 18%, rgba(22, 93, 255, 0.08), transparent 34%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(239, 247, 255, 0.94));
  background-size: 28px 28px, 28px 28px, auto, auto;
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
  stroke: rgba(100, 116, 139, 0.52);
  stroke-width: 1.1;
  cursor: pointer;
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
  stroke: rgba(100, 116, 139, 0.52);
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
  fill: var(--node-expert, #1e8ff3);
  stroke: #fff;
  stroke-width: 1.2;
  filter: drop-shadow(0 2px 5px rgba(53, 77, 112, 0.16));
  transition: stroke-width 0.15s ease, filter 0.15s ease, transform 0.15s ease;
}

.platform-node--main .node-shape,
.platform-node.is-main .node-shape,
.platform-node.is-expert .node-shape { fill: #1e8ff3; }
.platform-node.is-org .node-shape,
.platform-node.is-company .node-shape { fill: #48c914; }
.platform-node.is-paper .node-shape { fill: #762bd7; }
.platform-node.is-project .node-shape { fill: #ffad17; }
.platform-node.is-event .node-shape { fill: #eb2aa3; }
.platform-node.is-topic .node-shape { fill: #2f6bff; }

.platform-node.is-selected .node-shape {
  stroke: #10264c;
  stroke-width: 2.2;
  filter: drop-shadow(0 0 8px rgba(22, 93, 255, 0.28));
}

.platform-node text {
  fill: #42526b;
  font-size: 10px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: hanging;
  pointer-events: none;
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.92);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.platform-node--main text,
.platform-node.is-main text {
  fill: #10264c;
  font-size: 11px;
  font-weight: 600;
  transform: translateY(18px);
  stroke: rgba(255, 255, 255, 0.94);
}

.platform-node:not(.platform-node--main):not(.is-main) text {
  transform: translateY(16px);
}

.platform-node.is-expert .node-shape {
  fill: #1e8ff3;
}

.platform-node.is-org .node-shape,
.platform-node.is-company .node-shape {
  fill: #48c914;
}

.platform-node.is-paper .node-shape {
  fill: #762bd7;
}

.platform-node.is-project .node-shape {
  fill: #ffad17;
}

.platform-node.is-event .node-shape {
  fill: #eb2aa3;
}

.platform-node.is-topic .node-shape {
  fill: #2f6bff;
}

.platform-node.is-chain .node-shape {
  fill: #14b8a6;
}

.platform-node.is-field .node-shape {
  fill: #2f6bff;
}

.platform-node.is-source .node-shape {
  fill: #64748b;
}

.platform-node--center .node-shape {
  stroke: #0b5fc6;
  stroke-width: 2.6;
  filter:
    drop-shadow(
      0 4px 8px
      rgba(30, 143, 243, 0.22)
    );
}

.edge-label-button {
  cursor: pointer;
}

.edge-label-button rect {
  fill: rgba(248, 252, 255, 0.95);
  stroke: rgba(22, 93, 255, 0.55);
  stroke-width: 1;
  filter: drop-shadow(0 1px 3px rgba(53, 77, 112, 0.16));
  transition: fill 0.15s ease, stroke 0.15s ease;
}

.edge-label-button:hover rect {
  fill: #165dff;
  stroke: #165dff;
}

.edge-label-button text {
  fill: #165dff;
  font-size: 11px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
  pointer-events: none;
  user-select: none;
}

.edge-label-button:hover text {
  fill: #fff;
}

.edge-label-button.is-labeled rect {
  fill: rgba(22, 93, 255, 0.12);
  stroke: #165dff;
}

.edge-label-button.is-labeled text {
  fill: #10264c;
  font-weight: 600;
}

.edge-label-modal {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(16, 38, 76, 0.42);
  backdrop-filter: blur(2px);
}

.edge-label-modal__panel {
  width: min(360px, 100%);
  border: 1px solid rgba(167, 201, 250, 0.96);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-panel);
  overflow: hidden;
}

.edge-label-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(90deg, rgba(22, 93, 255, 0.08), transparent 48%);
}

.edge-label-modal__header h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  line-height: 24px;
}

.edge-label-modal__header button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 999px;
  background: var(--surface-subtle);
  color: var(--text-secondary);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.edge-label-modal__body {
  padding: 16px;
}

.edge-label-modal__body input {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
}

.edge-label-modal__body input:focus {
  outline: none;
  border-color: #165dff;
}

.edge-label-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border);
}

.edge-label-modal__actions button {
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.edge-label-modal__actions button.is-primary {
  border-color: #165dff;
  background: #165dff;
  color: #fff;
}

.edge-label-modal__actions button.is-ghost {
  background: var(--surface-subtle);
  color: var(--text-secondary);
}
</style>
