<script setup lang="ts">
import type { ColleagueInferenceResult, RelationLink, RelationNode } from '../types'

defineProps<{
  result: ColleagueInferenceResult
  nodes: RelationNode[]
  links: RelationLink[]
}>()
</script>

<template>
  <section class="kg-panel relation-graph">
    <div class="kg-panel__header">
      <h2 class="kg-panel__title">测试结果预览</h2>
      <div class="relation-graph__legend">
        <span>最近测试时间：</span>
        <strong>{{ result.lastTestTime }}</strong>
      </div>
    </div>

    <div class="relation-graph__canvas">
      <svg viewBox="0 0 660 520" role="img" aria-label="科技专家同事关系推理结果">
        <defs>
          <marker id="arrow-blue" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
            <path d="M0,0 L8,4 L0,8 Z" fill="#4080ff" />
          </marker>
          <marker id="arrow-purple" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
            <path d="M0,0 L8,4 L0,8 Z" fill="#722ed1" />
          </marker>
          <marker id="arrow-green" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
            <path d="M0,0 L8,4 L0,8 Z" fill="#00b42a" />
          </marker>
          <marker id="arrow-orange" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
            <path d="M0,0 L8,4 L0,8 Z" fill="#ff7d00" />
          </marker>
        </defs>

        <path class="edge edge--purple" d="M185 76 H468" marker-end="url(#arrow-purple)" />
        <text class="edge-label edge-label--purple" x="326" y="58">同事关系</text>
        <path class="edge edge--blue" d="M155 104 C170 176, 238 201, 294 230" marker-end="url(#arrow-blue)" />
        <path class="edge edge--blue" d="M514 104 C500 176, 424 201, 366 230" marker-end="url(#arrow-blue)" />
        <text class="edge-label edge-label--blue" x="210" y="184">任职</text>
        <text class="edge-label edge-label--blue" x="430" y="184">任职</text>
        <path class="edge edge--green" d="M282 282 C192 284, 132 314, 106 365" marker-end="url(#arrow-green)" />
        <text class="edge-label edge-label--green" x="120" y="305">研究方向</text>
        <path class="edge edge--dash" d="M330 292 V362" marker-end="url(#arrow-blue)" />
        <text class="edge-label" x="340" y="338">共事时段</text>
        <path class="edge edge--orange" d="M383 282 C464 288, 516 319, 548 365" marker-end="url(#arrow-orange)" />
        <text class="edge-label edge-label--orange" x="502" y="306">协作成果</text>
        <path class="edge edge--dash edge--orange" d="M530 445 C520 460, 516 470, 508 486" marker-end="url(#arrow-orange)" />
        <path class="edge edge--dash edge--orange" d="M576 445 V486" marker-end="url(#arrow-orange)" />
        <path class="edge edge--dash edge--orange" d="M620 445 C630 460, 634 470, 642 486" marker-end="url(#arrow-orange)" />
        <text class="edge-label" x="500" y="474">参与</text>
        <text class="edge-label" x="588" y="474">参与</text>
        <text class="edge-label" x="646" y="474">参与</text>

        <g class="box box--expert" transform="translate(40 44)">
          <rect width="160" height="62" rx="6" />
          <text x="80" y="27">专家A：{{ result.expertA.name }}</text>
          <text x="80" y="50">{{ result.expertA.title }}</text>
        </g>
        <g class="box box--expert-b" transform="translate(468 44)">
          <rect width="160" height="62" rx="6" />
          <text x="80" y="27">专家B：{{ result.expertB.name }}</text>
          <text x="80" y="50">{{ result.expertB.title }}</text>
        </g>
        <g class="box box--org" transform="translate(262 230)">
          <rect width="140" height="62" rx="6" />
          <text x="70" y="27">共同机构：</text>
          <text x="70" y="50">{{ result.organization }}</text>
        </g>
        <g class="box box--field" transform="translate(16 365)">
          <rect width="122" height="88" rx="6" />
          <text x="61" y="26">研究方向</text>
          <rect class="chip" x="30" y="40" width="62" height="26" rx="6" />
          <text x="61" y="58">{{ result.researchDirections[0] }}</text>
          <rect class="chip" x="30" y="68" width="62" height="26" rx="6" />
          <text x="61" y="86">{{ result.researchDirections[1] }}</text>
        </g>
        <g class="box box--time" transform="translate(255 382)">
          <rect width="150" height="58" rx="6" />
          <text x="75" y="24">共事时段：</text>
          <text x="75" y="44">{{ result.overlapPeriod }}</text>
        </g>
        <g class="box box--result" transform="translate(510 365)">
          <rect width="132" height="88" rx="6" />
          <text x="66" y="28">协作成果</text>
          <rect class="result-chip" x="20" y="46" width="34" height="34" rx="6" />
          <rect class="result-chip" x="58" y="46" width="34" height="34" rx="6" />
          <rect class="result-chip" x="96" y="46" width="34" height="34" rx="6" />
          <text class="result-text" x="37" y="68">论文</text>
          <text class="result-text" x="75" y="68">专利</text>
          <text class="result-text" x="113" y="68">项目</text>
        </g>
        <g class="count-badge count-badge--paper" transform="translate(492 486)">
          <rect width="34" height="34" rx="8" />
          <text x="17" y="18">{{ result.collaborations.paper }}</text>
        </g>
        <g class="count-badge count-badge--patent" transform="translate(558 486)">
          <rect width="34" height="34" rx="8" />
          <text x="17" y="18">{{ result.collaborations.patent }}</text>
        </g>
        <g class="count-badge count-badge--project" transform="translate(624 486)">
          <rect width="34" height="34" rx="8" />
          <text x="17" y="18">{{ result.collaborations.project }}</text>
        </g>
      </svg>
    </div>
  </section>
</template>

<style scoped>
.relation-graph {
  height: 100%;
  min-height: 540px;
}

.relation-graph__legend {
  display: flex;
  align-items: center;
  gap: var(--space-12);
  color: var(--text-tertiary);
  font-size: 14px;
}

.relation-graph__legend strong {
  color: var(--text-tertiary);
  font-weight: 400;
}

.relation-graph__canvas {
  height: calc(100% - 68px);
  min-height: 488px;
  margin: 0 var(--space-16) var(--space-16);
  padding: var(--space-16);
  background: var(--surface);
}

.relation-graph__canvas svg {
  width: 100%;
  height: 100%;
}

.edge {
  fill: none;
  stroke-width: 2;
}

.edge--blue {
  stroke: var(--graph-blue);
}

.edge--purple {
  stroke: var(--graph-purple);
}

.edge--green {
  stroke: var(--graph-green);
}

.edge--orange {
  stroke: var(--graph-orange);
}

.edge--dash {
  stroke: var(--text-tertiary);
  stroke-dasharray: 5 5;
}

.edge--dash.edge--orange {
  stroke: var(--graph-orange);
}

.edge-label {
  fill: var(--text-secondary);
  font-size: 13px;
  text-anchor: middle;
}

.edge-label--blue {
  fill: #1d4ed8;
}

.edge-label--purple {
  fill: #722ed1;
}

.edge-label--green {
  fill: #237804;
}

.edge-label--orange {
  fill: #d46b08;
}

.box rect {
  fill: #f8fbff;
  stroke: var(--graph-blue);
  stroke-width: 1.4;
}

.box text {
  fill: #174ea6;
  font-size: 13px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
}

.box--expert-b rect,
.box--field rect {
  fill: #f5fff7;
  stroke: var(--graph-green);
}

.box--expert-b text,
.box--field text {
  fill: #237804;
}

.box--org rect {
  fill: #fbf7ff;
  stroke: #b37feb;
}

.box--org text {
  fill: #722ed1;
}

.box--time rect {
  fill: #fffbe6;
  stroke: var(--graph-gold);
}

.box--time text {
  fill: #ad6800;
}

.box--result rect {
  fill: #fff7ed;
  stroke: var(--graph-orange);
}

.box--result text {
  fill: #d46b08;
}

.box .chip {
  fill: var(--surface);
  stroke: #95de64;
}

.box .result-chip {
  fill: var(--surface);
  stroke: var(--graph-orange);
}

.box .result-text {
  fill: var(--primary);
  font-size: 12px;
}

.box--result .result-text {
  fill: #ff4d00;
}

.count-badge rect {
  fill: #f8fbff;
  stroke: var(--graph-blue);
}

.count-badge text {
  fill: var(--primary);
  font-size: 15px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: middle;
}

.count-badge--patent rect {
  fill: var(--success-subtle);
  stroke: var(--graph-green);
}

.count-badge--patent text {
  fill: #237804;
}

.count-badge--project rect {
  fill: var(--warning-subtle);
  stroke: var(--graph-orange);
}

.count-badge--project text {
  fill: #d46b08;
}

.relation-graph__meta {
  display: flex;
  gap: var(--space-12);
  padding: 0 var(--space-16) var(--space-16);
  color: var(--text-tertiary);
  font-size: 12px;
}
</style>
