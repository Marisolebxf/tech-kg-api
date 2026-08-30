import { describe, expect, it, vi } from 'vitest'

import {
  IFRAME_BRIDGE_PROTOCOL,
  IFRAME_BRIDGE_VERSION,
  IframeBridge,
  PortalAction,
  createPortalMessage,
  isPortalMessage,
  parsePortalOrigins,
  type PortalBridgeEnvironment,
} from './iframeBridge'

function testEnvironment() {
  const eventTarget = new EventTarget()
  const parentSource = {} as MessageEventSource
  const postMessage = vi.fn()
  const environment: PortalBridgeEnvironment = {
    eventTarget,
    parentWindow: { postMessage },
    parentSource,
    currentOrigin: 'https://tech.example.com',
    referrer: 'https://portal.example.com/home',
    inIframe: true,
  }
  return { environment, eventTarget, parentSource, postMessage }
}

function bridgeMessage(action = PortalAction.LOGOUT) {
  return {
    protocol: IFRAME_BRIDGE_PROTOCOL,
    version: IFRAME_BRIDGE_VERSION,
    id: 'msg_test_1',
    action,
    data: {},
  }
}

describe('iframeBridge', () => {
  it('parses comma-separated portal origins', () => {
    expect(parsePortalOrigins(' https://portal.example.com,https://test.example.com '))
      .toEqual(['https://portal.example.com', 'https://test.example.com'])
  })

  it('creates the documented iframe-bridge envelope', () => {
    const message = createPortalMessage(PortalAction.PAGE_READY, {
      source: 'tech-kg-api',
      title: '平台总览',
    })
    expect(message).toMatchObject({
      protocol: 'iframe-bridge',
      version: '1.0',
      action: 'page.ready',
      data: { source: 'tech-kg-api', title: '平台总览' },
    })
    expect(message.id).toMatch(/^msg_\d+_\d+$/)
    expect(isPortalMessage(message)).toBe(true)
  })

  it('sends only to the configured target origin', () => {
    const { environment, postMessage } = testEnvironment()
    const bridge = new IframeBridge({
      environment,
      allowedOrigins: ['https://portal.example.com'],
      targetOrigin: 'https://portal.example.com',
    })

    expect(bridge.ready('tech-kg-api', '平台总览')).toBe(true)
    expect(postMessage).toHaveBeenCalledTimes(1)
    expect(postMessage.mock.calls[0][1]).toBe('https://portal.example.com')
    expect(postMessage.mock.calls[0][0]).toMatchObject({
      protocol: 'iframe-bridge',
      version: '1.0',
      action: 'page.ready',
    })
  })

  it('does not post messages outside an iframe', () => {
    const { environment, postMessage } = testEnvironment()
    const bridge = new IframeBridge({
      environment: { ...environment, inIframe: false },
      allowedOrigins: ['https://portal.example.com'],
    })

    expect(bridge.send(PortalAction.PAGE_READY)).toBe(false)
    expect(postMessage).not.toHaveBeenCalled()
  })

  it('accepts valid parent messages from an allowed origin', () => {
    const { environment, eventTarget, parentSource } = testEnvironment()
    const bridge = new IframeBridge({
      environment,
      allowedOrigins: ['https://portal.example.com'],
    })
    const handler = vi.fn()
    bridge.on(PortalAction.LOGOUT, handler)
    bridge.start()

    eventTarget.dispatchEvent(new MessageEvent('message', {
      source: parentSource,
      origin: 'https://portal.example.com',
      data: bridgeMessage(),
    }))

    expect(handler).toHaveBeenCalledTimes(1)
    bridge.stop()
  })

  it('rejects messages from another origin, source, or protocol', () => {
    const { environment, eventTarget, parentSource } = testEnvironment()
    const bridge = new IframeBridge({
      environment,
      allowedOrigins: ['https://portal.example.com'],
    })
    const handler = vi.fn()
    bridge.on(PortalAction.LOGOUT, handler)
    bridge.start()

    eventTarget.dispatchEvent(new MessageEvent('message', {
      source: parentSource,
      origin: 'https://evil.example.com',
      data: bridgeMessage(),
    }))
    eventTarget.dispatchEvent(new MessageEvent('message', {
      source: {} as MessageEventSource,
      origin: 'https://portal.example.com',
      data: bridgeMessage(),
    }))
    eventTarget.dispatchEvent(new MessageEvent('message', {
      source: parentSource,
      origin: 'https://portal.example.com',
      data: { ...bridgeMessage(), protocol: 'other-bridge' },
    }))

    expect(handler).not.toHaveBeenCalled()
    bridge.stop()
  })
})
