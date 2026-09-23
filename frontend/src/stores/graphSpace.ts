import { defineStore } from 'pinia'
import { useAuthStore } from './auth'

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

/**
 * 全局图空间上下文：图空间选择器（位于配置管理 · 图数据空间页）的数据源，
 * 业务模块统一从这里取当前空间。
 * 空间列表来自 GET /v1/graph-search/spaces（所有用户=默认业务空间+本人绑定，
 * 绑定对所有用户生效，管理员经配置页修改绑定）；加载失败静默降级，
 * 当前值走 本人持久化 > 构建默认 > 'dev'。路由守卫在页面挂载前 bindUser +
 * ensureLoaded，保证页面拿到的 current 一定是本人列表内的取值。
 */
export const useGraphSpaceStore = defineStore('graphSpace', {
  state: () => ({
    spaces: [] as string[],
    current: '',
    userId: '',
    loading: false,
    loadError: false,
    initialized: false,
  }),
  actions: {
    /** 路由守卫在身份就绪后调用：切换用户时丢弃上一账号的选中空间。 */
    bindUser(userId: string): void {
      if (!userId || userId === this.userId) return
      this.userId = userId
      this.current = readStoredSpace(userId)
      if (!this.current) {
        this.current = configuredDefault || 'dev'
        persistSpace(userId, this.current)
      }
    },
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
          persistSpace(this.userId, '')
        }
      } finally {
        this.loading = false
      }
    },
    setCurrent(space: string): void {
      if (!space || ((useAuthStore().profile?.businessRbacEnabled || this.spaces.length) && !this.spaces.includes(space))) return
      this.current = space
      persistSpace(this.userId, space)
    },
    /** 列表到位后归一当前值：本人持久化 > 构建默认 > 列表第一个 > 'dev'。 */
    _normalizeCurrent(): void {
      const stored = readStoredSpace(this.userId)
      const pick =
        [stored, configuredDefault].find((v) => v && this.spaces.includes(v)) ??
        this.spaces[0] ??
        (useAuthStore().profile?.businessRbacEnabled ? '' : stored || configuredDefault || 'dev')
      this.current = pick
      persistSpace(this.userId, pick)
    },
  },
})
