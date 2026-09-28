/**
 * 面包屑层级（Arco Design Breadcrumb 规范）：首项为首页图标（回平台总览），
 * 中间级按侧边栏导航树展开（分组 → 子组 → 页面），`/` 分隔，末项恒为当前页（蓝色高亮）。
 * 层级与 AppLayout 侧边栏同口径，除当前页外每级都可点击跳转（分组默认进首个子页）；
 * 详情页（任务详情/人工审核详情）挂在所属功能页之下，取代页内「← 返回」链接。
 */
export interface BreadcrumbCrumb {
  label: string
  /** 跳转目标；除末项（当前页）外每级都有。 */
  to?: string
}

/** 面包屑首项（图标）指向平台总览。 */
export const breadcrumbHomeTo = '/overview'

/** 侧边栏导航分组名与默认跳转（分组的第一个子页，与 AppLayout 导航结构一致）。 */
const GROUP_BUILD = { label: '图谱建设与治理', to: '/schema' }
const GROUP_PLATFORM = { label: '平台管理', to: '/configurations' }
const GROUP_SERVICE = { label: '知识图谱构建服务', to: '/graph-query' }
const QUERY_GROUP = { label: '图谱查询', to: '/graph-query' }

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
    return [{ ...GROUP_BUILD }, current(pageTitle)]
  if (path.startsWith('/graph-build/jobs/'))
    return [{ ...GROUP_BUILD }, { label: '图谱构建', to: '/graph-build' }, current('任务详情')]
  if (path.startsWith('/manual-review/task/'))
    return [{ ...GROUP_BUILD }, { label: '人工审核', to: '/manual-review' }, current('人工审核详情')]

  // 平台管理（管理页）
  if (path === '/configurations') return [{ ...GROUP_PLATFORM }, current(pageTitle)]

  // 知识图谱构建服务：图谱查询 / 业务服务两个折叠组
  if (QUERY_TITLES[path])
    return [{ ...GROUP_SERVICE }, { ...QUERY_GROUP }, current(pageTitle)]
  if (SERVICE_TITLES[path])
    return [
      { ...GROUP_SERVICE },
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

/**
 * 行首「<」返回按钮的兜底目标（应用内无上一页时）：从最近的上级取第一个
 * 不落回当前页的链接；都没有（如平台总览首页）返回首页本身，按钮由组件按需隐藏。
 */
export function breadcrumbBackTarget(
  path: string,
  crumbs: BreadcrumbCrumb[],
): BreadcrumbCrumb & { to: string } {
  for (let i = crumbs.length - 2; i >= 0; i--) {
    const item = crumbs[i]
    if (!item.to || item.to === path) continue
    // 业务服务组入口 /business-service 重定向到首个服务页：当前就在服务页时等价于自页，跳过
    if (item.to === '/business-service' && SERVICE_TITLES[path]) continue
    return { label: item.label, to: item.to }
  }
  return { label: '平台总览', to: breadcrumbHomeTo }
}
