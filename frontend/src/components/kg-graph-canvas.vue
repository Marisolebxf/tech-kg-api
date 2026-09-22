<script setup lang="ts">
import { IconFullscreen, IconMinus, IconPlus } from '@arco-design/web-vue/es/icon'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { useForceLayout, type ForceLayoutOptions } from '../composables/use-force-layout'
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
    layoutOptions?: ForceLayoutOptions
    showEdgeLabels?: boolean
    uniformNodeSize?: boolean
  }>(),
  {
    activeCategories: null,
    selectedNodeId: null,
    selectedEdgeId: null,
    ariaLabel: '知识图谱',
    nodeShape: 'circle',
    showEdgeLabels: false,
    uniformNodeSize: false,
  },
)

const emit = defineEmits<{
  selectNode: [node: GraphNodeData]
  selectEdge: [edge: GraphEdgeData]
}>()

/** 画布坐标空间尺寸（viewBox）。放大坐标空间给节点更多活动场地，
 *  1.0 倍下整图仍可见，节点不会被推到边界墙上堆成长方形。 */
const CANVAS_W = 960
const CANVAS_H = 540
const CX = CANVAS_W / 2
const CY = CANVAS_H / 2
const viewBox = `0 0 ${CANVAS_W} ${CANVAS_H}`
const minScale = 0.6
const maxScale = 2.2
const scaleStep = 0.1
/** 初始（及复位）缩放：1.0 倍，整图可见并居中。 */
const DEFAULT_SCALE = 1

/** 给定缩放比例，返回让画布内容居中所需的平移量（缩放以左上原点为基准）。 */
function centeredPan(s: number) {
  return { x: CX * (1 - s), y: CY * (1 - s) }
}

const scale = ref(DEFAULT_SCALE)
const initPan = centeredPan(DEFAULT_SCALE)
const panX = ref(initPan.x)
const panY = ref(initPan.y)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const containerRef = ref<HTMLElement | null>(null)

const transform = computed(() => `translate(${panX.value} ${panY.value}) scale(${scale.value})`)

const { laidOutNodes } = useForceLayout(
  () => props.nodes,
  () => props.edges,
  () => ({ ...props.layoutOptions, nodeShape: props.nodeShape }),
)

/** 连线端点一次性算好（O(V+E)，id→端点查表）。此前模板里每条边要反复
 *  调 getLineCoords：每边十余次 laidOutNodes.find（O(n) 查找），平移/缩放
 *  每帧全量重算，节点一多拖动就明显掉帧。 */
const lineCoords = computed(() => {
  const nodeById = new Map(laidOutNodes.value.map((node) => [node.id, node]))
  const map = new Map<string, { x1: number; y1: number; x2: number; y2: number }>()
  for (const edge of props.edges) {
    const from = nodeById.get(edge.from)
    const to = nodeById.get(edge.to)
    if (!from || !to) continue
    const dx = to.x - from.x
    const dy = to.y - from.y
    // gap=0：线端点正好落在节点边界；节点绘制在线之上，
    // 任何亚像素溢出被节点覆盖，视觉上线与节点严丝合缝无间隙。
    const sourceOffset = nodeBoundaryOffset(from, dx, dy, 0)
    const targetOffset = nodeBoundaryOffset(to, -dx, -dy, 0)
    map.set(edge.id, {
      x1: from.x + sourceOffset.x,
      y1: from.y + sourceOffset.y,
      x2: to.x + targetOffset.x,
      y2: to.y + targetOffset.y,
    })
  }
  return map
})

function coordsOf(edge: GraphEdgeData) {
  return lineCoords.value.get(edge.id) ?? null
}

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
   * 中心节点标记为 --center（更大半径/光环/加粗标题），
   * uniform-node-size 下仍保留中心强调，只统一其余节点尺寸。
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
  return Math.min(node.level === 0 && !props.uniformNodeSize ? 164 : 144, preferred)
}

function nodeHeight(node: GraphNodeData) {
  return node.level === 0 && !props.uniformNodeSize ? 54 : 46
}

/** 圆形节点半径，渲染与连线偏移共用，避免节点/连线半径不一致。
 *  节点自带 radius（如 PageRank 重要性分值映射）时优先使用；
 *  uniform-node-size 只统一非中心节点，中心节点仍放大以区分。 */
function nodeRadius(node: GraphNodeData) {
  if (node.radius !== undefined && !props.uniformNodeSize) return node.radius
  if (node.level === 0) return props.uniformNodeSize ? 24 : 20
  return 15
}

/** 标签过长时截断，防止长文本撑爆画布。 */
/** 圆形节点标签最多两行、每行约 10 字，超长不再单行截断成省略号；
 * 矩形节点保持单行（下方有 meta 行，两行会重叠）。 */
function labelLines(node: GraphNodeData): string[] {
  const label = node.label || ''
  const perLine = 10
  if (props.nodeShape !== 'circle' || label.length <= perLine) {
    const max = 12
    return [label.length > max ? `${label.slice(0, max)}…` : label]
  }
  const first = label.slice(0, perLine)
  const rest = label.slice(perLine)
  // 第二行超过一行仍截断（极少见：30+ 字长名），完整名称在 title 悬浮提示
  const second = rest.length > perLine ? `${rest.slice(0, perLine)}…` : rest
  return [first, second]
}

/** 边名称过长时截断，防止长关系名压住相邻元素；ASCII 名称（如 AUTHORED_BY）字符窄，放宽上限。 */
function displayEdgeLabel(edge: GraphEdgeData) {
  const label = edge.label
  const max = /^[\x20-\x7e]+$/.test(label) ? 16 : 8
  return label.length > max ? `${label.slice(0, max)}…` : label
}

function nodeBoundaryOffset(node: GraphNodeData, dx: number, dy: number, gap = 0) {
  if (props.nodeShape === 'circle') {
    const length = Math.hypot(dx, dy) || 1
    const radius = nodeRadius(node) + gap
    return { x: (dx / length) * radius, y: (dy / length) * radius }
  }
  const halfWidth = nodeWidth(node) / 2 + gap
  const halfHeight = nodeHeight(node) / 2 + gap
  const factor = 1 / Math.max(Math.abs(dx) / halfWidth, Math.abs(dy) / halfHeight, 0.0001)
  return { x: dx * factor, y: dy * factor }
}

/** 拖动判定阈值（屏幕像素）：按下后位移超过它才算拖动平移，以内仍视为
 *  点击——保证从节点/边上发起的拖动能平移画布，而同一位置的单击选择不受影响。 */
const DRAG_THRESHOLD = 3
/** 本次手势是否已判定为拖动：拖动结束后的 click 不再触发节点/边选中。 */
let didPan = false
/** 是否处于按下（未超阈值）状态：阈值内的移动不更新平移。 */
let pointerDown = false
let downX = 0
let downY = 0
/** 高轮询率鼠标的 pointermove 可能比刷新率更密：待应用的指针位置先存这里，
 *  每帧最多写一次响应式状态，避免每个事件都触发 Vue 全量重渲染造成拖动掉帧。 */
let pendingClient: { x: number; y: number } | null = null
let panRafId = 0

function applyPanInRaf(x: number, y: number) {
  pendingClient = { x, y }
  if (panRafId) return
  panRafId = requestAnimationFrame(() => {
    panRafId = 0
    const pending = pendingClient
    pendingClient = null
    if (!pending || !isPanning.value) return
    panX.value = panStart.value.panX + (pending.x - panStart.value.x)
    panY.value = panStart.value.panY + (pending.y - panStart.value.y)
  })
}

/**
 * 以 (ax, ay)（viewBox 坐标）为锚点缩放到 newScale，
 * 保持锚点下的内容不动，避免放大时内容被推出视口外看不见。
 */
function zoomAt(newScale: number, ax: number, ay: number) {
  const s = scale.value
  if (s === newScale) return
  panX.value = panX.value + (ax - panX.value) * (1 - newScale / s)
  panY.value = panY.value + (ay - panY.value) * (1 - newScale / s)
  scale.value = newScale
}

function handleWheel(event: WheelEvent) {
  event.preventDefault()
  const delta = event.deltaY > 0 ? -0.08 : 0.08
  const newScale = Math.min(maxScale, Math.max(minScale, scale.value + delta))
  const rect = containerRef.value?.getBoundingClientRect()
  const ax = rect ? ((event.clientX - rect.left) / rect.width) * CANVAS_W : CX
  const ay = rect ? ((event.clientY - rect.top) / rect.height) * CANVAS_H : CY
  zoomAt(newScale, ax, ay)
}

function zoomIn() {
  zoomAt(Math.min(maxScale, Number((scale.value + scaleStep).toFixed(2))), CX, CY)
}

function zoomOut() {
  zoomAt(Math.max(minScale, Number((scale.value - scaleStep).toFixed(2))), CX, CY)
}

/** 滑块直接设值时，同样以画布中心为锚点，保持居中缩放。 */
function setScale(v: number | [number, number]) {
  const next = Array.isArray(v) ? v[0] : v
  if (next == null) return
  zoomAt(Number(next), CX, CY)
}

function handlePointerDown(event: PointerEvent) {
  // 控制条上的按下不触发平移；节点/边上的按下不再排除——超阈值即接管为拖动，
  // 让悬停在实体/关系上也能长按拖动图谱（见 DRAG_THRESHOLD 注释）。
  if ((event.target as Element).closest('.kg-graph-map-controls')) return
  pointerDown = true
  didPan = false
  downX = event.clientX
  downY = event.clientY
  panStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: panX.value,
    panY: panY.value,
  }
}

function handlePointerMove(event: PointerEvent) {
  if (!pointerDown) return
  if (!isPanning.value) {
    if (Math.hypot(event.clientX - downX, event.clientY - downY) < DRAG_THRESHOLD) return
    isPanning.value = true
    didPan = true
    // 拖动确定后才捕获指针：拖出画布范围仍持续平移；
    // 捕获前松手则 click 落回原目标，节点/边单击选择保持原生行为。
    containerRef.value?.setPointerCapture?.(event.pointerId)
  }
  applyPanInRaf(event.clientX, event.clientY)
}

function handlePointerUp(event: PointerEvent) {
  pointerDown = false
  isPanning.value = false
  pendingClient = null
  if (panRafId) {
    cancelAnimationFrame(panRafId)
    panRafId = 0
  }
  if (containerRef.value?.hasPointerCapture?.(event.pointerId)) {
    containerRef.value?.releasePointerCapture?.(event.pointerId)
  }
}

function handleNodeClick(node: GraphNodeData) {
  // 刚完成拖动平移（从节点上发起）的 click 不触发选中
  if (didPan) return
  emit('selectNode', node)
}

function handleEdgeClick(edge: GraphEdgeData) {
  if (didPan) return
  if (!isEdgeActive(edge)) return
  emit('selectEdge', edge)
}

function resetView() {
  scale.value = DEFAULT_SCALE
  const p = centeredPan(DEFAULT_SCALE)
  panX.value = p.x
  panY.value = p.y
}

onMounted(() => {
  containerRef.value?.addEventListener('wheel', handleWheel, { passive: false })
})

onUnmounted(() => {
  containerRef.value?.removeEventListener('wheel', handleWheel)
  if (panRafId) cancelAnimationFrame(panRafId)
})
</script>

<template>
  <div
    ref="containerRef"
    class="kg-graph-viewport"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointerleave="handlePointerUp"
  >
    <svg
      class="kg-graph-canvas platform-svg"
      :viewBox="viewBox"
      role="img"
      :aria-label="ariaLabel"
    >
      <g :transform="transform">
        <g class="platform-network-lines">
          <line
            v-for="edge in edges"
            :key="`${edge.id}-base`"
            :x1="coordsOf(edge)?.x1"
            :y1="coordsOf(edge)?.y1"
            :x2="coordsOf(edge)?.x2"
            :y2="coordsOf(edge)?.y2"
            :class="{ 'is-dimmed': !isEdgeActive(edge) }"
          />
        </g>
        <template v-for="edge in edges" :key="edge.id">
          <line
            v-if="coordsOf(edge)"
            :class="edgeClass(edge)"
            :x1="coordsOf(edge)!.x1"
            :y1="coordsOf(edge)!.y1"
            :x2="coordsOf(edge)!.x2"
            :y2="coordsOf(edge)!.y2"
            @click.stop="handleEdgeClick(edge)"
          />
          <line
            v-if="coordsOf(edge)"
            class="platform-network-hit-area"
            :x1="coordsOf(edge)!.x1"
            :y1="coordsOf(edge)!.y1"
            :x2="coordsOf(edge)!.x2"
            :y2="coordsOf(edge)!.y2"
            @click.stop="handleEdgeClick(edge)"
          />
          <text
            v-if="showEdgeLabels && edge.label && coordsOf(edge)"
            :class="['platform-network-line__label', { 'is-dimmed': !isEdgeActive(edge) }]"
            :x="(coordsOf(edge)!.x1 + coordsOf(edge)!.x2) / 2"
            :y="(coordsOf(edge)!.y1 + coordsOf(edge)!.y2) / 2"
          >{{ displayEdgeLabel(edge) }}</text>
        </template>
        <g
          v-for="node in laidOutNodes"
          :key="node.id"
          :class="nodeClass(node)"
          :transform="`translate(${node.x} ${node.y})`"
          @click.stop="handleNodeClick(node)"
        >
          <title>{{ node.label }}｜{{ node.entityType }}｜{{ node.relations }}</title>
          <circle
            v-if="nodeShape === 'circle' && node.level === 0"
            class="node-halo"
            :r="nodeRadius(node) + 7"
          />
          <circle
            v-if="nodeShape === 'circle'"
            class="node-shape"
            :r="nodeRadius(node)"
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
            :y="nodeShape === 'circle' ? (nodeRadius(node) + 11 - (labelLines(node).length - 1) * 6) : -5"
          >
            <tspan
              v-for="(line, i) in labelLines(node)"
              :key="i"
              x="0"
              :dy="i === 0 ? 0 : 12"
            >{{ line }}</tspan>
          </text>
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
        :model-value="scale"
        class="kg-graph-map-controls__slider"
        :min="minScale"
        :max="maxScale"
        :step="0.05"
        :show-tooltip="false"
        aria-label="图谱缩放比例"
        @update:model-value="setScale"
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
  touch-action: none;
  cursor: grab;
}

.kg-graph-viewport:active {
  cursor: grabbing;
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
  color: #004ecc;
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
  background: #004ecc;
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

/* Reserve space for touch controls instead of covering graph content on phones. */
@media (max-width: 767px) {
  .kg-graph-viewport {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .platform-svg {
    flex: 1 1 0%;
    height: 0;
  }

  .kg-graph-map-controls {
    position: static;
    flex: none;
    align-self: center;
    width: calc(100% - 16px);
    max-width: 320px;
    min-height: 52px;
    margin: 8px;
    padding: 4px 6px;
    gap: 4px;
    transform: none;
    box-shadow: none;
  }

  .kg-graph-map-controls__button {
    width: 40px;
    height: 40px;
  }

  .kg-graph-map-controls__slider {
    flex: 1 1 104px;
    width: auto;
    min-width: 24px;
    margin-inline: 4px;
  }
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

.platform-network-line.is-dimmed {
  opacity: 0.18;
  cursor: default;
}

/* 边名称：白色描边光晕保证压在线上也清晰，不拦截点击（点击走 hit-area 线） */
.platform-network-line__label {
  fill: #4e5969;
  font-size: 8px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
  pointer-events: none;
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 3px;
  stroke-linejoin: round;
}

.platform-network-line__label.is-dimmed {
  opacity: 0.18;
}

.platform-network-line.is-selected {
  stroke: #004ecc;
  stroke-width: 2;
  filter: drop-shadow(0 0 4px rgba(22, 93, 255, 0.22));
}

.platform-network-line.is-primary,
.platform-network-line.is-green,
.platform-network-line.is-orange,
.platform-network-line.is-purple {
  stroke: #a9b4c5;
}

.platform-network-hit-area {
  stroke: transparent;
  stroke-width: 14;
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
  stroke: #004ecc;
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
  font-size: 9px;
  font-weight: 600;
}

.platform-node__meta {
  fill: #59636f;
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

.platform-node.is-solid-circle.is-main .node-shape { fill: #f43f5e; }
.platform-node.is-solid-circle.is-expert .node-shape { fill: #168cff; }
.platform-node.is-solid-circle.is-org .node-shape { fill: #0ea5a4; }
.platform-node.is-solid-circle.is-company .node-shape { fill: #36c414; }
.platform-node.is-solid-circle.is-paper .node-shape { fill: #f5b700; }
.platform-node.is-solid-circle.is-project .node-shape { fill: #ff9f0a; }
.platform-node.is-solid-circle.is-event .node-shape { fill: #d97706; }
.platform-node.is-solid-circle.is-topic .node-shape { fill: #722ed1; }
.platform-node.is-solid-circle.is-chain .node-shape { fill: #4f46e5; }
.platform-node.is-solid-circle.is-field .node-shape { fill: #a855f7; }
.platform-node.is-solid-circle.is-source .node-shape { fill: #eb2f96; }

.platform-node.is-solid-circle .platform-node__title {
  fill: #5f6b7a;
  font-size: 9px;
  font-weight: 500;
}

.platform-node.is-solid-circle.platform-node--center .platform-node__title {
  fill: #1d2129;
  font-size: 10px;
  font-weight: 700;
}

/* 中心节点强调：虚线光环外环 + 更强投影，与普通节点明显区分（circle 模式） */
.platform-node .node-halo {
  fill: none;
  stroke: #4e5969;
  stroke-width: 1.2;
  stroke-dasharray: 3 4;
  opacity: 0.55;
  pointer-events: none;
}

.platform-node.is-solid-circle.platform-node--center .node-shape {
  stroke-width: 2.5;
  filter: drop-shadow(0 3px 9px rgba(29, 33, 41, 0.28));
}

</style>
