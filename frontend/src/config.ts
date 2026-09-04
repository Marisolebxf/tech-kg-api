/**
 * 前端运行时配置（方案 B：构建一次、部署期注入）。
 *
 * 读取链：window.__RUNTIME_CONFIG__（容器启动脚本 docker/40-app-runtime-config.sh
 * 从环境变量生成）→ import.meta.env.VITE_*（构建期 bake，本地 dev / 显式传参构建）
 * → 内置默认值。注入值为空串一律视为未设置，因此无 runtime-config.js 时行为与
 * 旧版构建期注入逐字一致。
 */

interface RuntimeConfig {
  base?: string
  apiBase?: string
  graphSpace?: string
  authEnabled?: string
  portalEmbeddedDefault?: string
  portalAllowedOrigins?: string
  portalTargetOrigin?: string
  portalSource?: string
  adminExampleFallback?: string
}

declare global {
  interface Window {
    __RUNTIME_CONFIG__?: RuntimeConfig
  }
}

const runtimeConfig: RuntimeConfig =
  (typeof window !== 'undefined' ? window.__RUNTIME_CONFIG__ : undefined) ?? {}

/** 运行时注入优先；两边都为空返回 undefined（由调用方决定默认值）。 */
function pick(runtimeKey: keyof RuntimeConfig, envKey: string): string | undefined {
  const injected = String(runtimeConfig[runtimeKey] ?? '').trim()
  if (injected) return injected
  const baked = (import.meta.env as Record<string, unknown>)[envKey]
  const bakedValue = typeof baked === 'string' ? baked.trim() : ''
  return bakedValue || undefined
}

/** base 归一化为绝对路径 + 尾斜杠：'' | './' → '/'；'/bkg_zpt' → '/bkg_zpt/'。 */
function normalizeBase(value: string | undefined): string {
  let base = (value ?? '').trim()
  if (!base || base === './' || base === '.') base = '/'
  if (!base.startsWith('/')) base = `/${base}`
  if (!base.endsWith('/')) base = `${base}/`
  // 哨兵泄漏兜底：镜像产物未经过启动脚本替换时（理论不发生），回落根路径。
  // 哨兵字面量拆分拼写——启动脚本的 sed 会把产物里的哨兵 token 全量替换，
  // 此处若写成完整字面量会被误改写，守卫随之失效（曾引发 base 被误判回 /）
  const sentinel = '__BASE' + '__'
  return base.includes(sentinel) ? '/' : base
}

/** 应用部署前缀（绝对、带尾斜杠），如 /bkg_zpt/ */
export const appBase = normalizeBase(pick('base', 'BASE_URL'))

/** API 前缀（不带尾斜杠）：缺省 {appBase}api，如 /bkg_zpt/api、根路径 /api */
export const apiBase = (() => {
  const explicit = pick('apiBase', 'VITE_API_BASE')
  if (explicit) return explicit.replace(/\/+$/, '')
  return `${appBase.slice(0, -1)}/api`
})()

/** 图空间缺省（TRS_GRAPH_SPACE，与后端同名同源） */
export const graphSpace = pick('graphSpace', 'VITE_GRAPH_SPACE')

/** 仅显式 'false' 关闭认证；未设置 = 开启（与后端 AUTH_ENABLED 语义对齐） */
export const authDisabled = pick('authEnabled', 'VITE_AUTH_ENABLED') === 'false'

export const portalEmbeddedDefault = pick('portalEmbeddedDefault', 'VITE_PORTAL_EMBEDDED_DEFAULT')
export const portalAllowedOrigins = pick('portalAllowedOrigins', 'VITE_PORTAL_ALLOWED_ORIGINS')
export const portalTargetOrigin = pick('portalTargetOrigin', 'VITE_PORTAL_TARGET_ORIGIN')
export const portalSource = pick('portalSource', 'VITE_PORTAL_SOURCE') || 'tech-kg-api'

/** 管理页示例数据兜底：默认开，仅显式 'false' 关闭 */
export const adminExampleFallback = pick('adminExampleFallback', 'VITE_ADMIN_EXAMPLE_FALLBACK') !== 'false'
