<script setup lang="ts">
import { computed } from 'vue'

import type { DirectRelationItem, DirectRelationQueryResponse } from '../expert-direct-types'

type ReferenceNode = {
  id: string
  kind: 'institution' | 'expert-blue' | 'expert-green'
  x: number
  y: number
  width: number
  height: number
  title: string
  subtitle?: string | null
}

type ReferenceEdge = {
  key: string
  d: string
  labelLines?: string[]
  labelX: number
  labelY: number
  stroke?: string
  width?: number
  startMarker?: 'dot' | 'arrow'
  endMarker?: 'dot' | 'arrow'
}

type Point = [number, number]

type PartnerSlot = {
  x: number
  y: number
  width: number
  height: number
  labelX: number
  labelY: number
  curve: [Point, Point, Point, Point]
}

const props = defineProps<{
  title: string
  loading: boolean
  errorMessage: string
  response: DirectRelationQueryResponse | null
}>()

const VIEWBOX_WIDTH = 920
const VIEWBOX_HEIGHT = 650
const relationColor = '#7b43e6'

const items = computed<DirectRelationItem[]>(() => props.response?.items?.slice(0, 4) ?? [])
const primaryExpert = computed(() => items.value[0]?.expertA ?? null)
const primaryInstitution = computed(() => primaryExpert.value?.organization || items.value[0]?.institution || '关系归属机构')

const centerNode = {
  x: 350,
  y: 270,
  width: 220,
  height: 100,
}

const partnerSlots: PartnerSlot[] = [
  { x: 50, y: 146, width: 220, height: 100, labelX: 326, labelY: 236, curve: [[350, 320], [305, 250], [290, 206], [270, 196]] },
  { x: 650, y: 146, width: 220, height: 100, labelX: 594, labelY: 236, curve: [[570, 320], [615, 250], [630, 206], [650, 196]] },
  { x: 60, y: 434, width: 220, height: 100, labelX: 322, labelY: 398, curve: [[350, 340], [292, 382], [282, 438], [280, 488]] },
  { x: 640, y: 434, width: 220, height: 100, labelX: 598, labelY: 398, curve: [[570, 340], [628, 382], [638, 438], [640, 488]] },
]

function line(fromX: number, fromY: number, toX: number, toY: number) {
  return `M ${fromX} ${fromY} L ${toX} ${toY}`
}

function curve(
  from: [number, number],
  c1: [number, number],
  c2: [number, number],
  to: [number, number],
) {
  return `M ${from[0]} ${from[1]} C ${c1[0]} ${c1[1]}, ${c2[0]} ${c2[1]}, ${to[0]} ${to[1]}`
}

function expertTitle(prefix: string, itemIndex: number) {
  const item = items.value[itemIndex]
  if (!item) return `${prefix}：暂无`
  return `${prefix}：${item.expertB.name}`
}

function expertSubtitle(itemIndex: number) {
  const expert = items.value[itemIndex]?.expertB
  return expert?.title || expert?.organization || ''
}

function relationLines(itemIndex: number, fallback: string) {
  const item = items.value[itemIndex]
  if (!item) return [fallback]
  return [item.relationSummary || fallback, `合作论文 ${item.coPaperCount ?? 0}`]
}

const referenceNodes = computed<ReferenceNode[]>(() => {
  if (!primaryExpert.value || !items.value.length) return []

  const nodes: ReferenceNode[] = [
    {
      id: 'primary-institution',
      kind: 'institution',
      x: 338,
      y: 54,
      width: 244,
      height: 70,
      title: primaryInstitution.value,
    },
    {
      id: 'primary-expert',
      kind: 'expert-blue',
      ...centerNode,
      title: `专家A：${primaryExpert.value.name}`,
      subtitle: primaryExpert.value.title || primaryExpert.value.organization,
    },
  ]

  items.value.forEach((item, index) => {
    const slot = partnerSlots[index]
    if (!slot) return
    nodes.push({
      id: `partner-${item.expertB.expertId || index}`,
      kind: 'expert-green',
      x: slot.x,
      y: slot.y,
      width: slot.width,
      height: slot.height,
      title: expertTitle('专家B', index),
      subtitle: expertSubtitle(index),
    })
  })

  return nodes
})

const referenceEdges = computed<ReferenceEdge[]>(() => {
  if (!referenceNodes.value.length) return []

  const edges: ReferenceEdge[] = [
    {
      key: 'institution-primary',
      d: line(460, 124, 460, centerNode.y),
      labelLines: ['任职'],
      labelX: 486,
      labelY: 204,
      width: 2,
      startMarker: 'dot',
      endMarker: 'dot',
    },
  ]

  items.value.forEach((_, index) => {
    const slot = partnerSlots[index]
    if (!slot) return
    const [from, c1, c2, to] = slot.curve
    edges.push({
      key: `primary-partner-${index}`,
      d: curve(from, c1, c2, to),
      labelLines: relationLines(index, '直接关系'),
      labelX: slot.labelX,
      labelY: slot.labelY,
      width: 2,
      endMarker: 'arrow',
    })
  })

  return edges
})

function nodeStyle(node: ReferenceNode) {
  return {
    left: `${(node.x / VIEWBOX_WIDTH) * 100}%`,
    top: `${(node.y / VIEWBOX_HEIGHT) * 100}%`,
    width: `${(node.width / VIEWBOX_WIDTH) * 100}%`,
    height: `${(node.height / VIEWBOX_HEIGHT) * 100}%`,
  }
}
</script>

<template>
  <div class="direct-graph-panel">
    <div v-if="errorMessage && !items.length" class="direct-graph-panel__empty">
      <strong>查询失败</strong>
      <p>{{ errorMessage }}</p>
    </div>

    <div v-else-if="items.length" class="reference-graph">
      <svg class="reference-graph__svg" viewBox="0 0 920 650" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <marker id="direct-reference-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" :fill="relationColor"></path>
          </marker>
          <marker id="direct-reference-dot" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto">
            <circle cx="3.5" cy="3.5" r="2.8" :fill="relationColor"></circle>
          </marker>
        </defs>

        <g v-for="edge in referenceEdges" :key="edge.key">
          <path
            :d="edge.d"
            fill="none"
            :stroke="edge.stroke || relationColor"
            :stroke-width="edge.width || 2"
            stroke-linecap="round"
            stroke-linejoin="round"
            :marker-start="edge.startMarker ? `url(#direct-reference-${edge.startMarker})` : undefined"
            :marker-end="edge.endMarker ? `url(#direct-reference-${edge.endMarker})` : undefined"
          />
          <text :x="edge.labelX" :y="edge.labelY" text-anchor="middle" class="reference-graph__edge-label">
            <tspan
              v-for="(lineText, index) in edge.labelLines"
              :key="`${edge.key}-${index}`"
              :x="edge.labelX"
              :dy="index === 0 ? 0 : 18"
            >
              {{ lineText }}
            </tspan>
          </text>
        </g>
      </svg>

      <article
        v-for="node in referenceNodes"
        :key="node.id"
        class="reference-graph__node"
        :class="`is-${node.kind}`"
        :style="nodeStyle(node)"
      >
        <strong>{{ node.title }}</strong>
        <span v-if="node.subtitle">{{ node.subtitle }}</span>
      </article>

      <div v-if="loading" class="direct-graph-panel__status">正在刷新结果...</div>
    </div>

    <div v-else-if="loading" class="direct-graph-panel__empty">
      <strong>{{ title }}</strong>
      <span>正在查询真实关系数据</span>
    </div>

    <div v-else class="direct-graph-panel__empty">
      <strong>{{ title }}</strong>
      <span>暂无匹配结果</span>
    </div>
  </div>
</template>

<style scoped>
.direct-graph-panel {
  position: relative;
  display: grid;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 8px 8px, rgba(253, 156, 0, 0.14) 1.2px, transparent 1.3px),
    #fffdf8;
  background-size: 32px 32px;
}

.reference-graph {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.reference-graph__svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.reference-graph__edge-label {
  fill: #5634e8;
  font-size: 9px;
  font-weight: 600;
  paint-order: stroke;
  stroke: rgba(255, 253, 248, 0.96);
  stroke-width: 5px;
}

.reference-graph__node {
  position: absolute;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 3px;
  padding: 14px 16px;
  border-radius: 8px;
  text-align: center;
  box-shadow: 0 10px 22px rgba(72, 132, 214, 0.08);
}

.reference-graph__node strong {
  display: block;
  overflow: hidden;
  width: 100%;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.18;
  text-wrap: balance;
}

.reference-graph__node span {
  display: block;
  overflow: hidden;
  width: 100%;
  color: #171d2d;
  font-size: 10px;
  line-height: 1.22;
  text-wrap: balance;
}

.reference-graph__node.is-institution {
  border: 1.5px solid #ff8a1f;
  background: linear-gradient(180deg, rgba(255, 252, 246, 0.98), rgba(255, 247, 236, 0.98));
}

.reference-graph__node.is-institution strong {
  color: #ef6c00;
  font-size: 12px;
}

.reference-graph__node.is-expert-blue {
  border: 1.5px solid #4f8cff;
  background: linear-gradient(180deg, rgba(250, 252, 255, 0.98), rgba(240, 246, 255, 0.98));
}

.reference-graph__node.is-expert-blue strong {
  color: #2d65f6;
}

.reference-graph__node.is-expert-green {
  border: 1.5px solid #00b333;
  background: linear-gradient(180deg, rgba(247, 255, 247, 0.98), rgba(240, 249, 240, 0.98));
}

.reference-graph__node.is-expert-green strong {
  color: #16871f;
}

.direct-graph-panel__empty {
  display: grid;
  width: 360px;
  min-height: 180px;
  place-items: center;
  align-self: center;
  justify-self: center;
  padding: 24px;
  border: 1px dashed #b5d3fc;
  border-radius: 18px;
  color: var(--text-secondary);
  text-align: center;
}

.direct-graph-panel__empty strong {
  color: var(--text-primary);
  font-size: 18px;
}

.direct-graph-panel__empty p {
  margin: 0;
}

.direct-graph-panel__status {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 3;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-secondary);
  font-size: 12px;
  box-shadow: 0 4px 12px rgba(72, 132, 214, 0.12);
}
</style>
