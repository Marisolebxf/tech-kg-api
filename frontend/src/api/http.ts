import axios from 'axios'

import { apiBase } from '../config'
import { PortalAction, portalBridge } from '../portal/iframeBridge'

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
  baseURL: apiBase,
  timeout: 20_000,
  withCredentials: true,
})

http.interceptors.response.use(
  (response) => response.data,
  (error: unknown) => {
    if (portalBridge.isInIframe && typeof error === 'object' && error !== null && 'response' in error) {
      const response = (error as { response?: { status?: number; data?: unknown } }).response
      const detail = responseDetail(response?.data)
      if (response?.status === 401) {
        portalBridge.send(PortalAction.SESSION_EXPIRED, {
          message: detail || '登录状态已失效',
        })
      } else if (response?.status === 403) {
        portalBridge.send(PortalAction.NO_PERMISSION, {
          message: detail || '当前用户无权限访问该页面或接口',
        })
      }
    }

    if (error instanceof Error) error.message = getErrorMessage(error, '请求失败')
    return Promise.reject(error)
  },
)
