import { http } from './http'

/**
 * 知识图谱构建接口统一前缀。
 *
 * http.ts 中已经配置：
 * baseURL: '/api'
 *
 * 因此这里写 /v1/kg-construction，
 * 最终请求地址就是：
 *
 * /api/v1/kg-construction/...
 */
const PREFIX =
  '/v1/kg-construction'


/* =========================================================
 * 1. 知识图谱构建模块
 * ========================================================= */

/**
 * 模块状态。
 *
 * 当前后端实际存在：
 * ready
 * scaffold
 *
 * 后续如果新增其他状态，
 * string 仍然可以兼容。
 */
export type RelationModuleStatus =
  | 'ready'
  | 'scaffold'
  | (string & {})


/**
 * GET /kg-construction/modules
 * 返回的单个模块结构。
 */
export interface KgConstructionModule {
  code: string
  name: string
  description: string
  status: RelationModuleStatus
}


/**
 * GET /kg-construction/modules
 * 返回的数据结构。
 */
export interface KgConstructionModuleList {
  items: KgConstructionModule[]
}


/**
 * 获取全部知识图谱构建模块。
 *
 * 实际请求：
 * GET /api/v1/kg-construction/modules
 */
export function listKgConstructionModules() {
  return http.get<KgConstructionModuleList>(
    `${PREFIX}/modules`,
  )
}


/**
 * 获取指定知识图谱构建模块信息。
 *
 * 实际请求：
 * GET /api/v1/kg-construction/modules/{module_code}
 */
export function getKgConstructionModule(
  moduleCode: string,
) {
  return http.get<KgConstructionModule>(
    `${PREFIX}/modules/${
      encodeURIComponent(
        moduleCode,
      )
    }`,
  )
}


/* =========================================================
 * 2. 科技专家 / 人才直接关系
 * ========================================================= */

/**
 * 直接关系查询请求参数。
 *
 * 对应：
 * POST
 * /api/v1/kg-construction/expert-direct-relations/query
 *
 * 字段已经根据当前 Swagger 确认。
 */
export interface DirectRelationQuery {
  dataSource: string
  endTime: string
  expertAId: string
  expertBId: string
  institution: string
  limit: number
  startTime: string
}


/**
 * 直接关系接口中的专家对象。
 *
 * 当前字段来自已经实际执行成功的
 * expert-direct-relations/query 返回结果。
 */
export interface DirectRelationExpert {
  expertId: string
  name: string

  organization?: string
  title?: string

  paperCount?: number
  citationCount?: number
  hIndex?: number

  /**
   * 后端以后如果在专家对象中返回置信度，
   * 前端直接读取。
   */
  confidence?: number
}


/**
 * 单条直接关系。
 */
export interface DirectRelationItem {
  key: string
  relationType: string

  expertA: DirectRelationExpert
  expertB: DirectRelationExpert

  /**
   * 为后续后端增加关系置信度预留。
   *
   * 前端不计算，只读取。
   */
  confidence?: number
  relationConfidence?: number
}


/**
 * 直接关系接口完整返回结构。
 *
 * 当前已经实际看到：
 *
 * taskName
 * input
 * total
 * items
 */
export interface DirectRelationResponse {
  taskName: string

  input: DirectRelationQuery

  total: number

  items: DirectRelationItem[]
}


/**
 * 查询科技专家 / 人才直接关系。
 *
 * 实际请求：
 * POST
 * /api/v1/kg-construction/expert-direct-relations/query
 */
export function queryExpertDirectRelations(
  payload: DirectRelationQuery,
) {
  return http.post<DirectRelationResponse>(
    `${PREFIX}/expert-direct-relations/query`,
    payload,
  )
}


/* =========================================================
 * 3. 科技专家校友关系
 * ========================================================= */

/**
 * 校友关系查询参数。
 *
 * 对应：
 * POST
 * /api/v1/kg-construction/expert-alumni-relations/query
 *
 * 字段已经根据 Swagger 确认。
 */
export interface AlumniRelationQuery {
  expertId: string
  targetExpertId: string
  school: string
  educationStage: string
  limit: number
}


/**
 * 当前部分业务接口使用的统一响应包装。
 *
 * 校友接口当前失败响应已经确认形如：
 *
 * {
 *   code: 404,
 *   success: false,
 *   data: null,
 *   msg: "专家不存在..."
 * }
 */
export interface BusinessApiResponse<T> {
  code: number
  success: boolean
  data: T | null
  msg?: string
}


/**
 * 查询科技专家校友关系。
 *
 * 目前成功返回 data 的详细字段
 * 仍在后端同步开发，因此暂时使用 unknown。
 *
 * 等后端成功返回结构确定后，
 * 只需要把 unknown 换成正式类型。
 */
export function queryExpertAlumniRelations(
  payload: AlumniRelationQuery,
) {
  return http.post<
    BusinessApiResponse<unknown>
  >(
    `${PREFIX}/expert-alumni-relations/query`,
    payload,
  )
}

/* =========================================================
 * 4. 科技专家论文合作关系
 * ========================================================= */

/**
 * 论文合作结构化结果查询参数。
 *
 * 对应：
 * POST
 * /api/v1/kg-construction/
 * expert-paper-cooperation-relations/
 * structured-result
 */
export interface PaperCooperationQuery {
  endTime: string
  expertAId: string
  expertBId: string
  startTime: string
}

export interface PaperCooperationTimeRange {
  startYear: number
  endYear: number
  displayText: string
}

export interface PaperCooperationCitation {
  total: number
  max: number
}

export interface PaperCooperationProvenance {
  sourceDatabase: string
  summary: string
  evidences: Array<{
    title: string
    businessTable: string
    technicalTable: string
    recordId: string
    fieldIdentifier: string
    summary: string
  }>
}

export interface PaperCooperationStructuredResult {
  authorList: string[]
  authorUnits: string[]

  cooperationTimeRange:
    PaperCooperationTimeRange

  paperTopics: string[]

  cooperationPaperCount: number

  journalLevelCount:
    Record<string, number>

  conferenceLevelCount:
    Record<string, number>

  citation:
    PaperCooperationCitation

  cooperationFrequency: number

  academicImpactScore: number

  stableTeamMembers: string[]

  coreCollaborators: string[]

  sharedContribution: string[]
}

export interface PaperCooperationResponse {
  structuredResult:
    PaperCooperationStructuredResult
  provenance: PaperCooperationProvenance
}

/**
 * 查询专家论文合作结构化结果。
 */
export function queryExpertPaperCooperation(
  payload: PaperCooperationQuery,
) {
  return http.post<
    PaperCooperationResponse
  >(
    `${PREFIX}`
    + '/expert-paper-cooperation-relations'
    + '/structured-result',
    payload,
  )
}

/* =========================================================
 * 4. Operator
 * ========================================================= */

/**
 * Operator 基本信息。
 *
 * 当前关系类型查询暂时不会依赖它，
 * 先保留调用能力。
 */
export interface OperatorInfo {
  name: string
  version?: string
  kind?: string
  description?: string
  builtin?: boolean
  updated_at?: string
}


/**
 * Operator 列表返回结构。
 */
export interface OperatorListResponse {
  items: OperatorInfo[]
}


/**
 * 获取 Operator 列表。
 *
 * 实际请求：
 * GET /api/v1/operators
 */
export function listOperators(
  kind?: string,
) {
  return http.get<OperatorListResponse>(
    '/v1/operators',
    {
      params:
        kind
          ? { kind }
          : undefined,
    },
  )
}


/**
 * 通用 Operator 调用。
 *
 * 当前不要直接拿它实现关系类型查询。
 * 只有后续确认某个关系模块明确通过
 * Operator 执行时才调用。
 *
 * 实际请求：
 * POST /api/v1/operators/{name}/invoke
 */
export function invokeOperator(
  name: string,
  payload: Record<string, unknown>,
) {
  return http.post(
    `/v1/operators/${
      encodeURIComponent(name)
    }/invoke`,
    payload,
  )
}
