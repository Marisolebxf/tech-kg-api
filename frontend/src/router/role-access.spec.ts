import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  authDisabled: false,
  graphVisualization: false,
  embedded: false,
  loadCurrentUser: vi.fn(),
}))

vi.mock('../config', () => ({
  appBase: '/',
  apiBase: '/',
  get authDisabled() { return mocks.authDisabled },
  get graphVisualizationEnabled() { return mocks.graphVisualization },
}))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ loadCurrentUser: mocks.loadCurrentUser }) }))
vi.mock('../portal/iframeBridge', () => ({
  isPortalEmbeddedMode: () => mocks.embedded,
  PortalAction: { SESSION_EXPIRED: 'session-expired' },
  portalBridge: { isInIframe: false, send: vi.fn() },
}))
vi.mock('../views/business-service/BusinessServiceView.vue', () => ({ default: {} }))
vi.mock('../views/auth/LoginView.vue', () => ({ default: {} }))
vi.mock('../views/auth/UserCenterView.vue', () => ({ default: {} }))
vi.mock('../views/auth/AccountSecurityView.vue', () => ({ default: {} }))
vi.mock('../views/auth/OperationLogsView.vue', () => ({ default: {} }))
vi.mock('../views/auth/AccessDeniedView.vue', () => ({ default: {} }))
vi.mock('../views/platform/PlatformWorkbenchView.vue', () => ({ default: {} }))
vi.mock('../views/platform/OperationsCenterView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ManualReviewWorkspaceView.vue', () => ({ default: {} }))
vi.mock('../views/platform/TDirectDemoView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ProcessInstanceDetailView.vue', () => ({ default: {} }))
vi.mock('../views/platform/SchemaBrowserView.vue', () => ({ default: {} }))
vi.mock('../views/platform/GraphBuildView.vue', () => ({ default: {} }))
vi.mock('../views/platform/EntityListView.vue', () => ({ default: {} }))
vi.mock('../views/platform/GraphVisualizationView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ConfigurationManagementView.vue', () => ({ default: {} }))

import { router } from './index'

// 图谱构建/人工审核等管理页仅管理员可见；平台总览与图谱查询对所有登录用户开放。
const restrictedPaths = [
  '/schema', '/graph-build', '/graph-build/jobs/job-1', '/manual-review',
  '/manual-review/task/instance-1', '/configurations', '/task-detail/extract/task-1',
  '/processing-instance/instance-1',
]
const sharedPaths = [
  '/expert-direct', '/node-indirect',
  '/two-point-achievement', '/expert-colleague', '/expert-alumni', '/paper-cooperation',
  '/enterprise-relation', '/industry-chain-event', '/industry-chain-panorama',
]

beforeEach(async () => {
  mocks.authDisabled = false
  mocks.embedded = false
  mocks.loadCurrentUser.mockReset().mockResolvedValue({ isAdmin: false, permissions: [] })
  await router.push('/login')
})

describe('角色控制与默认入口', () => {
  it.each(restrictedPaths)('业务开发维护可以访问 %s', async (path) => {
    mocks.loadCurrentUser.mockResolvedValue({ businessRbacEnabled: true, canDevelop: true, isAdmin: false, permissions: [] })
    await router.push(path)
    expect(router.currentRoute.value.path).toBe(path)
  })
  it('旧模式不因 canDevelop 字段意外放开管理页面', async () => {
    mocks.loadCurrentUser.mockResolvedValue({ businessRbacEnabled: false, canDevelop: true, isAdmin: false, permissions: [] })
    await router.push('/configurations')
    expect(router.currentRoute.value.path).toBe('/forbidden')
  })
  it('公司测试限制优先于业务开发维护角色', async () => {
    mocks.loadCurrentUser.mockResolvedValue({ businessOnly: true, businessRbacEnabled: true, canDevelop: true, isAdmin: false, permissions: ['*'] })
    await router.push('/configurations')
    expect(router.currentRoute.value.path).toBe('/expert-direct')
  })
  it.each(['/overview', '/', '/graph-query', '/graph-query/entities', '/demo/t-direct', ...restrictedPaths])('业务限定账号无法访问 %s', async (path) => {
    mocks.loadCurrentUser.mockResolvedValue({ businessOnly: true, isAdmin: true, permissions: ['*'] })
    await router.push(`${path}?embedded=1#entry`)
    expect(router.currentRoute.value.path).toBe('/expert-direct')
    expect(router.currentRoute.value.query.embedded).toBe('1')
    expect(router.currentRoute.value.hash).toBe('#entry')
  })

  it.each([...sharedPaths, '/user-center', '/account-security', '/operation-logs'])('业务限定账号仍可访问 %s', async (path) => {
    mocks.loadCurrentUser.mockResolvedValue({ businessOnly: true, isAdmin: false, permissions: [] })
    await router.push(path)
    expect(router.currentRoute.value.path).toBe(path)
  })

  it.each(restrictedPaths)('普通用户直接访问 %s 被拒绝', async (path) => {
    await router.push(path)
    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(router.currentRoute.value.query.redirect).toBe(path)
  })

  it.each(sharedPaths)('普通用户可访问 %s', async (path) => {
    await router.push(path)
    expect(router.currentRoute.value.path).toBe(path)
    expect(mocks.loadCurrentUser).toHaveBeenCalledWith(true)
  })

  it.each(['/overview', '/'])('普通用户可进入平台总览并保留门户参数', async (path) => {
    await router.push(`${path}?embedded=1#entry`)
    expect(router.currentRoute.value.path).toBe('/overview')
    expect(router.currentRoute.value.query.embedded).toBe('1')
    expect(router.currentRoute.value.hash).toBe('#entry')
  })

  it('旧管理路由重定向也经过角色检查', async () => {
    await router.push('/data-processing')
    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(router.currentRoute.value.query.redirect).toBe('/graph-build')
  })

  it('管理员可访问总览和全部管理页', async () => {
    mocks.loadCurrentUser.mockResolvedValue({ isAdmin: true, permissions: [] })
    for (const path of ['/overview', ...restrictedPaths, ...sharedPaths]) {
      await router.push(path)
      expect(router.currentRoute.value.path).toBe(path)
    }
  })

  it('后端撤权后下一次导航按普通用户权限执行', async () => {
    mocks.loadCurrentUser.mockResolvedValue({ isAdmin: true, permissions: [] })
    await router.push('/schema')
    mocks.loadCurrentUser.mockResolvedValue({ isAdmin: false, permissions: [] })
    await router.push('/configurations')
    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(mocks.loadCurrentUser).toHaveBeenLastCalledWith(true)
  })

  it('未登录用户不能进入共享业务页', async () => {
    mocks.loadCurrentUser.mockResolvedValue(null)
    await router.push('/expert-direct')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/expert-direct')
  })

  it('iframe 内会话失效仍走现有门户登录提示', async () => {
    mocks.embedded = true
    mocks.loadCurrentUser.mockResolvedValue(null)
    await router.push('/expert-direct')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query).toEqual({ embedded: '1', portalState: 'session-expired' })
  })

  it('后端明确允许的免登录开发身份保留管理页访问', async () => {
    mocks.authDisabled = true
    mocks.loadCurrentUser.mockResolvedValue({ authEnabled: false, isAdmin: true, permissions: [] })
    await router.push('/schema')
    expect(router.currentRoute.value.path).toBe('/schema')
    expect(mocks.loadCurrentUser).toHaveBeenCalledWith(true)
  })

  it.each(restrictedPaths)('前端误关闭认证也不能放行普通用户访问 %s', async (path) => {
    mocks.authDisabled = true
    await router.push(path)
    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(mocks.loadCurrentUser).toHaveBeenCalledWith(true)
  })

  it('前端误关闭认证不跳过未登录和业务限定检查', async () => {
    mocks.authDisabled = true
    mocks.loadCurrentUser.mockResolvedValue(null)
    await router.push('/overview')
    expect(router.currentRoute.value.path).toBe('/login')
    mocks.loadCurrentUser.mockResolvedValue({ businessOnly: true, isAdmin: true, permissions: ['*'] })
    await router.push('/schema')
    expect(router.currentRoute.value.path).toBe('/expert-direct')
  })

  it('前端误关闭认证但身份服务异常时不得进入管理页', async () => {
    mocks.authDisabled = true
    mocks.loadCurrentUser.mockRejectedValue(new Error('identity unavailable'))
    await router.push('/manual-review')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})

describe('图谱可视化部署开关', () => {
  it('默认隐藏：直达 /graph-query/visualization 归拢到综合查询', async () => {
    mocks.graphVisualization = false
    await router.push('/graph-query/visualization')
    expect(router.currentRoute.value.path).toBe('/graph-query')
  })

  it('开启后可达', async () => {
    mocks.graphVisualization = true
    await router.push('/graph-query/visualization')
    expect(router.currentRoute.value.name).toBe('graph-query-visualization')
  })
})
