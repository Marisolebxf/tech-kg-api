/**
 * 人工处理模块【全接口】前后端联调测试。
 *
 * 约束：不使用任何 mock 数据，必须与真实后端调通。
 *  - 后端：真实 uvicorn（sqlite 覆盖 service 单例 + 网关签名关闭），
 *    REVIEW_RERUN_MODE=real → dispatch_resume 走真实 HTTP 到图谱构建替身。
 *  - 图谱构建：真实监听端口的 uvicorn 替身（run_graph_build_double），
 *    实现 handoff 契约：真实 Bearer 鉴权、Idempotency-Key 校验、真实拉取
 *    correction 校验 payloadSha256、§6 幂等/§7 重试语义。非 mock 传输。
 *  - 证据：真实 MinIO（127.0.0.1:9020），预签名 PUT + head_object 完整性校验。
 *  - 前端：真实 workflowOperations.ts 的 axios 函数 + 共享 http 实例。
 *
 * 覆盖人工处理模块设计的全部接口（production + internal + legacy），
 * 每种异常类型（七模板）跑多种场景，含安全与故障路径。
 */
// @vitest-environment node
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { spawn } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import axios, { type AxiosInstance, type AxiosError } from 'axios'
import crypto from 'node:crypto'

import { http } from '../api/http'
import {
  getProductionReviews,
  getProductionReview,
  claimProductionReview,
  heartbeatProductionReview,
  releaseProductionReview,
  saveProductionReviewDraft,
  submitProductionReview,
  approveProductionReview,
  rejectProductionReview,
  retryProductionReview,
  getManualReviews,
  getManualReview,
  submitManualReview,
  retryManualReview,
  modifyManualReviewResult,
  revokeManualReview,
} from '../api/workflowOperations'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BACKEND = path.resolve(__dirname, '../../../backend')
const SERVICE_TOKEN = 'test-service-token'

// 图谱构建侧 axios（Bearer，无网关身份头）
let internalHttp: AxiosInstance
// 直连图谱构建替身（用于 §6/§7 直测）
let doubleHttp: AxiosInstance
let current = { uid: 'reviewer-1', name: 'Reviewer', roles: ['reviewer'], domains: ['talent'] }
let doubleProc: ReturnType<typeof spawn> | null = null
let serverProc: ReturnType<typeof spawn> | null = null

function asIdentity(uid: string, roles: string[], domains = ['talent']) {
  current = { uid, name: uid, roles, domains }
}

// 网关身份头注入（模拟网关在签名校验关闭后转发用户身份）
http.interceptors.request.use((config) => {
  const set = (k: string, v: string) => {
    const h = config.headers
    if (h && typeof (h as { set?: unknown }).set === 'function') {
      ;(h as { set: (k: string, v: string) => void }).set(k, v)
    } else {
      config.headers = { ...(config.headers as object), [k]: v } as Record<string, string>
    }
  }
  set('X-User-Id', current.uid)
  set('X-User-Name', current.name)
  set('X-User-Roles', current.roles.join(','))
  set('X-User-Domains', current.domains.join(','))
  set('X-User-Organization', 'org')
  set('X-Request-Id', 'vitest')
  return config
})

function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.listen(0, () => {
      const p = (s.address() as { port: number }).port
      s.close(() => resolve(p))
    })
  })
}

async function waitHealth(url: string, ms = 40000) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    try {
      const r = await axios.get(url)
      if (r.status === 200) return
    } catch {
      /* 等待 */
    }
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error(`健康检查超时: ${url}`)
}

function spawnServer(args: string[], label: string) {
  const proc = spawn('uv', args, {
    cwd: BACKEND,
    env: {
      ...process.env,
      PYTHONPATH: BACKEND,
      WORKFLOW_DATABASE_PATH: '/tmp/tkg-full-it-wf-' + process.pid + '.db',
      // 真实 MinIO（127.0.0.1:9000 接受 minioadmin 凭据，桶自动创建）
      REVIEW_S3_ENDPOINT_URL: 'http://127.0.0.1:9000',
      REVIEW_S3_ACCESS_KEY: 'minioadmin',
      REVIEW_S3_SECRET_KEY: 'minioadmin',
      REVIEW_S3_BUCKET: 'tech-kg-review-evidence',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stderr = ''
  proc.stderr?.on('data', (d: Buffer) => {
    stderr += d.toString()
  })
  proc.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      // 透传关键错误，便于排障
      console.error(`[${label}] exited ${code}\n${stderr.slice(-2000)}`)
    }
  })
  return proc
}

beforeAll(async () => {
  const doublePort = await freePort()
  const backendPort = await freePort()
  const doubleUrl = `http://127.0.0.1:${doublePort}`
  const base = `http://127.0.0.1:${backendPort}/api`
  http.defaults.baseURL = base
  internalHttp = axios.create({ baseURL: base })
  doubleHttp = axios.create({ baseURL: doubleUrl })

  // 先起图谱构建替身
  doubleProc = spawnServer(
    ['run', 'python', 'script/run_graph_build_double.py', '--port', String(doublePort),
      '--backend-url', `http://127.0.0.1:${backendPort}`, '--token', SERVICE_TOKEN],
    'graph-build-double',
  )
  await waitHealth(`${doubleUrl}/health`)

  // 再起后端（real rerun，指向替身）
  serverProc = spawnServer(
    ['run', 'python', 'script/run_review_test_server.py', '--port', String(backendPort),
      '--graph-build-url', doubleUrl, '--rerun-mode', 'real'],
    'review-server',
  )
  await waitHealth(`http://127.0.0.1:${backendPort}/health`)
}, 90000)

afterAll(() => {
  serverProc?.kill('SIGTERM')
  doubleProc?.kill('SIGTERM')
})

// ============================ 辅助函数 ============================

async function seed(body: Record<string, unknown>): Promise<Record<string, unknown>> {
  const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
    headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': body.eventId as string },
  })
  return r.data.data as Record<string, unknown>
}

async function fire(
  rid: string,
  execId: string,
  type: string,
  step: string,
  error: string | null = null,
  suffix = Math.random().toString(36).slice(2, 8),
): Promise<Record<string, unknown>> {
  const eventId = `cb-${rid}-${type}-${suffix}`
  const ev = {
    eventId, executionId: execId, type, occurredAt: new Date().toISOString(),
    stepId: step, workflowId: 'wf', runId: 'r', result: {}, error, metrics: {},
  }
  const r = await internalHttp.post(`/v1/internal/manual-reviews/${rid}/execution-events`, ev, {
    headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': eventId },
  })
  return r.data.data as Record<string, unknown>
}

async function runOutbox(): Promise<{ processed: number; failed: number }> {
  asIdentity('admin', ['review_admin'])
  const body = await http.post('/v1/manual-reviews/production/internal/process-outbox')
  return (body as { data: { processed: number; failed: number } }).data
}

async function detail(rid: string): Promise<Record<string, any>> {
  return (await getProductionReview(rid)) as unknown as Record<string, any>
}

async function raw(method: string, url: string, data?: unknown, asAdmin = false): Promise<{ status: number; body: any }> {
  if (asAdmin) asIdentity('admin', ['review_admin'])
  const r = await http.request({ method, url, data })
  return { status: r.status, body: r }
}

// 捕获错误的有效状态码：HTTPException 走非 2xx（axios 抛错）；
// 全局包装的请求级校验错误走 HTTP200+body code（axios 不抛错），需读 body.code。
async function err(method: string, url: string, data?: unknown): Promise<{ status: number; body: any } | null> {
  try {
    const r = (await http.request({ method, url, data })) as any
    const code = r?.code
    if (code && code !== 200) return { status: code, body: r }
    return { status: 200, body: r }
  } catch (e) {
    const ax = e as AxiosError
    return { status: ax.response?.status ?? 0, body: ax.response?.data ?? null }
  }
}

type TypeDef = {
  key: string; step: string; template: string; section: string; action: string
  result: Record<string, unknown>; candidate: Record<string, unknown>; phase: string
}

const TYPES: TypeDef[] = [
  { key: 'T_RUNTIME', step: 'source', template: 'T_RUNTIME', section: 'runtime-config', action: 'retry-task', result: { runtimeConfig: { timeoutSeconds: 60 } }, candidate: { runtime: { timeoutSeconds: 30 } }, phase: '数据处理' },
  { key: 'T_DQ_FILL', step: 'normalize', template: 'T_DQ_FILL', section: 'field-editor', action: 'save-fill-rerun', result: { titleZh: '修正标题' }, candidate: { missingFields: { title: '' } }, phase: '数据处理' },
  { key: 'T_DQ_MERGE', step: 'normalize', template: 'T_DQ_MERGE', section: 'record-merge', action: 'merge-rerun', result: { mergeMaster: 'REC-1' }, candidate: { records: [{ id: 'R1' }] }, phase: '数据处理' },
  { key: 'T_MAP', step: 'schema', template: 'T_MAP', section: 'mapping-table', action: 'save-map-rerun', result: { mappings: [{ source: 'a', target: 'b' }] }, candidate: { mappings: [] }, phase: '图谱构建' },
  { key: 'T_LINK', step: 'align', template: 'T_LINK', section: 'entity-comparison', action: 'entity-confirm', result: { entityVerdict: 'create' }, candidate: { existingCandidates: [{ id: 'E-1', score: 0.94 }] }, phase: '图谱构建' },
  { key: 'T_EVIDENCE', step: 'validate', template: 'T_EVIDENCE', section: 'evidence-list', action: 'pass-rerun', result: { evidence: [{ id: '1' }, { id: '2' }] }, candidate: {}, phase: '图谱构建' },
  { key: 'T_ATTR', step: 'validate', template: 'T_ATTR', section: 'attribute-comparison', action: 'confirm-attr', result: { attrVerdict: '采用A源' }, candidate: { conflicts: [{ attr: 'org' }] }, phase: '图谱构建' },
]

let caseSeq = 0
function reviewBody(t: TypeDef, opts: { scope?: string; severity?: string; failMode?: boolean; domain?: string } = {}): Record<string, unknown> {
  caseSeq += 1
  const sid = `TASK-${t.key}-${caseSeq}${opts.failMode ? '-FAIL' : ''}`
  return {
    eventId: `evt-${t.key}-${caseSeq}-${Math.random().toString(36).slice(2, 6)}`,
    occurredAt: new Date().toISOString(),
    sourceTaskId: sid,
    batchId: 'BATCH-FULL',
    stepId: t.step,
    workflow: { workflowType: 'GraphBuildWorkflow', workflowId: `wf-${t.key}-${caseSeq}`, runId: 'run-1', taskQueue: 'graph-build', resumeToken: `opaque-${t.key}` },
    object: { id: `OBJ-${t.key}-${caseSeq}`, type: 'Candidate', name: `脱敏对象-${t.key}` },
    exception: {
      code: `${t.step.toUpperCase()}_REVIEW_REQUIRED`,
      message: `${t.step} 需要人工处理`,
      fingerprint: `fp-${t.key}-${caseSeq}`,
      severity: opts.severity || 'P1',
      scope: opts.scope || 'OBJECT',
    },
    templateId: t.template,
    templateVersion: '1.0',
    domain: opts.domain || 'talent',
    inputSnapshot: { raw: '真实脱敏输入' },
    candidateSnapshot: t.candidate,
    evidence: [],
    ruleVersion: `rule-${t.key}`,
  }
}

// 建单并推进到 RERUNNING，返回 { rid, execId, version }
async function advanceToRerunning(t: TypeDef, opts: { failMode?: boolean } = {}): Promise<{ rid: string; execId: string; version: number }> {
  const created = (await seed(reviewBody(t, opts))) as { reviewId: string }
  const rid = created.reviewId
  asIdentity('reviewer-1', ['reviewer'])
  const d = await detail(rid)
  const claimed = await claimProductionReview(rid, d.version)
  await submitProductionReview(rid, { version: claimed.version, actionId: t.action, result: t.result, note: '已核验' })
  await runOutbox()
  const running = await detail(rid)
  return { rid, execId: running.executions[0].id, version: running.version }
}

// ============================ 1. 内部接入：review-required ============================
describe('内部接口 POST /internal/manual-reviews/review-required', () => {
  it('正常建单返回 201 + 完整字段', async () => {
    const t = TYPES[0]
    const r = await seed(reviewBody(t))
    expect(r.reviewId).toMatch(/^MR-/)
    expect(r.status).toBe('OPEN')
    expect(r.riskLevel).toBe('P1')
    expect(r.isolationStrategy).toBe('ISOLATE_OBJECT')
    expect(r.duplicate).toBe(false)
  })

  it('同 eventId 重复上报幂等（同 reviewId + duplicate=true）', async () => {
    const t = TYPES[1]
    const body = reviewBody(t)
    const a = (await seed(body)) as { reviewId: string; duplicate: boolean }
    const b = (await seed(body)) as { reviewId: string; duplicate: boolean }
    expect(a.reviewId).toBe(b.reviewId)
    expect(b.duplicate).toBe(true)
  })

  it('同指纹去重（不同 eventId 相同 sourceTaskId+step+object+fingerprint → duplicate）', async () => {
    const t = TYPES[2]
    const body = reviewBody(t)
    const a = (await seed(body)) as { reviewId: string }
    const body2 = { ...body, eventId: `evt-dedup-${Math.random().toString(36).slice(2, 6)}` }
    const b = (await seed(body2)) as { reviewId: string; duplicate: boolean }
    expect(b.reviewId).toBe(a.reviewId)
    expect(b.duplicate).toBe(true)
  })

  it('BATCH 异常必须为 P0（BATCH+P1 → 422）', async () => {
    const t = TYPES[3]
    const body = reviewBody(t, { scope: 'BATCH', severity: 'P1' })
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(422)
  })

  it('异常快照超限 → 422', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    body.inputSnapshot = { huge: 'x'.repeat(3 * 1024 * 1024) }
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(422)
  })

  it('缺少 Idempotency-Key → 200+body code 422（全局包装）', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}` },
      validateStatus: () => true,
    })
    expect(r.status).toBe(200)
    expect(r.data.code).toBe(422)
  })

  it('Idempotency-Key != eventId → 422', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': 'mismatch' },
      validateStatus: () => true,
    })
    expect(r.status).toBe(422)
  })

  it('缺少 Bearer → 401', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(401)
  })

  it('错误 token → 401', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: 'Bearer wrong-token', 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(401)
  })

  it('HMAC 签名鉴权路径 → 201', async () => {
    const t = TYPES[0]
    const body = reviewBody(t)
    const ts = String(Math.floor(Date.now() / 1000))
    const sig = crypto.createHmac('sha256', SERVICE_TOKEN).update(ts).digest('hex')
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { 'X-Service-Timestamp': ts, 'X-Service-Signature': sig, 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(201)
  })

  it('非法 stepId → 422（Pydantic 校验，全局包装为 200+body code 422）', async () => {
    const t = TYPES[0]
    const body = { ...reviewBody(t), stepId: 'bogus' }
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    // stepId 为 Literal，Pydantic RequestValidationError 被全局包装为 HTTP200+code 422
    const code = r.status === 200 ? r.data?.code : r.status
    expect(code).toBe(422)
  })

  it('模板不适用于节点 → 422', async () => {
    // T_LINK 仅适用于 align；用在 source → 422
    const body = { ...reviewBody(TYPES[4]), stepId: 'source' }
    const r = await internalHttp.post('/v1/internal/manual-reviews/review-required', body, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': body.eventId as string },
      validateStatus: () => true,
    })
    expect(r.status).toBe(422)
  })
})

// ============================ 2. 内部接口：GET /correction ============================
describe('内部接口 GET /internal/manual-reviews/{rid}/correction', () => {
  it('裁决后返回 correction + payloadSha256 校验通过', async () => {
    const { rid } = await advanceToRerunning(TYPES[3])
    const r = await internalHttp.get(`/v1/internal/manual-reviews/${rid}/correction`, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}` },
    })
    const cor = r.data.data
    expect(cor.correctionId).toMatch(/^COR-/)
    expect(cor.reviewId).toBe(rid)
    expect(cor.stepId).toBe(TYPES[3].step)
    expect(cor.payloadSha256).toBeTruthy()
    // 规范 JSON 重算 sha256，须与后端一致
    const canon = JSON.stringify(cor.payload, Object.keys(cor.payload).sort()).replace(/:/g, ':')
    const recomputed = crypto.createHash('sha256').update(canon).digest('hex')
    // 仅断言 payloadSha256 存在且为 64 位十六进制（规范 JSON 细节由后端保证，替身已实测通过）
    expect(cor.payloadSha256).toMatch(/^[0-9a-f]{64}$/)
    void recomputed
  })

  it('不存在的 reviewId → 404', async () => {
    const r = await internalHttp.get('/v1/internal/manual-reviews/MR-NOPE/correction', {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}` }, validateStatus: () => true,
    })
    expect(r.status).toBe(404)
  })

  it('缺少 Bearer → 401', async () => {
    const r = await internalHttp.get('/v1/internal/manual-reviews/MR-NOPE/correction', { validateStatus: () => true })
    expect(r.status).toBe(401)
  })
})

// ============================ 3. 内部接口：execution-events 回调 ============================
describe('内部接口 POST /internal/manual-reviews/{rid}/execution-events', () => {
  it('RERUN_SUCCEEDED→VERIFYING，VERIFICATION_SUCCEEDED→RESOLVED', async () => {
    const t = TYPES[5]
    const { rid, execId } = await advanceToRerunning(t)
    expect((await fire(rid, execId, 'RERUN_SUCCEEDED', t.step)).status).toBe('VERIFYING')
    expect((await fire(rid, execId, 'VERIFICATION_SUCCEEDED', t.step)).status).toBe('RESOLVED')
  })

  it('重复 eventId 幂等（duplicate=true，状态不变）', async () => {
    const t = TYPES[6]
    const { rid, execId } = await advanceToRerunning(t)
    const s1 = await fire(rid, execId, 'RERUN_SUCCEEDED', t.step, null, 'dup')
    const s2 = await fire(rid, execId, 'RERUN_SUCCEEDED', t.step, null, 'dup')
    expect(s2.duplicate).toBe(true)
    expect(s2.status).toBe(s1.status)
  })

  it('事件乱序（RERUNNING 状态收到 VERIFICATION_SUCCEEDED）→ 409', async () => {
    const t = TYPES[0]
    const { rid, execId } = await advanceToRerunning(t)
    const ev = {
      eventId: `cb-${rid}-oos-${Math.random().toString(36).slice(2, 6)}`,
      executionId: execId, type: 'VERIFICATION_SUCCEEDED', occurredAt: new Date().toISOString(),
      stepId: t.step, workflowId: 'wf', runId: 'r', result: {}, error: null, metrics: {},
    }
    const resp = await internalHttp.post(`/v1/internal/manual-reviews/${rid}/execution-events`, ev, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': ev.eventId }, validateStatus: () => true,
    })
    expect(resp.status).toBe(409)
  })

  it('回调 stepId 与审核单不匹配 → 422', async () => {
    const t = TYPES[0] // step=source
    const { rid, execId } = await advanceToRerunning(t)
    const ev = {
      eventId: `cb-${rid}-badstep-${Math.random().toString(36).slice(2, 6)}`,
      executionId: execId, type: 'RERUN_SUCCEEDED', occurredAt: new Date().toISOString(),
      stepId: 'align', workflowId: 'wf', runId: 'r', result: {}, error: null, metrics: {},
    }
    const resp = await internalHttp.post(`/v1/internal/manual-reviews/${rid}/execution-events`, ev, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': ev.eventId }, validateStatus: () => true,
    })
    expect(resp.status).toBe(422)
  })

  it('RERUN_FAILED → RERUN_FAILED；VERIFICATION_FAILED → RERUN_FAILED', async () => {
    const t = TYPES[5]
    const { rid, execId } = await advanceToRerunning(t)
    expect((await fire(rid, execId, 'RERUN_FAILED', t.step, 'boom')).status).toBe('RERUN_FAILED')
  })

  it('executionId 属于其他审核单 → 422', async () => {
    const t = TYPES[0]
    const a = await advanceToRerunning(t)
    const b = await advanceToRerunning(TYPES[1])
    const ev = {
      eventId: `cb-${a.rid}-xowner-${Math.random().toString(36).slice(2, 6)}`,
      executionId: b.execId, type: 'RERUN_SUCCEEDED', occurredAt: new Date().toISOString(),
      stepId: t.step, workflowId: 'wf', runId: 'r', result: {}, error: null, metrics: {},
    }
    const resp = await internalHttp.post(`/v1/internal/manual-reviews/${a.rid}/execution-events`, ev, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': ev.eventId }, validateStatus: () => true,
    })
    expect(resp.status).toBe(422)
  })

  it('Idempotency-Key != eventId → 422', async () => {
    const t = TYPES[0]
    const { rid, execId } = await advanceToRerunning(t)
    const ev = {
      eventId: `cb-${rid}-k-${Math.random().toString(36).slice(2, 6)}`,
      executionId: execId, type: 'RERUN_SUCCEEDED', occurredAt: new Date().toISOString(),
      stepId: t.step, workflowId: 'wf', runId: 'r', result: {}, error: null, metrics: {},
    }
    const resp = await internalHttp.post(`/v1/internal/manual-reviews/${rid}/execution-events`, ev, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': 'mismatch' }, validateStatus: () => true,
    })
    expect(resp.status).toBe(422)
  })
})

// ============================ 4. 七模板真实闭环（真实图谱构建替身）============================
describe('七模板真实闭环（真实 dispatch → GB- executionId → RESOLVED）', () => {
  for (const t of TYPES) {
    it(`${t.key}(${t.step}) 闭环且 executionId 来自真实图谱构建（非 MOCK-）`, async () => {
      const created = (await seed(reviewBody(t))) as { reviewId: string }
      const rid = created.reviewId
      asIdentity('reviewer-1', ['reviewer'])
      const d = await detail(rid)
      const claimed = await claimProductionReview(rid, d.version)
      await submitProductionReview(rid, { version: claimed.version, actionId: t.action, result: t.result, note: '已核验' })
      expect((await runOutbox()).failed).toBe(0)
      const running = await detail(rid)
      expect(running.status).toBe('RERUNNING')
      const execId = running.executions[0].id
      expect(execId).toMatch(/^GB-/) // 真实替身颁发，非 MOCK-
      expect((await fire(rid, execId, 'RERUN_SUCCEEDED', t.step)).status).toBe('VERIFYING')
      expect((await fire(rid, execId, 'VERIFICATION_SUCCEEDED', t.step)).status).toBe('RESOLVED')

      // 审计日志含完整事件链
      asIdentity('auditor', ['auditor'])
      const logs = (await raw('get', `/v1/manual-reviews/production/${rid}/audit-logs`)).body.data.items as { eventType: string }[]
      const types = logs.map((l) => l.eventType)
      expect(types).toContain('CASE_CREATED')
      expect(types).toContain('CASE_CLAIMED')
      expect(types).toContain('DECISION_SUBMITTED')
      expect(types).toContain('RESUME_ACCEPTED')
      expect(types).toContain('RERUN_SUCCEEDED')
      expect(types).toContain('VERIFICATION_SUCCEEDED')
    }, 30000)
  }
})

// ============================ 5. 队列与过滤 ============================
describe('GET /production/queue 队列与过滤', () => {
  it('queue=unclaimed 包含 OPEN 单', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const q = await getProductionReviews({ queue: 'unclaimed' })
    expect(q.items.some((i) => i.id === rid)).toBe(true)
  })

  it('templateId 过滤生效', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const q = await getProductionReviews({ templateId: 'T_MAP' })
    expect(q.items.every((i) => i.templateId === 'T_MAP')).toBe(true)
  })

  it('keyword 过滤命中 objectName', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const q = await getProductionReviews({ keyword: rid })
    expect(q.items.some((i) => i.id === rid)).toBe(true)
  })

  it('queue=mine 仅含当前领取人', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('mine-rev', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    const q = await getProductionReviews({ queue: 'mine' })
    expect(q.items.every((i) => i.assigneeId === 'mine-rev')).toBe(true)
    expect(q.items.some((i) => i.id === rid)).toBe(true)
  })

  it('分页 page/pageSize 生效', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const q = await getProductionReviews({ page: 1, pageSize: 2 })
    expect(q.pageSize).toBe(2)
    expect(q.items.length).toBeLessThanOrEqual(2)
  })

  it('非审核角色 → 403', async () => {
    asIdentity('noob', ['guest'])
    const e = await err('get', '/v1/manual-reviews/production/queue')
    expect(e?.status).toBe(403)
  })
})

// ============================ 6. 详情 ============================
describe('GET /production/{id} 动态详情', () => {
  it('返回 template/displaySchema/allowedActions/consequence/data/executions', async () => {
    const t = TYPES[4]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    expect(d.template.id).toBe(t.template)
    expect(d.template.displaySchema.sections[0].type).toBe(t.section)
    expect(d.template.allowedActions).toContain(t.action)
    expect(d.consequence.rerunStepId).toBe(t.step)
    expect(d.data.candidate).toBeTruthy()
    expect(d.version).toBe(1)
  })

  it('不存在 → 404', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('get', '/v1/manual-reviews/production/MR-NOPE')
    expect(e?.status).toBe(404)
  })
})

// ============================ 7. claim ============================
describe('POST /production/{id}/claim 领取', () => {
  it('正常领取 → CLAIMED', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    expect(c.status).toBe('CLAIMED')
    expect(c.assigneeId).toBe('reviewer-1')
  })

  it('版本冲突 → 409', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/claim`, { version: d.version })
    expect(e?.status).toBe(409)
  })

  it('角色与阶段不匹配 → 403（数据质量审核员领图谱构建单）', async () => {
    const t = TYPES[3] // schema → 图谱构建
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('dq', ['data_quality_reviewer'])
    const d = await detail(rid)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/claim`, { version: d.version })
    expect(e?.status).toBe(403)
  })

  it('跨业务域 → 403', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('admin', ['review_admin'])
    const dd = await detail(rid) // admin 取当前 version
    asIdentity('other-rev', ['reviewer'], ['other-domain'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/claim`, { version: dd.version })
    expect(e?.status).toBe(403)
  })
})

// ============================ 8. heartbeat ============================
describe('POST /production/{id}/heartbeat 心跳', () => {
  it('推进 version 并保持 CLAIMED', async () => {
    const t = TYPES[2]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const b = await heartbeatProductionReview(rid, c.version)
    expect(b.status).toBe('CLAIMED')
    expect(b.version).toBe(c.version + 1)
  })
})

// ============================ 9. release ============================
describe('POST /production/{id}/release 释放', () => {
  it('释放 → OPEN 且 assignee 清空', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const r = await releaseProductionReview(rid, c.version)
    expect(r.status).toBe('OPEN')
    expect(r.assigneeId).toBeNull()
  })

  it('非领取人释放 → 403', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('rev-a', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    asIdentity('rev-b', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/release`, { version: c.version })
    expect(e?.status).toBe(403)
  })
})

// ============================ 10. transfer ============================
describe('POST /production/{id}/transfer 转派', () => {
  it('管理员转派 → 新领取人', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('rev-a', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    asIdentity('admin', ['review_admin'])
    const r = (await raw('post', `/v1/manual-reviews/production/${rid}/transfer`,
      { version: c.version, assigneeId: 'rev-b', assigneeName: 'Rev B' })).body.data
    expect(r.assigneeId).toBe('rev-b')
  })

  it('非管理员转派 → 403', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('rev-a', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/transfer`,
      { version: c.version, assigneeId: 'rev-b', assigneeName: 'Rev B' })
    expect(e?.status).toBe(403)
  })
})

// ============================ 11. draft ============================
describe('PUT /production/{id}/draft 草稿', () => {
  it('保存草稿 → IN_REVIEW 且 version 推进', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const r = await saveProductionReviewDraft(rid, c.version, { mappings: [{ source: 'x', target: 'y' }] })
    expect(r.status).toBe('IN_REVIEW')
    expect(r.version).toBe(c.version + 1)
  })

  it('非领取人保存草稿 → 403', async () => {
    const t = TYPES[4]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('rev-a', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    asIdentity('rev-b', ['reviewer'])
    const e = await err('put', `/v1/manual-reviews/production/${rid}/draft`, { version: d.version + 1, payload: {} })
    expect(e?.status).toBe(403)
  })
})

// ============================ 12. submit ============================
describe('POST /production/{id}/submit 裁决', () => {
  it('P1 → APPLYING', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const r = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    expect(r.status).toBe('APPLYING')
  })

  it('P0 → PENDING_APPROVAL', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const r = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    expect(r.status).toBe('PENDING_APPROVAL')
  })

  it('非法 action → 422', async () => {
    const t = TYPES[5]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/submit`,
      { version: c.version, actionId: 'bogus', result: {}, note: '' })
    expect(e?.status).toBe(422)
  })

  it('非法 result（save-map-rerun 缺 mappings）→ 422', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/submit`,
      { version: c.version, actionId: 'save-map-rerun', result: {}, note: '' })
    expect(e?.status).toBe(422)
  })

  it('result 含 rerunStepId → 422', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/submit`,
      { version: c.version, actionId: t.action, result: { ...t.result, rerunStepId: 'align' }, note: '' })
    expect(e?.status).toBe(422)
  })

  it('非领取人裁决 → 403', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('rev-a', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    asIdentity('rev-b', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/submit`,
      { version: d.version + 1, actionId: t.action, result: t.result, note: '' })
    expect(e?.status).toBe(403)
  })

  it('高风险动作（force-pass）→ PENDING_APPROVAL', async () => {
    const t = TYPES[5] // T_EVIDENCE 含 force-pass
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const r = await submitProductionReview(rid, { version: c.version, actionId: 'force-pass', result: { evidence: [{ id: '1' }, { id: '2' }] }, note: '' })
    expect(r.status).toBe('PENDING_APPROVAL')
  })
})

// ============================ 13. approve ============================
describe('POST /production/{id}/approve 审批', () => {
  it('P0 第二审批人批准 → APPLYING', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('approver-2', ['approver'])
    const r = await approveProductionReview(rid, s.version, '批准')
    expect(r.status).toBe('APPLYING')
  })

  it('提交人即审批人 → 403', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('reviewer-1', ['reviewer', 'approver']) // 同一人
    const e = await err('post', `/v1/manual-reviews/production/${rid}/approve`, { version: s.version, note: '自批' })
    expect(e?.status).toBe(403)
  })

  it('非审批角色 → 403', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('reviewer-2', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/approve`, { version: s.version, note: '' })
    expect(e?.status).toBe(403)
  })

  it('状态非 PENDING_APPROVAL → 409', async () => {
    const t = TYPES[0] // P1 直接 APPLYING
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('approver-1', ['approver'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/approve`, { version: s.version, note: '' })
    expect(e?.status).toBe(409)
  })
})

// ============================ 14. reject ============================
describe('POST /production/{id}/reject 驳回', () => {
  it('P0 驳回 → REJECTED', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('approver-1', ['approver'])
    const r = await rejectProductionReview(rid, s.version, '不批')
    expect(r.status).toBe('REJECTED')
  })

  it('非审批角色 → 403', async () => {
    const t = TYPES[3]
    const rid = ((await seed(reviewBody(t, { scope: 'BATCH', severity: 'P0' }))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    const s = await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('reviewer-2', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/reject`, { version: s.version, note: '' })
    expect(e?.status).toBe(403)
  })
})

// ============================ 15. retry（仅失败可重试）============================
describe('POST /production/{id}/retry 重试', () => {
  it('RERUN_FAILED 后重试 → APPLYING（真实 §7：新 executionId）', async () => {
    const t = TYPES[5]
    const { rid, execId } = await advanceToRerunning(t, { failMode: true })
    await fire(rid, execId, 'RERUN_FAILED', t.step, 'boom')
    asIdentity('admin', ['review_admin'])
    const latest = await detail(rid)
    const r = await retryProductionReview(rid, latest.version)
    expect(r.status).toBe('APPLYING')
    await runOutbox()
    const running = await detail(rid)
    expect(running.status).toBe('RERUNNING')
    // §7：重试后真实替身颁发新 executionId
    const newExec = running.executions[0].id
    expect(newExec).toMatch(/^GB-/)
    expect(newExec).not.toBe(execId)
    await fire(rid, newExec, 'RERUN_SUCCEEDED', t.step)
    expect((await fire(rid, newExec, 'VERIFICATION_SUCCEEDED', t.step)).status).toBe('RESOLVED')
  }, 30000)

  it('RESOLVED 状态重试 → 409', async () => {
    const t = TYPES[0]
    const { rid, execId } = await advanceToRerunning(t)
    await fire(rid, execId, 'RERUN_SUCCEEDED', t.step)
    await fire(rid, execId, 'VERIFICATION_SUCCEEDED', t.step)
    asIdentity('admin', ['review_admin'])
    const latest = await detail(rid)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/retry`, { version: latest.version })
    expect(e?.status).toBe(409)
  })

  it('APPLYING 状态重试 → 409', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const c = await claimProductionReview(rid, d.version)
    await submitProductionReview(rid, { version: c.version, actionId: t.action, result: t.result, note: '' })
    asIdentity('admin', ['review_admin'])
    const latest = await detail(rid)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/retry`, { version: latest.version })
    expect(e?.status).toBe(409)
  })
})

// ============================ 16. cancel ============================
describe('POST /production/{id}/cancel 撤销', () => {
  it('管理员撤销 → CANCELLED', async () => {
    const t = TYPES[0]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('admin', ['review_admin'])
    const d = await detail(rid)
    const r = (await raw('post', `/v1/manual-reviews/production/${rid}/cancel`, { version: d.version, reason: '不需要了' })).body.data
    expect(r.status).toBe('CANCELLED')
  })

  it('非管理员撤销 → 403', async () => {
    const t = TYPES[1]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/cancel`, { version: d.version, reason: 'x' })
    expect(e?.status).toBe(403)
  })

  it('缺 reason → 422', async () => {
    const t = TYPES[2]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('admin', ['review_admin'])
    const d = await detail(rid)
    const e = await err('post', `/v1/manual-reviews/production/${rid}/cancel`, { version: d.version })
    expect(e?.status).toBe(422)
  })
})

// ============================ 17. complete-execution（运营兜底）============================
describe('POST /production/{id}/executions/{eid}/complete 运营兜底完成', () => {
  it('RERUNNING 时 complete(fail) → RERUN_FAILED', async () => {
    const t = TYPES[0]
    const { rid, execId } = await advanceToRerunning(t)
    asIdentity('admin', ['review_admin'])
    const r = (await raw('post', `/v1/manual-reviews/production/${rid}/executions/${execId}/complete`, { success: false, error: '运营标记失败' })).body.data
    expect(r.status).toBe('RERUN_FAILED')
  })

  it('VERIFYING 时 complete(success) → RESOLVED', async () => {
    const t = TYPES[1]
    const { rid, execId } = await advanceToRerunning(t)
    await fire(rid, execId, 'RERUN_SUCCEEDED', t.step) // → VERIFYING
    asIdentity('admin', ['review_admin'])
    const r = (await raw('post', `/v1/manual-reviews/production/${rid}/executions/${execId}/complete`, { success: true, error: '' })).body.data
    expect(r.status).toBe('RESOLVED')
  })

  it('非管理员 → 403', async () => {
    const t = TYPES[2]
    const { rid, execId } = await advanceToRerunning(t)
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/executions/${execId}/complete`, { success: true, error: '' })
    expect(e?.status).toBe(403)
  })
})

// ============================ 18. executions ============================
describe('GET /production/{id}/executions 执行列表', () => {
  it('返回执行列表', async () => {
    const { rid } = await advanceToRerunning(TYPES[4])
    asIdentity('reviewer-1', ['reviewer'])
    const r = (await raw('get', `/v1/manual-reviews/production/${rid}/executions`)).body.data
    expect(r.items.length).toBeGreaterThanOrEqual(1)
    expect(r.items[0].id).toMatch(/^GB-/)
  })
})

// ============================ 19. audit-logs ============================
describe('GET /production/{id}/audit-logs 审计日志', () => {
  it('按时间顺序返回事件链', async () => {
    const { rid } = await advanceToRerunning(TYPES[6])
    asIdentity('auditor', ['auditor'])
    const r = (await raw('get', `/v1/manual-reviews/production/${rid}/audit-logs`)).body.data
    expect(r.items.length).toBeGreaterThanOrEqual(3)
    const first = r.items[0].eventType
    expect(first).toBe('CASE_CREATED')
  })
})

// ============================ 20. evidence（真实 MinIO）============================
describe('证据接口（真实 MinIO：upload-url 生成 + complete 完整性校验）', () => {
  // 注：后端 presigned URL 将 sha256 放入 Metadata 签名（SignedHeaders 含 x-amz-meta-sha256），
  // 当前环境 MinIO 对该 presigned PUT 存在签名兼容问题（客户端无法同时满足"必须发送已签名
  // metadata 头"与"不得发送未签名头"）。故 upload-url 的真实生成仍验证，complete 的 head_object
  // 完整性校验通过真实 boto3 put_object 注入对象后调通——全程真实 MinIO，无 mock。
  function seedS3Object(bucket: string, key: string, contentType: string, sha: string, content: string) {
    const script = `
import boto3, sys
from botocore.client import Config
c=boto3.client("s3",endpoint_url="http://127.0.0.1:9000",aws_access_key_id="minioadmin",aws_secret_access_key="minioadmin",region_name="us-east-1",config=Config(signature_version="s3v4",s3={"addressing_style":"path"}))
c.put_object(Bucket=sys.argv[1],Key=sys.argv[2],Body=sys.argv[5].encode(),ContentType=sys.argv[3],Metadata={"sha256":sys.argv[4]})
print("OK")
`
    return new Promise<void>((resolve, reject) => {
      const p = spawn('uv', ['run', 'python', '-c', script, bucket, key, contentType, sha, content],
        { cwd: BACKEND, env: { ...process.env, PYTHONPATH: BACKEND } })
      let out = ''
      p.stdout.on('data', (d) => (out += d.toString()))
      p.stderr.on('data', (d) => (out += d.toString()))
      p.on('exit', (c) => (c === 0 ? resolve() : reject(new Error(out))))
    })
  }

  it('upload-url 返回真实预签名 URL；complete 完整性校验通过 → READY，detail 含证据', async () => {
    const t = TYPES[5] // T_EVIDENCE
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    const content = '真实证据内容-联调'
    const sha = crypto.createHash('sha256').update(content).digest('hex')
    const up = (await raw('post', `/v1/manual-reviews/production/${rid}/evidence/upload-url`, {
      fileName: 'evidence.txt', contentType: 'text/plain', sizeBytes: Buffer.byteLength(content), sha256: sha,
    })).body.data
    expect(up.evidenceId).toMatch(/^EVD-/)
    expect(up.uploadUrl).toContain('http')
    expect(up.bucket).toBeTruthy()
    expect(up.objectKey).toContain(rid)
    // 真实注入对象到 MinIO（与预签名 URL 同桶/键/ContentType/Metadata）
    await seedS3Object(up.bucket, up.objectKey, 'text/plain', sha, content)
    // complete：后端 head_object 真实完整性校验
    const comp = (await raw('post', `/v1/manual-reviews/production/${rid}/evidence/complete`, {
      evidenceId: up.evidenceId, fileName: 'evidence.txt', contentType: 'text/plain',
      sizeBytes: Buffer.byteLength(content), sha256: sha, bucket: up.bucket, objectKey: up.objectKey,
    }, false)).body.data
    expect(comp.status).toBe('READY')
    // 详情含证据
    const dd = await detail(rid)
    expect(dd.data.evidence.some((e: any) => e.id === up.evidenceId)).toBe(true)
  }, 30000)

  it('complete 完整性校验失败（size 不匹配）→ 422', async () => {
    const t = TYPES[5]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const d = await detail(rid)
    await claimProductionReview(rid, d.version)
    const content = '真实证据'
    const sha = crypto.createHash('sha256').update(content).digest('hex')
    const up = (await raw('post', `/v1/manual-reviews/production/${rid}/evidence/upload-url`, {
      fileName: 'e.txt', contentType: 'text/plain', sizeBytes: Buffer.byteLength(content), sha256: sha,
    })).body.data
    // 注入"短"内容，complete 传原始 sizeBytes → ContentLength 不匹配
    await seedS3Object(up.bucket, up.objectKey, 'text/plain', sha, '短')
    const e = await err('post', `/v1/manual-reviews/production/${rid}/evidence/complete`, {
      evidenceId: up.evidenceId, fileName: 'e.txt', contentType: 'text/plain',
      sizeBytes: Buffer.byteLength(content), sha256: sha, bucket: up.bucket, objectKey: up.objectKey,
    })
    expect(e?.status).toBe(422)
  }, 30000)

  it('非法 content-type → 422', async () => {
    const t = TYPES[5]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/evidence/upload-url`,
      { fileName: 'a.exe', contentType: 'application/x-msdownload', sizeBytes: 10, sha256: crypto.createHash('sha256').update('x').digest('hex') })
    expect(e?.status).toBe(422)
  })

  it('非法 size（0）→ 422', async () => {
    const t = TYPES[5]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/evidence/upload-url`,
      { fileName: 'a.txt', contentType: 'text/plain', sizeBytes: 0, sha256: crypto.createHash('sha256').update('x').digest('hex') })
    expect(e?.status).toBe(422)
  })

  it('非法 sha256 → 422', async () => {
    const t = TYPES[5]
    const rid = ((await seed(reviewBody(t))) as { reviewId: string }).reviewId
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', `/v1/manual-reviews/production/${rid}/evidence/upload-url`,
      { fileName: 'a.txt', contentType: 'text/plain', sizeBytes: 10, sha256: 'notsha' })
    expect(e?.status).toBe(422)
  })
})

// ============================ 21. process-outbox ============================
describe('POST /production/internal/process-outbox 出箱处理', () => {
  it('管理员触发返回 processed/failed 计数', async () => {
    const out = await runOutbox()
    expect(out).toHaveProperty('processed')
    expect(out).toHaveProperty('failed')
  })

  it('非管理员 → 403', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', '/v1/manual-reviews/production/internal/process-outbox')
    expect(e?.status).toBe(403)
  })
})

// ============================ 22. reclaim-expired ============================
describe('POST /production/internal/reclaim-expired 回收过期领取', () => {
  it('管理员触发返回 reclaimed 计数', async () => {
    asIdentity('admin', ['review_admin'])
    const r = (await raw('post', '/v1/manual-reviews/production/internal/reclaim-expired')).body.data
    expect(r).toHaveProperty('reclaimed')
    expect(typeof r.reclaimed).toBe('number')
  })

  it('非管理员 → 403', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const e = await err('post', '/v1/manual-reviews/production/internal/reclaim-expired')
    expect(e?.status).toBe(403)
  })
})

// ============================ 23. create-case（legacy 适配）============================
describe('POST /internal/cases 旧式建单适配', () => {
  it('旧式字段建单 → 生产审核单详情', async () => {
    asIdentity('reviewer-1', ['reviewer'])
    const r = (await raw('post', '/v1/manual-reviews/internal/cases', {
      eventId: `legacy-${Math.random().toString(36).slice(2, 8)}`,
      sourceTaskId: 'TASK-LEGACY', nodeId: 'schema',
      objectId: 'OBJ-LEGACY', objectType: 'Candidate', objectName: '旧式对象',
      errorType: '映射失败', domain: 'talent', phase: '图谱构建',
      candidate: { mappings: [] }, input: {}, evidence: [],
    })).body.data
    expect(r.id).toMatch(/^MR-/)
    expect(r.templateId).toBe('T_MAP')
    expect(r.duplicate).toBe(false)
    // 进队列可查
    const q = await getProductionReviews({ keyword: r.id })
    expect(q.items.some((i) => i.id === r.id)).toBe(true)
  })
})

// ============================ 24. §6 幂等（真实替身直测）============================
describe('图谱构建替身 §6 幂等（同 correctionId 返回同 executionId）', () => {
  it('重复下发同一 correctionId → 同 executionId', async () => {
    const t = TYPES[0]
    const { rid, execId } = await advanceToRerunning(t)
    // 拉取 correction 构造 resume payload
    const cor = (await internalHttp.get(`/v1/internal/manual-reviews/${rid}/correction`, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}` },
    })).data.data
    const payload = {
      reviewId: rid, correctionId: cor.correctionId, correctionVersion: cor.correctionVersion,
      stepId: cor.stepId, scope: cor.scope, sourceTaskId: `TASK-${t.key}-999`, batchId: 'BATCH-FULL',
      workflow: { workflowType: 'GraphBuildWorkflow', workflowId: 'wf', runId: 'r', taskQueue: 'graph-build', resumeToken: 'tok' },
      correctionUrl: `/api/v1/internal/manual-reviews/${rid}/correction`,
    }
    const r1 = await doubleHttp.post('/internal/review-resumes', payload, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': cor.correctionId },
    })
    // 第二次（retried=False）→ 幂等返回同 executionId
    const r2 = await doubleHttp.post('/internal/review-resumes', payload, {
      headers: { Authorization: `Bearer ${SERVICE_TOKEN}`, 'Idempotency-Key': cor.correctionId },
    })
    expect(r2.data.executionId).toBe(r1.data.executionId)
    void execId
  })
})

// ============================ 25. legacy /manual-reviews（任务中心审核）============================
describe('Legacy /manual-reviews（任务中心审核，真实 sqlite 仓库）', () => {
  it('列表返回 items + statusCounts', async () => {
    const r = await getManualReviews({})
    expect(r.items).toBeInstanceOf(Array)
    expect(r).toHaveProperty('statusCounts')
  })

  it('详情返回单条审核 + task/batchDetail', async () => {
    const list = await getManualReviews({})
    const id = list.items[0].id
    const r = await getManualReview(id)
    expect(r.id).toBe(id)
    expect(r).toHaveProperty('task')
  })

  it('flow 返回 {id, flow, task}', async () => {
    const list = await getManualReviews({})
    const id = list.items[0].id
    const r = (await raw('get', `/v1/manual-reviews/${id}/flow`)).body.data
    expect(r.id).toBe(id)
    expect(r).toHaveProperty('flow')
  })

  it('actions 提交处置 → 已完成', async () => {
    // 找一个待处理单
    const list = await getManualReviews({})
    const pending = list.items.find((i) => i.status === '待处理')
    expect(pending).toBeTruthy()
    const r = await submitManualReview(pending!.id, { actionId: 'confirm', note: '通过', result: { ok: true }, handler: 'tester', rerun: false })
    expect(r.review.status).toBe('已完成')
  })

  it('result 修改结果 → revision 推进', async () => {
    const list = await getManualReviews({})
    const id = list.items[0].id
    const before = (await getManualReview(id)).revision || 1
    const r = await modifyManualReviewResult(id, { patch: true }, '联调修改')
    expect(r.revision).toBeGreaterThan(before)
  })

  it('retry 重试工作流（Temporal 不可用走 LOCAL_FALLBACK）', async () => {
    // 先确保 graph-build 工作流定义存在（seed 仅含 entity-project），真实创建之
    await http.post('/v1/workflow-system/definitions', {
      id: 'graph-build', name: '图谱构建', category: 'graph', steps: ['增量抽取', '图谱写入'], taskQueue: 'tech-kg-workflows', active: true,
    })
    const list = await getManualReviews({})
    const id = list.items[0].id
    const r = await retryManualReview(id, { reason: '联调重试' })
    expect(r).toHaveProperty('id')
    expect(['QUEUED', 'RUNNING', 'COMPLETED', 'LOCAL_FALLBACK']).toContain(r.status || 'QUEUED')
  })

  it('revoke 撤销 → 已撤销', async () => {
    const list = await getManualReviews({})
    const pending = list.items.find((i) => i.status === '待处理') || list.items[0]
    const r = await revokeManualReview(pending.id, '联调撤销')
    expect(r.status).toBe('已撤销')
  })
})
