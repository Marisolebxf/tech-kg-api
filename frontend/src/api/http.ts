import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useToast } from '../composables/use-toast'

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    skipErrorToast?: boolean
  }
  interface AxiosRequestConfig {
    skipErrorToast?: boolean
  }
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 20_000,
})

function errorMessage(error: AxiosError): string {
  const status = error.response?.status
  const data = error.response?.data as { msg?: string; message?: string } | undefined
  if (data?.msg) return data.msg
  if (data?.message) return data.message
  if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (!error.response) return '网络异常，请检查网络后重试'
  if (status && status >= 500) return '服务异常，请稍后重试'
  if (status === 401) return '请先登录'
  if (status === 403) return '没有操作权限'
  if (status === 404) return '请求的资源不存在'
  return '请求失败'
}

http.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError) => {
    const config = error.config as InternalAxiosRequestConfig | undefined
    const shouldToast = !config?.skipErrorToast && error.response?.status !== 401
    if (shouldToast) {
      const { showToast } = useToast()
      showToast(errorMessage(error), 'error', 5000)
    }
    return Promise.reject(error)
  },
)
