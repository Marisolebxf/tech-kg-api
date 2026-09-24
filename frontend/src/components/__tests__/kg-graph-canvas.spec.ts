import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import KgGraphCanvas from '../kg-graph-canvas.vue'
import type { GraphEdgeData, GraphNodeData } from '../../data/graph-presets'

vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconFullscreen: { template: '<i />' },
  IconMinus: { template: '<i />' },
  IconPlus: { template: '<i />' },
}))

const SlotStub = { template: '<div><slot /></div>' }

function nodeFixture(id: string, label: string): GraphNodeData {
  return {
    id,
    label,
    nodeType: 'topic',
    x: 0,
    y: 0,
    entityType: id.toUpperCase(),
    relations: '',
    evidence: [],
  }
}

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(KgGraphCanvas, {
    props: {
      nodes: [nodeFixture('a', '实体A'), nodeFixture('b', '实体B')],
      edges: [{ id: 'e1', from: 'a', to: 'b', label: 'USES', category: '直接关系' } as GraphEdgeData],
      showEdgeLabels: true,
      ...props,
    },
    global: {
      components: { ATooltip: SlotStub, ASlider: { template: '<div />' } },
    },
  })
}

/** 拖动平移经 requestAnimationFrame 合帧应用：等一帧 + 一个宏任务让状态写入与重渲染完成。 */
async function flushRaf() {
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

function currentTransform(view: ReturnType<typeof mountCanvas>) {
  return view.get('svg > g').attributes('transform') ?? ''
}

describe('KgGraphCanvas 拖动平移', () => {
  it('空白处按下拖动：平移画布（原有行为不回归）', async () => {
    const view = mountCanvas()
    expect(currentTransform(view)).toContain('translate(0 0)')

    const viewport = view.get('.kg-graph-viewport')
    await viewport.trigger('pointerdown', { pointerId: 1, clientX: 300, clientY: 200 })
    await viewport.trigger('pointermove', { pointerId: 1, clientX: 340, clientY: 220 })
    await flushRaf()

    expect(currentTransform(view)).toContain('translate(40 20)')
    await viewport.trigger('pointerup', { pointerId: 1 })
  })

  it('实体节点上按下拖动：也能平移画布，松手后的 click 不触发选中', async () => {
    const view = mountCanvas()
    const node = view.findAll('.platform-node')[0]

    await node.trigger('pointerdown', { pointerId: 1, clientX: 100, clientY: 100 })
    await view.get('.kg-graph-viewport').trigger('pointermove', { pointerId: 1, clientX: 150, clientY: 130 })
    await flushRaf()

    expect(currentTransform(view)).toContain('translate(50 30)')

    await node.trigger('pointerup', { pointerId: 1 })
    await node.trigger('click')
    expect(view.emitted('selectNode')).toBeUndefined()
  })

  it('实体节点上按下不动松开：单击选择不受影响', async () => {
    const view = mountCanvas()
    const node = view.findAll('.platform-node')[0]

    await node.trigger('pointerdown', { pointerId: 1, clientX: 100, clientY: 100 })
    // 阈值内的轻微抖动不算拖动
    await view.get('.kg-graph-viewport').trigger('pointermove', { pointerId: 1, clientX: 101, clientY: 102 })
    await flushRaf()
    expect(currentTransform(view)).toContain('translate(0 0)')

    await node.trigger('pointerup', { pointerId: 1 })
    await node.trigger('click')
    expect(view.emitted('selectNode')).toHaveLength(1)
  })

  it('关系线（含加粗命中区）上按下拖动：也能平移，click 不触发选中', async () => {
    const view = mountCanvas()
    const hitArea = view.get('.platform-network-hit-area')

    await hitArea.trigger('pointerdown', { pointerId: 1, clientX: 200, clientY: 200 })
    await view.get('.kg-graph-viewport').trigger('pointermove', { pointerId: 1, clientX: 230, clientY: 210 })
    await flushRaf()

    expect(currentTransform(view)).toContain('translate(30 10)')

    await hitArea.trigger('pointerup', { pointerId: 1 })
    await hitArea.trigger('click')
    expect(view.emitted('selectEdge')).toBeUndefined()
  })

  it('连线端点落在两端节点边界上（端点查表渲染）', async () => {
    const view = mountCanvas()
    const line = view.get('.platform-network-line')
    const x1 = Number(line.attributes('x1'))
    const y1 = Number(line.attributes('y1'))
    const x2 = Number(line.attributes('x2'))
    const y2 = Number(line.attributes('y2'))
    for (const value of [x1, y1, x2, y2]) {
      expect(Number.isFinite(value)).toBe(true)
    }
    // 两端不重叠且方向合理：x2 > x1 或 y2 > y1（力导向把两节点推开）
    expect(x2 - x1).not.toBe(0)
    expect(y2 - y1).not.toBe(0)
  })
})
