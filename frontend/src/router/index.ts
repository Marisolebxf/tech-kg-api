import { createRouter, createWebHistory } from 'vue-router'

import { appBase, authDisabled } from '../config'

import { useAuthStore } from '../stores/auth'
import { isPortalEmbeddedMode } from '../portal/iframeBridge'
import BusinessServiceView from '../views/business-service/BusinessServiceView.vue'
import LoginView from '../views/auth/LoginView.vue'
import UserCenterView from '../views/auth/UserCenterView.vue'
import AccountSecurityView from '../views/auth/AccountSecurityView.vue'
import OperationLogsView from '../views/auth/OperationLogsView.vue'
import PlatformWorkbenchView from '../views/platform/PlatformWorkbenchView.vue'
import OperationsCenterView from '../views/platform/OperationsCenterView.vue'
import ManualReviewWorkspaceView from '../views/platform/ManualReviewWorkspaceView.vue'
import TDirectDemoView from '../views/platform/TDirectDemoView.vue'
import ProcessInstanceDetailView from '../views/platform/ProcessInstanceDetailView.vue'
import SchemaBrowserView from '../views/platform/SchemaBrowserView.vue'
import GraphBuildView from '../views/platform/GraphBuildView.vue'
import EntityListView from '../views/platform/EntityListView.vue'
import ConfigurationManagementView from '../views/platform/ConfigurationManagementView.vue'
import AccessDeniedView from '../views/auth/AccessDeniedView.vue'
import CorrectionCenterView from '../views/admin/CorrectionCenterView.vue'
import MemberManagementView from '../views/admin/MemberManagementView.vue'

const serviceRoutes = [
  { path: '/expert-direct', name: 'expert-direct', title: '科技专家/人才直接关系', serviceKey: 'expert-direct' },
  { path: '/node-indirect', name: 'node-indirect', title: '科技单节点间接关系', serviceKey: 'node-indirect' },
  { path: '/two-point-achievement', name: 'two-point-achievement', title: '科技两点合作成果', serviceKey: 'two-point-achievement' },
  { path: '/expert-colleague', name: 'expert-colleague', title: '科技专家同事关系', serviceKey: 'expert-colleague' },
  { path: '/expert-alumni', name: 'expert-alumni', title: '科技专家校友关系', serviceKey: 'expert-alumni' },
  { path: '/paper-cooperation', name: 'paper-cooperation', title: '科技专家论文合作关系', serviceKey: 'paper-cooperation' },
  { path: '/enterprise-relation', name: 'enterprise-relation', title: '重点关注科技企业关系', serviceKey: 'enterprise-relation' },
  { path: '/industry-chain-event', name: 'industry-chain-event', title: '科技产业链点TOP-N事件关系', serviceKey: 'industry-chain-event' },
  { path: '/industry-chain-panorama', name: 'industry-chain-panorama', title: '科技产业链全景图', serviceKey: 'industry-chain-panorama' },
] as const

export const router = createRouter({
  history: createWebHistory(appBase),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '统一身份登录', public: true, layout: 'blank' },
    },
    {
      path: '/forbidden',
      name: 'forbidden',
      component: AccessDeniedView,
      meta: { title: '无管理端权限' },
    },
    {
      path: '/',
      redirect: '/overview',
    },
    {
      path: '/overview',
      name: 'overview',
      component: PlatformWorkbenchView,
      props: { initialTab: 'overview' },
      meta: { title: '平台总览' },
    },
    {
      path: '/data-processing',
      redirect: '/graph-build',
    },
    {
      path: '/graph-construction',
      redirect: '/graph-build',
    },
    {
      path: '/graph-query',
      name: 'graph-query',
      component: PlatformWorkbenchView,
      props: { initialTab: 'query' },
      meta: { title: '图谱查询' },
    },
    {
      path: '/graph-query/entities',
      name: 'graph-query-entities',
      component: EntityListView,
      meta: { title: '实体列表' },
    },
    { path: '/admin', redirect: '/admin/reviews' },
    { path: '/admin/corrections', name: 'admin-corrections', component: CorrectionCenterView, props: { scope: 'admin' }, meta: { title: '修正记录', admin: true } },
    { path: '/admin/reviews', name: 'admin-reviews', component: CorrectionCenterView, props: { scope: 'admin', mode: 'review' }, meta: { title: '审核与同步', admin: true } },
    { path: '/admin/members', name: 'admin-members', component: MemberManagementView, meta: { title: '成员管理', admin: true } },
    { path: '/admin/schema', redirect: '/admin/corrections' },
    { path: '/admin/tasks', redirect: '/admin/corrections' },
    { path: '/admin/pipelines', redirect: '/admin/corrections' },
    { path: '/admin/configurations', redirect: '/admin/corrections' },
    { path: '/schema', name: 'schema', component: SchemaBrowserView, meta: { title: 'Schema 管理' } },
    { path: '/graph-build', name: 'graph-build', component: GraphBuildView, meta: { title: '图谱构建' } },
    { path: '/graph-build/jobs/:jobId', name: 'job-detail', component: ProcessInstanceDetailView, meta: { title: '任务详情' } },
    { path: '/manual-review', name: 'manual-review', component: OperationsCenterView, props: { mode: 'review' }, meta: { title: '人工审核' } },
    { path: '/manual-review/task/:instanceId', name: 'manual-review-detail', component: ManualReviewWorkspaceView, meta: { title: '人工审核详情' } },
    { path: '/demo/t-direct', name: 'demo-t-direct', component: TDirectDemoView, meta: { title: 'T_DIRECT Demo', public: true } },
    { path: '/configurations', name: 'configurations', component: ConfigurationManagementView, meta: { title: '配置管理' } },
    { path: '/user-center', name: 'user-center', component: UserCenterView, meta: { title: '个人中心' } },
    { path: '/account-security', name: 'account-security', component: AccountSecurityView, meta: { title: '账号与安全' } },
    { path: '/operation-logs', name: 'operation-logs', component: OperationLogsView, meta: { title: '操作记录' } },
    { path: '/user-permissions', redirect: '/user-center' },
    { path: '/admin/task-detail/:area/:taskId', name: 'admin-task-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情', admin: true } },
    { path: '/admin/processing-instance/:instanceId', name: 'admin-processing-instance-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情', admin: true } },
    { path: '/task-detail/:area/:taskId', name: 'task-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情' } },
    { path: '/processing-instance/:instanceId', name: 'processing-instance-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情' } },
    // { path: '/graph-versions', redirect: '/graph-build' },
    {
      path: '/business-service',
      redirect: '/expert-direct',
    },
    ...serviceRoutes.map((route) => ({
      path: route.path,
      name: route.name,
      component: BusinessServiceView,
      meta: { title: route.title },
    })),
  ],
})

function loginRedirect(fullPath: string, error?: string) {
  if (isPortalEmbeddedMode()) {
    return {
      path: '/login',
      query: { embedded: '1', portalState: 'session-expired' },
    }
  }
  return {
    path: '/login',
    query: {
      redirect: fullPath,
      ...(error ? { error } : {}),
    },
  }
}

router.beforeEach(async (to) => {
  if (authDisabled) {
    return to.name === 'login' ? { path: '/overview' } : true
  }

  if (to.meta.public) return true

  const authStore = useAuthStore()
  try {
    const profile = await authStore.loadCurrentUser()
    if (!profile) {
      return loginRedirect(to.fullPath, '登录状态已失效或已超时，请重新登录')
    }
    const requiredPermission = typeof to.meta.permission === 'string' ? to.meta.permission : ''
    if (to.meta.admin === true && !profile.isAdmin) {
      return { path: '/forbidden', query: { redirect: to.fullPath } }
    }
    if (
      requiredPermission
      && !profile.permissions.includes('*')
      && !profile.permissions.includes(requiredPermission)
    ) {
      return { path: '/overview', query: { denied: requiredPermission } }
    }
    return true
  } catch {
    return loginRedirect(to.fullPath, '登录服务暂时不可用，请稍后重试')
  }
})
