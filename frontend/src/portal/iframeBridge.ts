export const IFRAME_BRIDGE_PROTOCOL = 'iframe-bridge'
export const IFRAME_BRIDGE_VERSION = '1.0'

export const PortalAction = {
  PAGE_READY: 'page.ready',
  LOADING_SHOW: 'loading.show',
  LOADING_HIDE: 'loading.hide',
  MENU_NAVIGATE: 'menu.navigate',
  ROUTE_CHANGE: 'route.change',
  SESSION_EXPIRED: 'session_expired',
  NO_PERMISSION: 'NO_PERMISSION',
  LOGOUT: 'LOGOUT',
} as const

export type PortalActionName =
  | (typeof PortalAction)[keyof typeof PortalAction]
  | (string & {})
export type PortalMessageData = Record<string, unknown>

export interface PortalMessage {
  protocol: typeof IFRAME_BRIDGE_PROTOCOL
  version: typeof IFRAME_BRIDGE_VERSION
  id: string
  action: PortalActionName
  data: PortalMessageData
}

type PortalMessageHandler = (data: PortalMessageData, message: PortalMessage) => void

interface MessagePoster {
  postMessage(message: unknown, targetOrigin: string): void
}

export interface PortalBridgeEnvironment {
  eventTarget: EventTarget
  parentWindow: MessagePoster
  parentSource: MessageEventSource
  currentOrigin: string
  referrer: string
  inIframe: boolean
}

export interface PortalBridgeOptions {
  allowedOrigins?: string[]
  targetOrigin?: string
  environment?: PortalBridgeEnvironment
}

let messageSequence = 0

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : null
}

function normalizeOrigin(value: string, baseOrigin: string): string | null {
  const candidate = value.trim()
  if (!candidate) return null
  try {
    return new URL(candidate, baseOrigin).origin
  } catch {
    return null
  }
}

export function parsePortalOrigins(value: string | undefined): string[] {
  if (!value) return []
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function createPortalMessage(
  action: PortalActionName,
  data: PortalMessageData = {},
): PortalMessage {
  messageSequence += 1
  return {
    protocol: IFRAME_BRIDGE_PROTOCOL,
    version: IFRAME_BRIDGE_VERSION,
    id: `msg_${Date.now()}_${messageSequence}`,
    action,
    data,
  }
}

export function isPortalMessage(value: unknown): value is PortalMessage {
  const message = asObject(value)
  return Boolean(
    message?.protocol === IFRAME_BRIDGE_PROTOCOL
      && message.version === IFRAME_BRIDGE_VERSION
      && typeof message.id === 'string'
      && message.id.length > 0
      && typeof message.action === 'string'
      && message.action.length > 0
      && asObject(message.data),
  )
}

function browserEnvironment(): PortalBridgeEnvironment {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    const eventTarget = new EventTarget()
    const parentWindow: MessagePoster = { postMessage: () => undefined }
    return {
      eventTarget,
      parentWindow,
      parentSource: parentWindow as MessageEventSource,
      currentOrigin: 'http://localhost',
      referrer: '',
      inIframe: false,
    }
  }
  return {
    eventTarget: window,
    parentWindow: window.parent,
    parentSource: window.parent,
    currentOrigin: window.location.origin,
    referrer: document.referrer,
    inIframe: window.parent !== window,
  }
}

export class IframeBridge {
  private readonly environment: PortalBridgeEnvironment
  private readonly allowedOrigins: Set<string>
  private readonly handlers = new Map<string, Set<PortalMessageHandler>>()
  private started = false
  readonly targetOrigin: string

  constructor(options: PortalBridgeOptions = {}) {
    this.environment = options.environment ?? browserEnvironment()
    const configuredOrigins = (options.allowedOrigins ?? [])
      .map((origin) => normalizeOrigin(origin, this.environment.currentOrigin))
      .filter((origin): origin is string => Boolean(origin))

    this.allowedOrigins = new Set(configuredOrigins)
    // 同源部署是方案推荐方式；即使未配置额外来源，也允许同源门户通信。
    this.allowedOrigins.add(this.environment.currentOrigin)

    const configuredTarget = normalizeOrigin(
      options.targetOrigin ?? '',
      this.environment.currentOrigin,
    )
    const referrerOrigin = normalizeOrigin(
      this.environment.referrer,
      this.environment.currentOrigin,
    )

    if (configuredTarget && this.allowedOrigins.has(configuredTarget)) {
      this.targetOrigin = configuredTarget
    } else if (referrerOrigin && this.allowedOrigins.has(referrerOrigin)) {
      this.targetOrigin = referrerOrigin
    } else {
      this.targetOrigin = configuredOrigins[0] ?? this.environment.currentOrigin
    }
  }

  get isInIframe(): boolean {
    return this.environment.inIframe
  }

  start(): void {
    if (!this.isInIframe || this.started) return
    this.environment.eventTarget.addEventListener('message', this.handleMessage)
    this.started = true
  }

  stop(): void {
    if (!this.started) return
    this.environment.eventTarget.removeEventListener('message', this.handleMessage)
    this.started = false
  }

  on(action: PortalActionName, handler: PortalMessageHandler): () => void {
    const handlers = this.handlers.get(action) ?? new Set<PortalMessageHandler>()
    handlers.add(handler)
    this.handlers.set(action, handlers)
    return () => {
      handlers.delete(handler)
      if (handlers.size === 0) this.handlers.delete(action)
    }
  }

  send(action: PortalActionName, data: PortalMessageData = {}): boolean {
    if (!this.isInIframe) return false
    this.environment.parentWindow.postMessage(
      createPortalMessage(action, data),
      this.targetOrigin,
    )
    return true
  }

  ready(source: string, title: string): boolean {
    return this.send(PortalAction.PAGE_READY, { source, title })
  }

  private readonly handleMessage = (event: Event): void => {
    const messageEvent = event as MessageEvent<unknown>
    if (messageEvent.source !== this.environment.parentSource) return
    if (!this.allowedOrigins.has(messageEvent.origin)) return
    const message = messageEvent.data
    if (!isPortalMessage(message)) return

    const handlers = this.handlers.get(message.action)
    if (!handlers) return
    handlers.forEach((handler) => handler(message.data, message))
  }
}

const envAllowedOrigins = parsePortalOrigins(import.meta.env.VITE_PORTAL_ALLOWED_ORIGINS)

export const portalBridge = new IframeBridge({
  allowedOrigins: envAllowedOrigins,
  targetOrigin: import.meta.env.VITE_PORTAL_TARGET_ORIGIN,
})

function isTruthyFlag(value: unknown): boolean {
  const candidate = Array.isArray(value) ? value[0] : value
  return typeof candidate === 'string'
    && ['1', 'true', 'yes', 'on'].includes(candidate.toLowerCase())
}

function locationEmbeddedFlag(): boolean {
  if (typeof window === 'undefined') return false
  const searchFlag = new URLSearchParams(window.location.search).get('embedded')
  const hashQuery = window.location.hash.includes('?')
    ? window.location.hash.slice(window.location.hash.indexOf('?') + 1)
    : ''
  const hashFlag = new URLSearchParams(hashQuery).get('embedded')
  return isTruthyFlag(searchFlag) || isTruthyFlag(hashFlag)
}

export function isPortalEmbeddedMode(routeFlag?: unknown): boolean {
  return portalBridge.isInIframe
    || isTruthyFlag(routeFlag)
    || locationEmbeddedFlag()
    || isTruthyFlag(import.meta.env.VITE_PORTAL_EMBEDDED_DEFAULT)
}
