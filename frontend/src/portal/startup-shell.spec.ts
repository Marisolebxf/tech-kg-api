import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const html = readFileSync('index.html', 'utf8')
const script = readFileSync('public/startup-shell.v1.js', 'utf8')
const parent = { postMessage: vi.fn() }
let windowListeners: ReturnType<typeof vi.spyOn>
let documentListeners: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  document.body.innerHTML = new DOMParser().parseFromString(html, 'text/html').body.innerHTML
  vi.stubGlobal('parent', parent)
  delete window.__RUNTIME_CONFIG__
  windowListeners = vi.spyOn(window, 'addEventListener')
  documentListeners = vi.spyOn(document, 'addEventListener')
})
afterEach(() => {
  for (const [name, listener, options] of windowListeners.mock.calls) window.removeEventListener(name, listener, options)
  for (const [name, listener, options] of documentListeners.mock.calls) document.removeEventListener(name, listener, options)
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete window.__KG_PAGE_LOADING__
  delete window.__RUNTIME_CONFIG__
  document.body.innerHTML = ''
})
function boot() { window.eval(script) }
const shell = () => document.getElementById('kg-page-loading')!

describe('standalone startup shell', () => {
  it('is present before the runtime config and the application bundle', () => {
    expect(html.indexOf('src="%BASE_URL%startup-shell.v1.js"')).toBeLessThan(html.indexOf('id="kg-page-loading"'))
    expect(html.indexOf('src="%BASE_URL%startup-shell.v1.js"')).toBeLessThan(html.indexOf('id="kg-runtime-config"'))
    expect(html.indexOf('id="kg-runtime-config"')).toBeLessThan(html.indexOf('src="/src/main.ts"'))
    boot()
    expect(shell().hidden).toBe(false)
    expect(document.getElementById('app')!.hasAttribute('inert')).toBe(true)
    expect(parent.postMessage).toHaveBeenCalledWith(expect.objectContaining({
      action: 'loading.hide', protocol: 'iframe-bridge', version: '1.0',
    }), window.location.origin)
    expect(parent.postMessage.mock.calls.some(([message]) => message.action === 'page.ready')).toBe(false)
  })

  it('can install in the head and start when the shell appears without waiting for app modules', async () => {
    const body = document.body.innerHTML
    document.body.innerHTML = ''
    boot()
    expect(parent.postMessage).not.toHaveBeenCalled()
    document.body.innerHTML = body
    await Promise.resolve()
    expect(window.__KG_PAGE_LOADING__).toBeDefined()
    expect(parent.postMessage).toHaveBeenCalledWith(expect.objectContaining({ action: 'loading.hide' }), window.location.origin)
  })

  it('turns a stalled startup into a local retry UI after twenty seconds', () => {
    boot()
    vi.advanceTimersByTime(19_999)
    expect(document.getElementById('kg-loading-retry')!.hidden).toBe(true)
    vi.advanceTimersByTime(1)
    expect(shell().getAttribute('data-state')).toBe('error')
    expect(document.getElementById('kg-loading-retry')!.hidden).toBe(false)
    expect(parent.postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'loading.hide' }), window.location.origin)
    // Slow requests may still finish naturally; the timeout does not bypass auth or destroy state.
    window.__KG_PAGE_LOADING__!.finish()
    expect(shell().hidden).toBe(true)
    expect(document.getElementById('app')!.hasAttribute('inert')).toBe(false)
  })

  it('shows a local error when the main JavaScript cannot be downloaded', () => {
    boot()
    const resource = document.createElement('script')
    resource.src = '/missing-main.js'
    document.body.append(resource)
    resource.dispatchEvent(new Event('error'))
    expect(shell().getAttribute('data-state')).toBe('error')
    expect(document.getElementById('kg-loading-retry')!.hidden).toBe(false)
  })

  it('does not treat an optional runtime config or an image failure as an app failure', () => {
    boot()
    document.getElementById('kg-runtime-config')!.dispatchEvent(new Event('error'))
    const image = document.createElement('img')
    document.body.append(image)
    image.dispatchEvent(new Event('error'))
    expect(shell().getAttribute('data-state')).toBe('loading')
  })

  it('uses the configured allowlisted portal after runtime config loads, never a wildcard', () => {
    boot()
    window.__RUNTIME_CONFIG__ = {
      portalAllowedOrigins: 'https://portal.example', portalTargetOrigin: 'https://portal.example',
    }
    document.getElementById('kg-runtime-config')!.dispatchEvent(new Event('load'))
    expect(parent.postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'loading.hide' }), 'https://portal.example')
    expect(parent.postMessage.mock.calls.every(([, target]) => target !== '*')).toBe(true)
  })

  it('does not send to a configured target outside the origin allowlist', () => {
    window.__RUNTIME_CONFIG__ = { portalTargetOrigin: 'https://untrusted.example' }
    boot()
    expect(parent.postMessage).toHaveBeenCalledWith(expect.anything(), window.location.origin)
  })

  it('does not notify a parent when running independently', () => {
    vi.stubGlobal('parent', window)
    boot()
    expect(parent.postMessage).not.toHaveBeenCalled()
  })

  it('clears old navigation timers on completion and on a new navigation', () => {
    boot()
    vi.advanceTimersByTime(10_000)
    window.__KG_PAGE_LOADING__!.start('/expert-alumni')
    vi.advanceTimersByTime(10_000)
    expect(shell().getAttribute('data-state')).toBe('loading')
    window.__KG_PAGE_LOADING__!.finish()
    vi.advanceTimersByTime(30_000)
    expect(shell().hidden).toBe(true)
  })
})
