import { describe, expect, it } from 'vitest'

import {
  CREATE_DESCRIPTION_MAX,
  DETAIL_DESCRIPTION_MAX,
  numberOrNullForSubmit,
  portValueForSubmit,
  validateConfigFields,
  validateGraphSpaceName,
  validateNumericField,
  validateTextField,
} from './configFieldValidation'

const repeat = (ch: string, n: number) => ch.repeat(n)

/** 语言模型/MySQL 各一条合法基线值，单项测试在其上改一个字段 */
const validLlm = () => ({
  name: '抽取大模型',
  baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
  model: 'glm-5.3-flash',
  apiKey: 'sk-test',
  description: '',
})

const validEmbedding = () => ({ ...validLlm(), model: 'embedding-3', dimensions: 1024 })

const validMysql = () => ({
  name: '业务库',
  host: '127.0.0.1',
  port: 3306,
  defaultDatabase: 'gkx_element',
  username: 'root',
  password: '123456',
  description: '',
})

describe('validateTextField 长度边界（FUNC-00404/00443/00478/00506～00522）', () => {
  it('128 上限：127/128 合法，129 报错且文案含上限', () => {
    expect(validateTextField('配置名称', repeat('A', 127), { max: 128 })).toBeNull()
    expect(validateTextField('配置名称', repeat('A', 128), { max: 128 })).toBeNull()
    expect(validateTextField('配置名称', repeat('A', 129), { max: 128 })).toBe('输入长度不能超过128个字符')
  })

  it('256 上限（Base URL/主机/凭据）：255/256 合法，257 报错（FUNC-00423/00485/00513～00515）', () => {
    expect(validateTextField('Base URL', repeat('h', 256), { max: 256 })).toBeNull()
    expect(validateTextField('Base URL', repeat('h', 257), { max: 256 })).toBe('输入长度不能超过256个字符')
  })

  it('中文按字符计数', () => {
    expect(validateTextField('说明', '测'.repeat(200), { max: 200 })).toBeNull()
    expect(validateTextField('说明', '测'.repeat(201), { max: 200 })).toBe('输入长度不能超过200个字符')
  })
})

describe('validateTextField 异常字符（FUNC-00431 等 XSS 簇）', () => {
  it('尖括号输入立即报错（不依赖提交）', () => {
    expect(validateTextField('说明', '<script>alert(1)</script>', { max: 200 })).toContain('异常字符')
    expect(validateTextField('主机地址', '127.0.0.1;<script>', { max: 256 })).toContain('异常字符')
  })

  it('凭据类 allowMarkup 不做字符集校验（密码控件 + 安全字符串提交口径，FUNC-00424/00486）', () => {
    expect(validateTextField('API Key', '<script>alert(1)</script>', { max: 256, allowMarkup: true })).toBeNull()
    expect(validateTextField('密码', '<script>', { max: 256, allowMarkup: true })).toBeNull()
  })

  it('必填：空/空白报必填，其余字段合法', () => {
    expect(validateTextField('用户名', '', { required: true, max: 128 })).toBe('请输入用户名')
    expect(validateTextField('用户名', '   ', { required: true, max: 128 })).toBe('请输入用户名')
    expect(validateTextField('用户名', 'root', { required: true, max: 128 })).toBeNull()
  })
})

describe('validateNumericField 位数与范围（FUNC-00407/00412/00417/00454/00462～00464）', () => {
  const port = { label: '端口', min: 1, max: 65535 }

  it('63/64 位数字可接收并按业务范围校验（位数不报错，范围报错）', () => {
    expect(validateNumericField(repeat('9', 63), port)).toBe('输入超出有效范围1～65535')
    expect(validateNumericField(repeat('9', 64), port)).toBe('输入超出有效范围1～65535')
  })

  it('第 65 位数字触发位数校验，文案逐字对齐用例', () => {
    expect(validateNumericField(repeat('9', 65), port)).toBe('数字输入长度不能超过64个字符')
  })

  it('端口边界：0 拒绝、1/65535 合法、65536 拒绝', () => {
    expect(validateNumericField('0', port)).toBe('输入超出有效范围1～65535')
    expect(validateNumericField('1', port)).toBeNull()
    expect(validateNumericField('65535', port)).toBeNull()
    expect(validateNumericField('65536', port)).toBe('输入超出有效范围1～65535')
  })

  it('维度边界：0/8193 拒绝、1/8192 合法、空可空（FUNC-00407/00412/00560/00565）', () => {
    const dim = { label: '维度', min: 1, max: 8192 }
    expect(validateNumericField('0', dim)).toBe('输入超出有效范围1～8192')
    expect(validateNumericField('8193', dim)).toBe('输入超出有效范围1～8192')
    expect(validateNumericField('1', dim)).toBeNull()
    expect(validateNumericField('8192', dim)).toBeNull()
    expect(validateNumericField('', dim)).toBeNull()
  })

  it('非数字（科学计数法 e 等）报数字格式错误', () => {
    expect(validateNumericField('12e5', { label: '端口' })).toBe('端口需为数字')
  })
})

describe('提交值换算（FUNC-00454：输入 0 不得静默回退 3306）', () => {
  it('空值归默认 3306，0 保持 0 交由校验拦截', () => {
    expect(portValueForSubmit('')).toBe(3306)
    expect(portValueForSubmit(undefined)).toBe(3306)
    expect(portValueForSubmit(0)).toBe(0)
    expect(portValueForSubmit('3306')).toBe(3306)
    expect(portValueForSubmit(' 3307 ')).toBe(3307)
  })

  it('可空数字：空归 null（维度留空语义），数字字符串转数字', () => {
    expect(numberOrNullForSubmit('')).toBeNull()
    expect(numberOrNullForSubmit(null)).toBeNull()
    expect(numberOrNullForSubmit('1024')).toBe(1024)
    expect(numberOrNullForSubmit(2048)).toBe(2048)
  })
})

describe('validateConfigFields 整表（新建/详情两套口径）', () => {
  it('合法基线三类型零错误', () => {
    expect(validateConfigFields('llm', validLlm(), 'create')).toEqual({})
    expect(validateConfigFields('embedding', validEmbedding(), 'create')).toEqual({})
    expect(validateConfigFields('mysql', validMysql(), 'create')).toEqual({})
  })

  it('MySQL 用户名为空报必填（FUNC-00473）', () => {
    const values = { ...validMysql(), username: '' }
    expect(validateConfigFields('mysql', values, 'create').username).toBe('请输入用户名')
  })

  it('向量模型详情：模型为空报必填（FUNC-00553），更新 API Key 留空合法（FUNC-00526）', () => {
    const values = { ...validEmbedding(), model: '', apiKey: '' }
    const errors = validateConfigFields('embedding', values, 'detail')
    expect(errors.model).toBe('请输入模型名称')
    expect(errors.apiKey).toBeUndefined()
  })

  it('新建 API Key 必填、257 位报超长（FUNC-00423）', () => {
    expect(validateConfigFields('llm', { ...validLlm(), apiKey: '' }, 'create').apiKey).toBe('请输入 API Key')
    expect(validateConfigFields('llm', { ...validLlm(), apiKey: repeat('k', 257) }, 'create').apiKey).toBe('输入长度不能超过256个字符')
  })

  it('说明上限：新建 200 / 详情 500（FUNC-00430/00492/00534～00536/00637）', () => {
    expect(CREATE_DESCRIPTION_MAX).toBe(200)
    expect(DETAIL_DESCRIPTION_MAX).toBe(500)
    const over200 = repeat('d', CREATE_DESCRIPTION_MAX + 1)
    expect(validateConfigFields('llm', { ...validLlm(), description: over200 }, 'create').description).toBeTruthy()
    expect(validateConfigFields('llm', { ...validLlm(), description: over200 }, 'detail').description).toBeUndefined()
    const over500 = repeat('d', DETAIL_DESCRIPTION_MAX + 1)
    expect(validateConfigFields('mysql', { ...validMysql(), description: over500 }, 'detail').description).toBe('输入长度不能超过500个字符')
  })

  it('主机/默认库异常字符拦截（FUNC-00452/00471/00598/00617）', () => {
    expect(validateConfigFields('mysql', { ...validMysql(), host: '127.0.0.1;<script>' }, 'create').host).toContain('异常字符')
    expect(validateConfigFields('mysql', { ...validMysql(), defaultDatabase: 'gkx_element;<script>' }, 'detail').defaultDatabase).toContain('异常字符')
  })

  it('端口 0 在整表里也拦截（FUNC-00454）', () => {
    expect(validateConfigFields('mysql', { ...validMysql(), port: 0 }, 'create').port).toBe('输入超出有效范围1～65535')
    expect(validateConfigFields('mysql', { ...validMysql(), port: '0' }, 'detail').port).toBe('输入超出有效范围1～65535')
  })

  it('详情主机 256/257 边界（FUNC-00596/00597）', () => {
    expect(validateConfigFields('mysql', { ...validMysql(), host: repeat('h', 256) }, 'detail').host).toBeUndefined()
    expect(validateConfigFields('mysql', { ...validMysql(), host: repeat('h', 257) }, 'detail').host).toBe('输入长度不能超过256个字符')
  })
})

describe('validateGraphSpaceName（FUNC-00672/00676）', () => {
  it('空报必填文案', () => {
    expect(validateGraphSpaceName('')).toBe('请输入图数据空间名称')
  })

  it('64 合法、65 报超长', () => {
    expect(validateGraphSpaceName(repeat('s', 64))).toBeNull()
    expect(validateGraphSpaceName(repeat('s', 65))).toBe('输入长度不能超过64个字符')
  })
})
