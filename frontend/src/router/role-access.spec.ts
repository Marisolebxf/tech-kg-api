import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  authDisabled: false,
  embedded: false,
  loadCurrentUser: vi.fn(),
}))

vi.mock('../config', () => ({
  appBase: '/',
  apiBase: '/',
  get authDisabled() { return mocks.authDisabled },
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
vi.mock('../views/platform/ConfigurationManagementView.vue', () => ({ default: {} }))
vi.mock('../views/admin/CorrectionCenterView.vue', () => ({ default: {} }))
vi.mock('../views/admin/MemberManagementView.vue', () => ({ default: {} }))

import { router } from './index'

// 图谱查询（综合查询/实体列表）按产品决策并入管理端，仅管理员可见。
const restrictedPaths = [
  '/schema', '/graph-build', '/graph-build/jobs/job-1', '/manual-review',
  '/manual-review/task/instance-1', '/configurations', '/task-detail/extract/task-1',
  '/processing-instance/instance-1', '/admin/members', '/admin/reviews', '/admin/corrections',
  '/admin/task-detail/extract/task-1', '/admin/processing-instance/instance-1',
  '/graph-query', '/graph-query/entities',
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

  it.each(['/overview', '/'])('普通用户从 %s 落到专家直达并保留门户参数', async (path) => {
    await router.push(`${path}?embedded=1#entry`)
    expect(router.currentRoute.value.fullPath).toBe('/expert-direct?embedded=1#entry')
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

  it('显式免登录开发模式保留管理页访问', async () => {
    mocks.authDisabled = true
    await router.push('/schema')
    expect(router.currentRoute.value.path).toBe('/schema')
    expect(mocks.loadCurrentUser).not.toHaveBeenCalled()
  })
})
