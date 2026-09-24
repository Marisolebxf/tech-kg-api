import { defineStore } from 'pinia'

import { listGraphSpaces } from '../api/graphSearch'
import { graphSpace as configuredDefault } from '../config'

/** 全局图空间选择的 localStorage key（命名对齐 tech-kg-schema-user-id）。 */
export const GRAPH_SPACE_STORAGE_KEY = 'tech-kg-graph-space'

/**
 * 持久化格式：{"u":<userId>,"s":<space>}。
 * 旧版是裸字符串（跨账号共享），换账号登录会把上一个用户选的空间带进新会话——
 * 普通用户会拿着无权空间发请求（总览串数据/实体列表 403，2026-09-24 修复）。
 * 裸字符串与别人的记录一律视为过期，不采纳。
 */
function readStoredSpace(userId: string): string {
  if (!userId) return ''
  try {
    const raw = localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)
    if (!raw) return ''
    const parsed = JSON.parse(raw) as { u?: unknown; s?: unknown }
    if (parsed && parsed.u === userId && typeof parsed.s === 'string') return parsed.s
    return ''
  } catch {
    return ''
  }
}

function persistSpace(userId: string, space: string): void {
  if (!userId) return
  try {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, JSON.stringify({ u: userId, s: space }))
  } catch {
    // localStorage 不可用（隐私模式等）：仅内存态生效
  }
}

const pendingLoads = new WeakMap<object, { generation: number; promise: Promise<void> }>()

/** 当前空间只能从服务端授权列表选择，持久化记录仅作为列表加载后的候选。 */
export const useGraphSpaceStore = defineStore('graphSpace', {
  state: () => ({
    spaces: [] as string[],
    current: '',
    userId: '',
    loading: false,
    loadError: false,
    initialized: false,
    generation: 0,
  }),
  actions: {
    /** 路由守卫在身份就绪后调用：切换用户时丢弃上一账号的选中空间。 */
    bindUser(userId: string): void {
      if (userId === this.userId) return
      this.reset()
      this.userId = userId
    },
    reset(): void {
      this.generation += 1
      pendingLoads.delete(this)
      this.userId = ''
      this.spaces = []
      this.current = ''
      this.initialized = false
      this.loading = false
      this.loadError = false
    },
    async ensureLoaded(force = false): Promise<void> {
      const pending = pendingLoads.get(this)
      if (pending && !force) return pending.promise
      if (this.initialized && !force) return
      const generation = ++this.generation
      const userId = this.userId
      this.loading = true
      this.loadError = false
      const promise = (async () => {
        try {
          // http 拦截器已解包为 ApiResponse（运行时），axios 泛型声明与运行时不同，故做一次窄化断言
          const payload = (await listGraphSpaces()) as unknown as { data?: { spaces?: string[] } }
          if (this.generation !== generation || this.userId !== userId) return
          this.spaces = payload.data?.spaces ?? []
          this._normalizeCurrent()
          this.initialized = true
        } catch {
          if (this.generation !== generation || this.userId !== userId) return
          this.loadError = true
          this.initialized = false
          this.spaces = []
          this.current = ''
        } finally {
          if (this.generation === generation) this.loading = false
          if (pendingLoads.get(this)?.generation === generation) pendingLoads.delete(this)
        }
      })()
      pendingLoads.set(this, { generation, promise })
      return promise
    },
    setCurrent(space: string): void {
      if (!space || !this.spaces.includes(space)) return
      this.current = space
      persistSpace(this.userId, space)
    },
    /** 列表到位后归一当前值：本人持久化 > 构建默认 > 列表第一个；空集保持空值。 */
    _normalizeCurrent(): void {
      const stored = readStoredSpace(this.userId)
      const pick =
        [stored, configuredDefault].find((v) => v && this.spaces.includes(v)) ??
        this.spaces[0] ??
        ''
      this.current = pick
      persistSpace(this.userId, pick)
    },
  },
})
