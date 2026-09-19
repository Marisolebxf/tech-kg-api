// 门户菜单编码与子应用路由并不相同；保持与当前门户菜单配置一致。
const portalRoutes = [
  { path: '/overview', code: 'overview' },
  { path: '/schema', code: 'schema' },
  { path: '/graph-build', code: 'graph_build' },
  { path: '/manual-review', code: 'manual_review' },
  { path: '/configurations', code: 'configurations' },
  { path: '/graph-query/entities', code: 'graph_query_entities' },
  { path: '/graph-query', code: 'graph_query' },
  { path: '/expert-direct', code: 'yjkjzstp_expert_direct' },
  { path: '/node-indirect', code: 'yjkjzstp_node_indirect' },
  { path: '/two-point-achievement', code: 'yjkjzstp_two_point_achievement' },
  { path: '/expert-colleague', code: 'yjkjzstp_expert_colleague' },
  { path: '/expert-alumni', code: 'yjkjzstp_expert_alumni' },
  { path: '/paper-cooperation', code: 'yjkjzstp_paper_cooperation' },
  { path: '/enterprise-relation', code: 'yjkjzstp_enterprise_relation' },
  { path: '/industry-chain-event', code: 'yjkjzstp_industry_chain_event' },
  { path: '/industry-chain-panorama', code: 'yjkjzstp_industry_chain_panorama' },
] as const

export function portalMenuCode(path: string): string | undefined {
  if (path.startsWith('/task-detail/') || path.startsWith('/processing-instance/')) return 'graph_build'
  return portalRoutes.find((item) => path === item.path || path.startsWith(`${item.path}/`))?.code
}

export function portalMenuPath(code: string): string | undefined {
  return portalRoutes.find((item) => item.code === code)?.path
}
