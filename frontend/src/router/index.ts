import { createRouter, createWebHashHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import BusinessServiceView from '../views/business-service/BusinessServiceView.vue'
import LoginView from '../views/auth/LoginView.vue'
import UserCenterView from '../views/auth/UserCenterView.vue'
import AccountSecurityView from '../views/auth/AccountSecurityView.vue'
import OperationLogsView from '../views/auth/OperationLogsView.vue'
import PlatformWorkbenchView from '../views/platform/PlatformWorkbenchView.vue'
import OperationsCenterView from '../views/platform/OperationsCenterView.vue'
import ManualReviewWorkspaceView from '../views/platform/ManualReviewWorkspaceView.vue'
import ProcessInstanceDetailView from '../views/platform/ProcessInstanceDetailView.vue'
import TaskCenterView from '../views/platform/TaskCenterView.vue'
import SchemaBrowserView from '../views/platform/SchemaBrowserView.vue'
import ConfigurationManagementView from '../views/platform/ConfigurationManagementView.vue'
import PipelineDesignerView from '../views/platform/PipelineDesignerView.vue'

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
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '统一身份登录', public: true, layout: 'blank' },
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
      redirect: { path: '/tasks', query: { module: '数据处理' } },
    },
    {
      path: '/graph-construction',
      redirect: { path: '/tasks', query: { module: '图谱构建' } },
    },
    {
      path: '/graph-query',
      name: 'graph-query',
      component: PlatformWorkbenchView,
      props: { initialTab: 'query' },
      meta: { title: '图谱查询' },
    },
    { path: '/schema', name: 'schema', component: SchemaBrowserView, meta: { title: '图谱 Schema' } },
    { path: '/pipelines', name: 'pipelines', component: PipelineDesignerView, meta: { title: '自定义抽取 Pipeline' } },
    { path: '/configurations', name: 'configurations', component: ConfigurationManagementView, meta: { title: '配置管理' } },
    { path: '/tasks', name: 'tasks', component: TaskCenterView, meta: { title: '图谱构建' } },
    { path: '/manual-review', name: 'manual-review', component: OperationsCenterView, props: { mode: 'review' }, meta: { title: '人工处理平台' } },
    { path: '/manual-review/task/:instanceId', name: 'manual-review-detail', component: ManualReviewWorkspaceView, meta: { title: '人工处理详情' } },
    { path: '/user-center', name: 'user-center', component: UserCenterView, meta: { title: '个人中心' } },
    { path: '/account-security', name: 'account-security', component: AccountSecurityView, meta: { title: '账号与安全' } },
    { path: '/operation-logs', name: 'operation-logs', component: OperationLogsView, meta: { title: '操作记录' } },
    { path: '/user-permissions', redirect: '/user-center' },
    { path: '/task-detail/:area/:taskId', name: 'task-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情' } },
    { path: '/processing-instance/:instanceId', name: 'processing-instance-detail', component: ProcessInstanceDetailView, meta: { title: '任务实例详情' } },
    // { path: '/graph-versions', redirect: { path: '/tasks', query: { module: '图谱版本' } } },
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

router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const authStore = useAuthStore()
  try {
    const profile = await authStore.loadCurrentUser()
    if (!profile) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
    const requiredPermission = typeof to.meta.permission === 'string' ? to.meta.permission : ''
    if (
      requiredPermission
      && !profile.permissions.includes('*')
      && !profile.permissions.includes(requiredPermission)
    ) {
      return { path: '/overview', query: { denied: requiredPermission } }
    }
    return true
  } catch {
    return {
      path: '/login',
      query: { redirect: to.fullPath, error: '登录服务暂时不可用，请稍后重试' },
    }
  }
})
