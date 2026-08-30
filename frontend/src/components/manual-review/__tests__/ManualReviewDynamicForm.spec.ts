import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ManualReviewDynamicForm from '../ManualReviewDynamicForm.vue'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

type Section = { type: string; source?: string; target?: string }

const mountForm = (sections: Section[], data: Record<string, unknown> = {}) =>
  mount(ManualReviewDynamicForm, { props: { sections, data } })

describe('七种 displaySchema 渲染', () => {
  it('mapping-table 渲染字段/字典映射 textarea', () => {
    const w = mountForm([{ type: 'mapping-table' }])
    expect(w.text()).toContain('字段/字典映射')
    expect(w.find('textarea').exists()).toBe(true)
  })
  it('field-editor 渲染缺失字段补录', () => {
    const w = mountForm([{ type: 'field-editor', source: 'data.candidate.missingFields' }], {
      candidate: { missingFields: { title: '' } },
    })
    expect(w.text()).toContain('缺失字段补录')
    expect(w.text()).toContain('"title": ""')
  })
  it('record-merge 渲染重复记录定主 + 主记录 input', () => {
    const w = mountForm([{ type: 'record-merge' }], { candidate: { records: [{ id: 'R1' }] } })
    expect(w.text()).toContain('重复记录定主')
    expect(w.find('input').exists()).toBe(true)
  })
  it('entity-comparison 渲染候选与存量实体 + 裁决 select', () => {
    const w = mountForm([{ type: 'entity-comparison' }], {
      candidate: { existingCandidates: [{ id: 'E-1', score: 0.94 }] },
    })
    expect(w.text()).toContain('候选与存量实体')
    expect(w.find('.arco-select').exists()).toBe(true)
  })
  it('evidence-list 渲染关系证据勾选项', () => {
    const w = mountForm([{ type: 'evidence-list' }], { evidence: [{ id: 'ev-1' }, { id: 'ev-2' }] })
    expect(w.text()).toContain('关系证据')
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(2)
  })
  it('attribute-comparison 渲染属性来源对照', () => {
    const w = mountForm([{ type: 'attribute-comparison' }], {
      candidate: { conflicts: [{ attr: 'org', a: 'X', b: 'Y' }] },
    })
    expect(w.text()).toContain('属性来源对照')
    expect(w.text()).toContain('org')
  })
  it('runtime-config 渲染运行配置', () => {
    const w = mountForm([{ type: 'runtime-config' }], { candidate: { runtime: { timeout: 60 } } })
    expect(w.text()).toContain('运行配置')
    expect(w.text()).toContain('"timeout": 60')
  })
  it('raw-json-readonly 渲染只读异常数据（无任何输入控件）', () => {
    const w = mountForm([{ type: 'raw-json-readonly' }], { any: 'data' })
    expect(w.text()).toContain('只读异常数据')
    expect(w.find('textarea').exists()).toBe(false)
    expect(w.find('input').exists()).toBe(false)
    expect(w.find('select').exists()).toBe(false)
  })
})

describe('真实数据字段缺失时安全降级', () => {
  it('field-editor 在 missingFields 缺失时降级为空对象，不崩溃', () => {
    const w = mountForm([{ type: 'field-editor' }], { candidate: {} })
    expect(w.text()).toContain('缺失字段补录')
    // json(undefined ?? {}) => "{}"
    expect(w.text()).toContain('{}')
  })
  it('entity-comparison 在 existingCandidates 缺失时不崩溃', () => {
    const w = mountForm([{ type: 'entity-comparison' }], { candidate: {} })
    expect(w.text()).toContain('候选与存量实体')
    expect(w.find('.arco-select').exists()).toBe(true)
  })
  it('record-merge 在 records 缺失时不崩溃', () => {
    const w = mountForm([{ type: 'record-merge' }], {})
    expect(w.text()).toContain('重复记录定主')
  })
  it('evidence-list 在 evidence 缺失时渲染零勾选项', () => {
    const w = mountForm([{ type: 'evidence-list' }], {})
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(0)
  })
  it('candidate 整体缺失时各组件仍可渲染', () => {
    const w = mountForm(
      [{ type: 'field-editor' }, { type: 'attribute-comparison' }, { type: 'runtime-config' }],
      {},
    )
    expect(w.findAll('textarea').length).toBeGreaterThan(0)
  })
})

describe('未知组件不执行动态代码', () => {
  it('未知 type 走只读降级并给出升级治理员提示', () => {
    const w = mountForm([{ type: 'evil-dynamic-widget' }], { x: 1 })
    expect(w.text()).toContain('未知安全组件 evil-dynamic-widget')
    expect(w.text()).toContain('仅允许查看并升级治理员')
  })
  it('未知 type 不渲染任何交互控件（只读 pre）', () => {
    const w = mountForm([{ type: 'evil-dynamic-widget' }], {})
    expect(w.find('textarea').exists()).toBe(false)
    expect(w.find('input').exists()).toBe(false)
    expect(w.find('select').exists()).toBe(false)
    expect(w.find('pre').exists()).toBe(true)
  })
  it('恶意 type 名以文本插值转义，不产生 HTML 元素/不执行脚本', () => {
    const malicious = '<img src=x onerror=alert(1)>'
    const w = mountForm([{ type: malicious }], {})
    // Vue 文本插值会转义：不会生成 <img> 节点
    expect(w.find('img').exists()).toBe(false)
    // 字面字符串作为文本可见
    expect(w.html()).toContain('&lt;img')
  })
})

describe('生产模式无硬编码演示数据', () => {
  // 场景 7：生产渲染路径（本组件）只消费 props，绝不内置演示候选/证据。
  it('空 data 不产生任何伪造候选或证据文本', () => {
    const w = mountForm(
      [{ type: 'entity-comparison' }, { type: 'evidence-list' }],
      {},
    )
    const html = w.html()
    expect(html).not.toContain('EXPERT_')
    expect(html).not.toContain('candidate')
    expect(html).not.toMatch(/0\.\d{2}/) // 无伪造相似度分数
  })
  it('仅渲染传入的 sections/data，无内置演示记录', () => {
    const w = mountForm([{ type: 'mapping-table' }], { candidate: { real: true } })
    // 只出现我们传入的内容，不出现演示种子
    expect(w.text()).not.toContain('脱敏专家')
    expect(w.text()).not.toContain('华南智能芯片')
  })
})

describe('change 事件', () => {
  it('编辑 mapping textarea 触发 change 并携带值', async () => {
    const w = mountForm([{ type: 'mapping-table' }])
    await w.find('textarea').setValue('[{"source":"a","target":"b"}]')
    const events = w.emitted('change')
    expect(events).toBeTruthy()
    const last = events![events!.length - 1][0] as Record<string, unknown>
    expect(last.mappingsJson).toBe('[{"source":"a","target":"b"}]')
  })
  it('勾选证据把证据项加入 change.evidence', async () => {
    const w = mountForm([{ type: 'evidence-list' }], { evidence: [{ id: 'ev-1' }] })
    await w.find('input[type="checkbox"]').setValue(true)
    const last = w.emitted('change')!.at(-1)![0] as { evidence: unknown[] }
    expect(last.evidence).toHaveLength(1)
  })
})
