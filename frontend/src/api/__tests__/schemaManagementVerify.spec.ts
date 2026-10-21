import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 模拟 fetchEventSource 需要的最小 options 面。 */
interface SseOptions {
  onmessage?: (ev: { data?: string }) => void
  onopen?: (response: Response) => Promise<void>
  signal?: AbortSignal
}

const state = vi.hoisted(() => ({
  behavior: null as null | ((options: SseOptions) => Promise<void>),
  lastOptions: undefined as SseOptions | undefined,
}))

vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: vi.fn(async (_url: string, options: SseOptions) => {
    state.lastOptions = options
    await state.behavior?.(options)
  }),
}))

const { verifyAndSaveScript } = await import('../schemaManagement')

function sse(payload: unknown) {
  return { data: JSON.stringify(payload) }
}

function makeHandlers() {
  return {
    onProgress: vi.fn(),
    onSuccess: vi.fn(),
    onError: vi.fn(),
  }
}

function makeFile() {
  return new File(['x = 1\n'], 't.py', { type: 'text/x-python' })
}

beforeEach(() => {
  state.behavior = null
  state.lastOptions = undefined
})

describe('verifyAndSaveScript 终态语义（复核 SEC-SSE）', () => {
  it('只有 progress 的正常 EOF 也必须以错误收尾，不得悬空', async () => {
    state.behavior = async (options) => {
      options.onmessage?.(sse({ type: 'progress', stage: 'llm', message: '校验中' }))
      // 模拟连接被掐：Promise 正常 resolve，没有任何终态事件
    }
    const handlers = makeHandlers()
    await verifyAndSaveScript('schema-1', makeFile(), 'u1', handlers)
    expect(handlers.onProgress).toHaveBeenCalled()
    expect(handlers.onSuccess).not.toHaveBeenCalled()
    expect(handlers.onError).toHaveBeenCalledTimes(1)
    const [message, issues, stage, detail] = handlers.onError.mock.calls[0]
    expect(message).toContain('连接中断')
    expect(issues).toEqual([])
    expect(stage).toBe('stream')
    expect(detail?.code).toBe('stream_eof')
  })

  it('错误事件的 code/category 经第 4 参数透出（兼容既有三元回调）', async () => {
    state.behavior = async (options) => {
      options.onmessage?.(
        sse({
          type: 'error',
          code: 'llm_unavailable',
          category: 'unavailable_auth',
          stage: 'llm',
          message: 'LLM 安全校验暂不可用（模型鉴权失败），请稍后重传',
          issues: ['LLM 安全校验暂不可用（模型鉴权失败），请稍后重传'],
        }),
      )
    }
    const handlers = makeHandlers()
    await verifyAndSaveScript('schema-1', makeFile(), 'u1', handlers)
    expect(handlers.onError).toHaveBeenCalledTimes(1)
    const [message, , stage, detail] = handlers.onError.mock.calls[0]
    expect(message).toContain('暂不可用')
    expect(stage).toBe('llm')
    expect(detail).toEqual({ code: 'llm_unavailable', category: 'unavailable_auth' })
    // 终态只触发一次：EOF 后不再补发 stream_eof
    expect(handlers.onError).toHaveBeenCalledTimes(1)
  })

  it('success 事件收尾后，EOF 不再触发错误', async () => {
    state.behavior = async (options) => {
      options.onmessage?.(sse({ type: 'success', script: null }))
    }
    const handlers = makeHandlers()
    await verifyAndSaveScript('schema-1', makeFile(), 'u1', handlers)
    expect(handlers.onSuccess).toHaveBeenCalledTimes(1)
    expect(handlers.onError).not.toHaveBeenCalled()
  })

  it('总截止超时按错误收尾并中断连接', async () => {
    vi.useFakeTimers()
    try {
      // 流一直挂着：既无终态也不结束，等看门狗出手
      state.behavior = (options) =>
        new Promise<void>((_resolve, reject) => {
          options.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        })
      const handlers = makeHandlers()
      const promise = verifyAndSaveScript('schema-1', makeFile(), 'u1', handlers)
      await vi.advanceTimersByTimeAsync(75_000)
      await promise
      expect(handlers.onError).toHaveBeenCalledTimes(1)
      const [, , stage, detail] = handlers.onError.mock.calls[0]
      expect(stage).toBe('stream')
      expect(detail?.code).toBe('stream_timeout')
      expect(state.lastOptions?.signal?.aborted).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('非 200 打开失败照旧抛给调用方 catch（既有契约不变）', async () => {
    state.behavior = async (options) => {
      await options.onopen?.(new Response('{"detail":"无权限"}', { status: 403 }))
    }
    const handlers = makeHandlers()
    await expect(verifyAndSaveScript('schema-1', makeFile(), 'u1', handlers)).rejects.toThrow(
      '无权限',
    )
    expect(handlers.onError).not.toHaveBeenCalled()
    expect(handlers.onSuccess).not.toHaveBeenCalled()
  })
})
