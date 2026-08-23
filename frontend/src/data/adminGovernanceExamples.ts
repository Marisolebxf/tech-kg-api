import type { CorrectionRecord, PlatformMember } from '../api/corrections'

const EXAMPLE_CORRECTIONS: CorrectionRecord[] = [
  {
    id: 'example-correction-001', targetType: 'expert', operation: 'update', targetId: 'person_0512632S',
    title: '修正专家所属机构', reason: '专家最新任职信息与图谱记录不一致。',
    beforeData: { name_zh: '张杰', scholar_org_name_zh: '北京大学信息学院' },
    afterData: { name_zh: '张杰', scholar_org_name_zh: '北京大学计算机学院' },
    status: 'PENDING_REVIEW', submitterId: 'dev-zhang', submitterName: '张明', reviewerId: null,
    reviewerName: null, decisionNote: '', version: 1, submittedAt: '2026-08-22T09:18:00',
    reviewedAt: null, completedAt: null, updatedAt: '2026-08-22T09:18:00', sync: null,
    history: [{ id: 'history-001', action: 'SUBMIT', actorId: 'dev-zhang', actorName: '张明', note: '提交人工修正申请', createdAt: '2026-08-22T09:18:00' }],
  },
  {
    id: 'example-correction-002', targetType: 'organization', operation: 'update', targetId: 'org_44030001',
    title: '补充企业所在地区', reason: '机构基础信息缺少所在省市。',
    beforeData: { name_cn: '深圳智能计算研究院', province: '' },
    afterData: { name_cn: '深圳智能计算研究院', province: '广东省', city: '深圳市' },
    status: 'PENDING_REVIEW', submitterId: 'dev-li', submitterName: '李晓', reviewerId: null,
    reviewerName: null, decisionNote: '', version: 1, submittedAt: '2026-08-22T10:36:00',
    reviewedAt: null, completedAt: null, updatedAt: '2026-08-22T10:36:00', sync: null,
    history: [{ id: 'history-002', action: 'SUBMIT', actorId: 'dev-li', actorName: '李晓', note: '提交人工修正申请', createdAt: '2026-08-22T10:36:00' }],
  },
  {
    id: 'example-correction-003', targetType: 'relation', operation: 'create', targetId: 'person_aP4801002->org_44030001@0',
    title: '新增专家任职关系', reason: '公开履历显示专家已加入该研究机构。',
    beforeData: {}, afterData: { sourceId: 'person_aP4801002', targetId: 'org_44030001', edgeType: 'EMPLOYED_BY', properties: { role: '研究员' } },
    status: 'PENDING_REVIEW', submitterId: 'dev-wang', submitterName: '王晨', reviewerId: null,
    reviewerName: null, decisionNote: '', version: 1, submittedAt: '2026-08-22T14:05:00',
    reviewedAt: null, completedAt: null, updatedAt: '2026-08-22T14:05:00', sync: null,
    history: [{ id: 'history-003', action: 'SUBMIT', actorId: 'dev-wang', actorName: '王晨', note: '提交人工修正申请', createdAt: '2026-08-22T14:05:00' }],
  },
  {
    id: 'example-correction-004', targetType: 'expert', operation: 'update', targetId: 'person_2406B66w',
    title: '统一专家中文姓名', reason: '专家姓名存在同音异字。',
    beforeData: { name_zh: '陈志朋' }, afterData: { name_zh: '陈志鹏' },
    status: 'PENDING_SYNC', submitterId: 'dev-li', submitterName: '李晓', reviewerId: 'admin-01',
    reviewerName: '系统管理员', decisionNote: '来源可信，批准同步。', version: 1,
    submittedAt: '2026-08-21T15:20:00', reviewedAt: '2026-08-22T08:40:00', completedAt: null,
    updatedAt: '2026-08-22T08:40:00',
    sync: { id: 'sync-004', status: 'PENDING', mysqlStatus: 'SUCCEEDED', graphStatus: 'PENDING', attempts: 1, maxAttempts: 8, nextRetryAt: '2026-08-23T10:00:00', lastError: '' },
    history: [{ id: 'history-004', action: 'APPROVE', actorId: 'admin-01', actorName: '系统管理员', note: '批准并进入同步队列', createdAt: '2026-08-22T08:40:00' }],
  },
  {
    id: 'example-correction-005', targetType: 'relation', operation: 'update', targetId: 'person_99a94795->org_44030002@0',
    title: '修正专家任职时间', reason: '任职结束时间需要依据履历更新。',
    beforeData: { end_time: '2023-12' }, afterData: { end_time: '2024-12' },
    status: 'SYNC_FAILED', submitterId: 'dev-wang', submitterName: '王晨', reviewerId: 'admin-01',
    reviewerName: '系统管理员', decisionNote: '审核通过。', version: 1,
    submittedAt: '2026-08-20T11:12:00', reviewedAt: '2026-08-20T14:25:00', completedAt: null,
    updatedAt: '2026-08-22T16:08:00',
    sync: { id: 'sync-005', status: 'RETRYING', mysqlStatus: 'SUCCEEDED', graphStatus: 'FAILED', attempts: 3, maxAttempts: 8, nextRetryAt: '2026-08-23T10:10:00', lastError: '图库连接暂时不可用，等待自动重试。' },
    history: [{ id: 'history-005', action: 'SYNC_FAILED', actorId: 'system', actorName: '同步服务', note: '图库写入失败，已进入重试队列', createdAt: '2026-08-22T16:08:00' }],
  },
  {
    id: 'example-correction-006', targetType: 'organization', operation: 'update', targetId: 'org_44030003',
    title: '更新机构标准名称', reason: '机构已完成工商名称变更。',
    beforeData: { name_cn: '深圳前沿科技有限公司' }, afterData: { name_cn: '深圳前沿科技集团有限公司' },
    status: 'COMPLETED', submitterId: 'dev-zhang', submitterName: '张明', reviewerId: 'admin-01',
    reviewerName: '系统管理员', decisionNote: '材料完整，同意修正。', version: 1,
    submittedAt: '2026-08-18T09:00:00', reviewedAt: '2026-08-18T10:05:00', completedAt: '2026-08-18T10:06:00',
    updatedAt: '2026-08-18T10:06:00',
    sync: { id: 'sync-006', status: 'SUCCEEDED', mysqlStatus: 'SUCCEEDED', graphStatus: 'SUCCEEDED', attempts: 1, maxAttempts: 8, nextRetryAt: null, lastError: '' },
    history: [{ id: 'history-006', action: 'COMPLETE', actorId: 'system', actorName: '同步服务', note: 'MySQL 与图库同步完成', createdAt: '2026-08-18T10:06:00' }],
  },
  {
    id: 'example-correction-007', targetType: 'expert', operation: 'update', targetId: 'person_9A62597r',
    title: '补充专家职称', reason: '申报材料中缺少可核验来源。',
    beforeData: { title: '' }, afterData: { title: '副研究员' },
    status: 'REJECTED', submitterId: 'dev-li', submitterName: '李晓', reviewerId: 'admin-01',
    reviewerName: '系统管理员', decisionNote: '请补充正式任职证明后重新提交。', version: 1,
    submittedAt: '2026-08-17T13:15:00', reviewedAt: '2026-08-17T17:40:00', completedAt: null,
    updatedAt: '2026-08-17T17:40:00', sync: null,
    history: [{ id: 'history-007', action: 'REJECT', actorId: 'admin-01', actorName: '系统管理员', note: '请补充正式任职证明后重新提交', createdAt: '2026-08-17T17:40:00' }],
  },
]

const EXAMPLE_MEMBERS: PlatformMember[] = [
  { userId: 'dev-zhang', username: 'zhangming', nickname: '张明', email: 'zhangming@itic-sci.com', isAdmin: true, lastSeenAt: '2026-08-23T09:42:00' },
  { userId: 'dev-li', username: 'lixiao', nickname: '李晓', email: 'lixiao@itic-sci.com', isAdmin: true, lastSeenAt: '2026-08-23T09:18:00' },
  { userId: 'dev-wang', username: 'wangchen', nickname: '王晨', email: 'wangchen@itic-sci.com', isAdmin: false, lastSeenAt: '2026-08-22T18:06:00' },
  { userId: 'dev-chen', username: 'chenyu', nickname: '陈宇', email: 'chenyu@itic-sci.com', isAdmin: false, lastSeenAt: '2026-08-22T16:31:00' },
]

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function getExampleCorrections(): CorrectionRecord[] {
  return clone(EXAMPLE_CORRECTIONS)
}

export function getExampleMembers(): PlatformMember[] {
  return clone(EXAMPLE_MEMBERS)
}
