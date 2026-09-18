import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { subscribeJobEvents } from './jobEvents'

type Listener = (event: { type: string; data?: string }) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  private listeners = new Map<string, Set<Listener>>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(listener)
  }

  emit(type: string, data?: string) {
    for (const listener of this.listeners.get(type) ?? []) listener({ type, data })
  }

  close() {
    this.closed = true
  }
}

describe('subscribeJobEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('订阅后端任务变更 SSE 并透传 jobs-changed 事件', () => {
    const changes: unknown[] = []
    const close = subscribeJobEvents((event) => changes.push(event))

    const source = FakeEventSource.instances.at(-1)!
    expect(source.url).toContain('/v1/workflow-system/jobs/events')

    source.emit('jobs-changed', JSON.stringify({ changed: ['job:a'], removed: [] }))
    expect(changes).toEqual([{ changed: ['job:a'], removed: [] }])

    close()
    expect(source.closed).toBe(true)
  })

  it('open 事件触发 onOpen（重连补拉钩子）', () => {
    const onOpen = vi.fn()
    subscribeJobEvents(() => {}, onOpen)

    FakeEventSource.instances.at(-1)!.emit('open')
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('事件数据解析失败也触发一次重拉（兜底为空变更）', () => {
    const changes: unknown[] = []
    subscribeJobEvents((event) => changes.push(event))

    FakeEventSource.instances.at(-1)!.emit('jobs-changed', 'not-json')
    expect(changes).toEqual([{ changed: [], removed: [] }])
  })
})
