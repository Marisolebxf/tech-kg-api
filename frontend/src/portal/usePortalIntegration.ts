import { computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { portalSource } from '../config'
import { useAuthStore } from '../stores/auth'
import {
  PortalAction,
  isPortalEmbeddedMode,
  portalBridge,
  type PortalMessageData,
} from './iframeBridge'
import { portalMenuCode, portalMenuPath } from './portalRoutes'

const PORTAL_SOURCE = portalSource

function routeTitle(title: unknown): string {
  return typeof title === 'string' && title.trim()
    ? title.trim()
    : '亿级科技知识图谱引擎'
}

export function usePortalIntegration() {
  const route = useRoute()
  const router = useRouter()
  const authStore = useAuthStore()

  const isEmbedded = computed(() => isPortalEmbeddedMode(route.query.embedded))
  const portalStatusText = computed(() => {
    if (route.query.portalState === 'logout') {
      return '已退出登录，请从统一门户重新进入。'
    }
    return '登录状态已失效，已通知统一门户处理。'
  })

  let removeLogoutHandler: (() => void) | undefined
  let removeLegacyLogoutHandler: (() => void) | undefined
  let removeRouteHandler: (() => void) | undefined
  let restoringPortalRoute = 0
  let ready = false
  let disposed = false

  const stopEmbeddedWatch = watch(
    isEmbedded,
    (embedded) => {
      document.documentElement.classList.toggle('portal-embedded', embedded)
    },
    { immediate: true },
  )

  const stopRouteWatch = watch(
    () => [route.fullPath, route.meta.title] as const,
    async ([path, title]) => {
      if (!ready || !isEmbedded.value || !portalBridge.isInIframe) return
      const code = portalMenuCode(route.path)
      if (!restoringPortalRoute && code) {
        // 门户用 code 选择菜单、subPath 保存子应用深链；path 不是该协议的导航字段。
        portalBridge.send(PortalAction.ROUTE_CHANGE, { code, subPath: path })
      }
      await nextTick()
      portalBridge.send(PortalAction.PAGE_SET_TITLE, { title: routeTitle(title) })
      portalBridge.send(PortalAction.LOADING_HIDE)
    },
    { flush: 'post' },
  )

  async function handlePortalRoute(data: PortalMessageData): Promise<void> {
    const code = typeof data.code === 'string' ? data.code.trim() : ''
    const target = typeof data.subPath === 'string' && data.subPath.trim()
      ? data.subPath.trim()
      : portalMenuPath(code)
    if (!target || !target.startsWith('/') || target.startsWith('//') || target.includes('\\')) return
    const resolved = router.resolve(target)
    // 仅接受本应用已注册且属于指定菜单的路由，身份限制仍由 router guard 执行。
    const targetCode = portalMenuCode(resolved.path)
    if (!resolved.matched.length || !targetCode || (code && targetCode !== code)) return
    if (resolved.fullPath === route.fullPath) return
    restoringPortalRoute += 1
    try {
      await router.replace(resolved.fullPath)
      await nextTick()
    } finally {
      restoringPortalRoute -= 1
    }
  }

  async function handlePortalLogout(): Promise<void> {
    try {
      await authStore.logout()
    } catch {
      // 门户已发出退出命令，本地接口失败时仍清除前端身份并进入退出状态页。
    }
    await router.replace({
      path: '/login',
      query: { embedded: '1', portalState: 'logout' },
    })
  }

  onMounted(async () => {
    if (!portalBridge.isInIframe) return
    portalBridge.start()
    removeLogoutHandler = portalBridge.on(PortalAction.LOGOUT, () => {
      void handlePortalLogout()
    })
    // 兼容门户早期实现中的点分命名。
    removeLegacyLogoutHandler = portalBridge.on('user.logout', () => {
      void handlePortalLogout()
    })
    removeRouteHandler = portalBridge.on(PortalAction.ROUTE_CHANGE, (data) => {
      void handlePortalRoute(data)
    })
    // main.ts 在初始路由完成前挂载应用；不能把首次路由解析当成本地导航覆盖门户深链。
    await router.isReady()
    await nextTick()
    if (disposed) return
    ready = true
    // ready 会触发门户下发深链，只在监听器就绪后发送一次，避免每次跳转都被旧深链拉回。
    portalBridge.ready(PORTAL_SOURCE, routeTitle(route.meta.title))
    portalBridge.send(PortalAction.PAGE_SET_TITLE, { title: routeTitle(route.meta.title) })
    portalBridge.send(PortalAction.LOADING_HIDE)
  })

  onBeforeUnmount(() => {
    disposed = true
    stopEmbeddedWatch()
    stopRouteWatch()
    removeLogoutHandler?.()
    removeLegacyLogoutHandler?.()
    removeRouteHandler?.()
    portalBridge.stop()
    document.documentElement.classList.remove('portal-embedded')
  })

  return {
    isEmbedded,
    portalStatusText,
  }
}
