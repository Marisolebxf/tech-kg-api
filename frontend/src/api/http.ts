import axios from 'axios'

import { apiBase } from '../config'
import { currentSessionVersion } from '../auth/sessionVersion'
import { PortalAction, portalBridge } from '../portal/iframeBridge'

type SessionExpiredHandler = (message: string) => void | Promise<unknown>
let sessionExpiredHandler: SessionExpiredHandler | undefined
const requestVersions = new WeakMap<object, number>()
const AUTH_CONTROL_REQUEST = /\/v1\/auth\/(?:me|login-url|callback|logout)(?:[/?#]|$)/

export function setSessionExpiredHandler(handler: SessionExpiredHandler): void {
  sessionExpiredHandler = handler
}

const RAW_REQUEST_ERROR = /request failed|network error|status code 5\d\d|failed to fetch|load failed/i

function responseDetail(data: unknown): string {
  if (!data || typeof data !== 'object') return ''
  const payload = data as { detail?: unknown; msg?: unknown }
  if (typeof payload.detail === 'string') return payload.detail
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : ''))
      .filter(Boolean)
      .join('；')
  }
  return typeof payload.msg === 'string' ? payload.msg : ''
}

export function getErrorMessage(error: unknown, fallback = '操作失败'): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { status?: number; data?: unknown } }).response
    const detail = responseDetail(response?.data)
    if (detail && !RAW_REQUEST_ERROR.test(detail)) return detail
    if (response?.status && response.status >= 500) {
      return `${fallback}，服务暂时不可用，请稍后重试`
    }
  }
  const message = error instanceof Error ? error.message : ''
  if (message && !RAW_REQUEST_ERROR.test(message)) return message
  if (message) return `${fallback}，无法连接服务，请确认网络和后端状态后重试`
  return fallback
}

export const http = axios.create({
  // 运行时注入的 apiBase（config.ts）已按 appBase 解析网关子路径，等价于相对 './api' 方案。
  baseURL: apiBase,
  timeout: 20_000,
  withCredentials: true,
})

http.interceptors.request.use((config) => {
  requestVersions.set(config, currentSessionVersion())
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error: unknown) => {
    if (typeof error === 'object' && error !== null && 'response' in error) {
      const { response, config } = error as {
        response?: { status?: number; data?: unknown }
        config?: { url?: string }
      }
      const detail = responseDetail(response?.data)
      if (
        response?.status === 401
        && !AUTH_CONTROL_REQUEST.test(config?.url || '')
        && (!config || requestVersions.get(config) === currentSessionVersion())
      ) {
        void Promise.resolve(sessionExpiredHandler?.(detail || '登录状态已失效')).catch(() => {
          // 导航取消或失败时仍向调用方保留原始请求错误。
        })
      } else if (response?.status === 403 && portalBridge.isInIframe) {
        portalBridge.send(PortalAction.NO_PERMISSION, {
          message: detail || '当前用户无权限访问该页面或接口',
        })
      }
    }

    if (error instanceof Error) error.message = getErrorMessage(error, '请求失败')
    return Promise.reject(error)
  },
)
