import { computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import {
  PortalAction,
  isPortalEmbeddedMode,
  portalBridge,
} from './iframeBridge'

const PORTAL_SOURCE = import.meta.env.VITE_PORTAL_SOURCE || 'tech-kg-api'

function routeTitle(title: unknown): string {
  return typeof title === 'string' && title.trim()
    ? title.trim()
    : '亿级知识图谱平台'
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
      if (!isEmbedded.value || !portalBridge.isInIframe) return
      portalBridge.send(PortalAction.ROUTE_CHANGE, { path })
      await nextTick()
      portalBridge.ready(PORTAL_SOURCE, routeTitle(title))
      portalBridge.send(PortalAction.LOADING_HIDE)
    },
    { immediate: true, flush: 'post' },
  )

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

  onMounted(() => {
    if (!portalBridge.isInIframe) return
    portalBridge.start()
    removeLogoutHandler = portalBridge.on(PortalAction.LOGOUT, () => {
      void handlePortalLogout()
    })
    // 兼容门户早期实现中的点分命名。
    removeLegacyLogoutHandler = portalBridge.on('user.logout', () => {
      void handlePortalLogout()
    })
  })

  onBeforeUnmount(() => {
    stopEmbeddedWatch()
    stopRouteWatch()
    removeLogoutHandler?.()
    removeLegacyLogoutHandler?.()
    portalBridge.stop()
    document.documentElement.classList.remove('portal-embedded')
  })

  return {
    isEmbedded,
    portalStatusText,
  }
}
