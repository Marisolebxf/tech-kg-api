/**
 * 配置管理表单字段校验（语言模型 / 向量模型 / MySQL 数据源 × 新建弹窗 + 详情抽屉、图数据空间弹窗）。
 * 口径对齐第一轮测试用例（FUNC-00404～00676、00872）：输入即校验——超长 / 异常字符 /
 * 数字位数与范围 / 必填，返回错误文案；只负责「不合规不让提交」，不改变提交链路本身。
 * 与 textInput.ts 的关系：那边是任务/Schema 表单口径，这边是配置管理各字段定制上限（128/256/200/500/64）。
 */

/** 数字输入框位数上限：第 65 位数字触发长度校验（FUNC-00417/00462～00464/00610/00872） */
export const NUMERIC_INPUT_MAX_LENGTH = 64

/** 异常字符：尖括号是脚本注入口径（FUNC-00431 等，测试数据 `<script>alert(1)</script>`） */
const MARKUP_CHARS = /[<>]/

/** 控制字符 / 零宽空格等不可见字符（防视觉欺骗与破坏下游 SQL/nGQL，口径同 textInput.ts） */
const ABNORMAL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u2028\u2029\u202A-\u202E\u2060\uFEFF]/

export interface TextFieldOptions {
  /** 必填（trim 后非空） */
  required?: boolean
  requiredMessage?: string
  /** 最大字符数（恰好等于上限必须能完整接收） */
  max: number
  /** 凭据类字段（API Key / 密码）：只做长度校验，字符集不拦（按安全字符串提交，连接验证会把关） */
  allowMarkup?: boolean
}

/** 校验单项文本：返回错误文案，合法返回 null。 */
export function validateTextField(label: string, value: unknown, options: TextFieldOptions): string | null {
  const text = value == null ? '' : String(value)
  if (options.required && !text.trim()) return options.requiredMessage || `请输入${label}`
  if (!text) return null
  if (text.length > options.max) return `输入长度不能超过${options.max}个字符`
  if (!options.allowMarkup && MARKUP_CHARS.test(text)) return `${label}包含异常字符（< >），请删除后重试`
  if (ABNORMAL_CHARS.test(text)) return `${label}包含控制字符或不可见字符，请删除后重试`
  return null
}

export interface NumericFieldOptions {
  label: string
  /** 有效范围（闭区间）；63/64 位数字仍可接收并按业务范围校验（FUNC-00462/00463） */
  min?: number
  max?: number
  required?: boolean
}

/**
 * 校验数字输入（端口 / 维度 / 批大小）：按原样字符串校验，不改绑定为 number——
 * v-model.number 会把 65 位数字折叠成 1e+64，位数校验就做不成了。
 * 空值返回 null（必填由调用方决定）；超长文案与用例逐字对齐。
 */
export function validateNumericField(value: unknown, options: NumericFieldOptions): string | null {
  const text = value == null ? '' : String(value).trim()
  if (!text) return options.required ? `请输入${options.label}` : null
  if (text.length > NUMERIC_INPUT_MAX_LENGTH) return `数字输入长度不能超过${NUMERIC_INPUT_MAX_LENGTH}个字符`
  if (!/^\d+$/.test(text)) return `${options.label}需为数字`
  const numeric = Number(text)
  if ((options.min != null && numeric < options.min) || (options.max != null && numeric > options.max)) {
    return `输入超出有效范围${options.min}～${options.max}`
  }
  return null
}

/** 数字字段提交值：空串/undefined 归 3306（表单预填默认口径），其余 Number()——杜绝 `0 || 3306` 把 0 静默换成 3306（FUNC-00454） */
export function portValueForSubmit(value: unknown): number {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? 3306 : Number(text)
}

/** 可空数字字段提交值：空归 null，其余 Number()（维度等可选数字） */
export function numberOrNullForSubmit(value: unknown): number | null {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : Number(text)
}

export type ConfigKindKey = 'llm' | 'embedding' | 'mysql'

/** 文本字段上限表（FUNC-00404～00638）：名称/模型/用户名/默认库 128；URL/主机/凭据 256 */
const CONFIG_TEXT_LIMITS = {
  name: 128,
  baseUrl: 256,
  model: 128,
  host: 256,
  defaultDatabase: 128,
  username: 128,
  apiKey: 256,
  password: 256,
} as const

/** 说明：新建表单 200（FUNC-00430/00492），详情抽屉 500（FUNC-00534～00536/00581～00583/00637） */
export const CREATE_DESCRIPTION_MAX = 200
export const DETAIL_DESCRIPTION_MAX = 500

/** 图数据空间名称：必填 + 64（FUNC-00672/00676），标识符字符集由后端 CREATE SPACE 约束 */
export function validateGraphSpaceName(value: unknown): string | null {
  return validateTextField('图数据空间名称', value, {
    required: true,
    requiredMessage: '请输入图数据空间名称',
    max: 64,
  })
}

export type ConfigFieldErrors = Partial<Record<
  'name' | 'baseUrl' | 'model' | 'apiKey' | 'dimensions' | 'host' | 'port' | 'defaultDatabase' | 'username' | 'password' | 'description',
  string
>>

/**
 * 整表校验：按配置类型对当前值算出全部字段错误（键为字段名）。
 * variant 只影响凭据必填（新建 API Key 必填、更新留空保留原值）与说明上限（新建 200 / 详情 500）。
 * 只校验该类型存在的字段，缺失字段不产生错误。
 */
export function validateConfigFields(
  kind: ConfigKindKey,
  values: Record<string, unknown>,
  variant: 'create' | 'detail',
): ConfigFieldErrors {
  const errors: ConfigFieldErrors = {}
  const limits = CONFIG_TEXT_LIMITS
  const put = (field: keyof ConfigFieldErrors, error: string | null) => {
    if (error) errors[field] = error
  }

  put('name', validateTextField('配置名称', values.name, { required: true, requiredMessage: '请输入配置名称', max: limits.name }))
  put(
    'description',
    validateTextField('说明', values.description, {
      max: variant === 'create' ? CREATE_DESCRIPTION_MAX : DETAIL_DESCRIPTION_MAX,
    }),
  )

  if (kind === 'llm' || kind === 'embedding') {
    put('baseUrl', validateTextField('Base URL', values.baseUrl, { required: true, requiredMessage: '请输入 Base URL', max: limits.baseUrl }))
    put('model', validateTextField('模型名称', values.model, { required: true, requiredMessage: '请输入模型名称', max: limits.model }))
    put(
      'apiKey',
      validateTextField('API Key', values.apiKey, {
        required: variant === 'create',
        requiredMessage: '请输入 API Key',
        max: limits.apiKey,
        allowMarkup: true,
      }),
    )
    if (kind === 'embedding') {
      put('dimensions', validateNumericField(values.dimensions, { label: '维度', min: 1, max: 8192 }))
    }
    return errors
  }

  put('host', validateTextField('主机地址', values.host, { required: true, requiredMessage: '请输入主机地址', max: limits.host }))
  put('port', validateNumericField(values.port, { label: '端口', min: 1, max: 65535 }))
  put('defaultDatabase', validateTextField('默认库', values.defaultDatabase, { max: limits.defaultDatabase }))
  put('username', validateTextField('用户名', values.username, { required: true, requiredMessage: '请输入用户名', max: limits.username }))
  put('password', validateTextField('密码', values.password, { max: limits.password, allowMarkup: true }))
  return errors
}
