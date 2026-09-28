/**
 * 面包屑层级（Arco Design Breadcrumb 规范）：首项为图标入口（回平台总览），
 * 中间级按侧边栏导航树展开（分组 → 子组 → 页面），`/` 分隔，末项恒为当前页。
 * 层级与 AppLayout 侧边栏同口径；详情页（任务详情/人工审核详情）挂在所属功能页之下，
 * 取代页内「← 返回」链接。
 */
export interface BreadcrumbCrumb {
  label: string
  /** 有 to 的中间级可点击回上级；末项恒为当前页不可点。 */
  to?: string
}

/** 面包屑首项（图标）指向平台总览。 */
export const breadcrumbHomeTo = '/overview'

/** 侧边栏导航分组名（与 AppLayout 导航结构一致）。 */
const GROUP_BUILD = '图谱建设与治理'
const GROUP_PLATFORM = '平台管理'
const GROUP_SERVICE = '知识图谱构建服务'
const QUERY_GROUP = '图谱查询'

/** 业务服务折叠组标题（产品命名自带「/」，面包屑按原样展示）。 */
export const businessServiceGroupTitle = '科技专家/人才知识推理构建服务'

/** 九大业务服务子功能：路径 → 页面名（父级为业务服务折叠组）。 */
const SERVICE_TITLES: Record<string, string> = {
  '/expert-direct': '科技专家/人才直接关系',
  '/node-indirect': '科技单节点间接关系',
  '/two-point-achievement': '科技两点合作成果',
  '/expert-colleague': '科技专家同事关系',
  '/expert-alumni': '科技专家校友关系',
  '/paper-cooperation': '科技专家论文合作关系',
  '/enterprise-relation': '重点关注科技企业关系',
  '/industry-chain-event': '科技产业链点TOP-N事件关系',
  '/industry-chain-panorama': '科技产业链全景图',
}

/** 图谱查询折叠组：路径 → 页面名。 */
const QUERY_TITLES: Record<string, string> = {
  '/graph-query': '综合查询',
  '/graph-query/entities': '实体列表',
  '/graph-query/visualization': '图谱可视化',
}

/** 顶级功能页与账号页：路径 → 页面名。 */
const PAGE_TITLES: Record<string, string> = {
  '/overview': '平台总览',
  '/schema': 'Schema 管理',
  '/graph-build': '图谱构建',
  '/manual-review': '人工审核',
  '/configurations': '配置管理',
  '/user-center': '个人中心',
  '/account-security': '账号与安全',
  '/operation-logs': '操作记录',
  '/demo/t-direct': 'T_DIRECT Demo',
}

/**
 * 生成当前路由的面包屑链条（不含首项图标，组件模板单独渲染）。
 * 末项为当前页；未收录的路径（无管理员权限、任务实例详情等直达页）只展示当前页。
 */
export function breadcrumbCrumbs(path: string, fallbackTitle: string): BreadcrumbCrumb[] {
  const current = (label: string): BreadcrumbCrumb => ({ label })
  const pageTitle = PAGE_TITLES[path] ?? QUERY_TITLES[path] ?? SERVICE_TITLES[path] ?? fallbackTitle

  // 图谱建设与治理（管理页）：分组 + 页面，详情页挂在功能页之下
  if (path === '/schema' || path === '/graph-build' || path === '/manual-review')
    return [{ label: GROUP_BUILD }, current(pageTitle)]
  if (path.startsWith('/graph-build/jobs/'))
    return [{ label: GROUP_BUILD }, { label: '图谱构建', to: '/graph-build' }, current('任务详情')]
  if (path.startsWith('/manual-review/task/'))
    return [{ label: GROUP_BUILD }, { label: '人工审核', to: '/manual-review' }, current('人工审核详情')]

  // 平台管理（管理页）
  if (path === '/configurations') return [{ label: GROUP_PLATFORM }, current(pageTitle)]

  // 知识图谱构建服务：图谱查询 / 业务服务两个折叠组
  if (QUERY_TITLES[path])
    return [{ label: GROUP_SERVICE }, { label: QUERY_GROUP, to: '/graph-query' }, current(pageTitle)]
  if (SERVICE_TITLES[path])
    return [
      { label: GROUP_SERVICE },
      { label: businessServiceGroupTitle, to: '/business-service' },
      current(pageTitle),
    ]

  // T_DIRECT 演示页挂在人工审核之下；账号与安全、操作记录挂在个人中心之下
  if (path === '/demo/t-direct') return [{ label: '人工审核', to: '/manual-review' }, current(pageTitle)]
  if (path === '/account-security' || path === '/operation-logs')
    return [{ label: '个人中心', to: '/user-center' }, current(pageTitle)]

  // 平台总览、个人中心、任务实例详情（总览卡片/审核页直达）等：仅首页图标 + 当前页
  return [current(pageTitle)]
}
