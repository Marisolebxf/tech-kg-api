import { defineStore } from 'pinia'
import { useAuthStore } from './auth'

import { listGraphSpaces } from '../api/graphSearch'
import { graphSpace as configuredDefault } from '../config'

/** 全局图空间选择的 localStorage key（命名对齐 tech-kg-schema-user-id）。 */
export const GRAPH_SPACE_STORAGE_KEY = 'tech-kg-graph-space'

function readStoredSpace(): string {
  try {
    return localStorage.getItem(GRAPH_SPACE_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

function persistSpace(space: string): void {
  try {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, space)
  } catch {
    // localStorage 不可用（隐私模式等）：仅内存态生效
  }
}

/**
 * 全局图空间上下文：右上角选择器的数据源，业务模块统一从这里取当前空间。
 * 空间列表来自 GET /v1/graph-search/spaces（所有用户=默认业务空间+本人绑定，
 * 绑定对所有用户生效，管理员经配置页修改绑定）；加载失败静默降级，
 * 当前值走 localStorage > 构建默认 > 'dev'。
 */
export const useGraphSpaceStore = defineStore('graphSpace', {
  state: () => ({
    spaces: [] as string[],
    current: readStoredSpace(),
    loading: false,
    loadError: false,
    initialized: false,
  }),
  actions: {
    async ensureLoaded(force = false): Promise<void> {
      if ((this.initialized && !force) || this.loading) return
      this.loading = true
      this.loadError = false
      try {
        // http 拦截器已解包为 ApiResponse（运行时），axios 泛型声明与运行时不同，故做一次窄化断言
        const payload = (await listGraphSpaces()) as unknown as { data?: { spaces?: string[] } }
        this.spaces = payload.data?.spaces ?? []
        this._normalizeCurrent()
        this.initialized = true
      } catch {
        this.loadError = true
        if (useAuthStore().profile?.businessRbacEnabled) {
          this.spaces = []
          this.current = ''
          persistSpace('')
        }
      } finally {
        this.loading = false
      }
    },
    setCurrent(space: string): void {
      if (!space || ((useAuthStore().profile?.businessRbacEnabled || this.spaces.length) && !this.spaces.includes(space))) return
      this.current = space
      persistSpace(space)
    },
    /** 列表到位后归一当前值：localStorage > 构建默认 > 列表第一个 > 'dev'。 */
    _normalizeCurrent(): void {
      const stored = readStoredSpace()
      const pick =
        [stored, configuredDefault].find((v) => v && this.spaces.includes(v)) ??
        this.spaces[0] ??
        (useAuthStore().profile?.businessRbacEnabled ? '' : stored || configuredDefault || 'dev')
      this.current = pick
      persistSpace(pick)
    },
  },
})
