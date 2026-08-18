import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

type Case = {
  id: string; module: '科技两点合作成果' | '科技专家两点校友关系'; name: string
  endpoint: string; body: Record<string, unknown>; expected: string
  assert: (http: number, payload: any) => boolean
}

const person = (n: number) => `person_expert_e2e_v1_${String(n).padStart(3, '0')}`
const coop = '/api/v1/kg-construction/expert-cooperation-achievements/query'
const alumni = '/api/v1/kg-construction/expert-alumni-relations/query'

const cases: Case[] = [
  { id:'COOP-001', module:'科技两点合作成果', name:'查询论文专利项目多类型成果', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(4),achievementTypes:['paper','patent','project'],limitPerType:20},
    expected:'HTTP 200，论文2、专利2、项目2，合作模式为多类型或长期稳定型', assert:(h,p)=>h===200&&p.code===200&&p.data.summary.papers===2&&p.data.summary.patents===2&&p.data.summary.projects===2 },
  { id:'COOP-002', module:'科技两点合作成果', name:'查询单篇共同论文', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(2),achievementTypes:['paper']}, expected:'共同论文1篇', assert:(h,p)=>h===200&&p.data?.summary?.papers===1 },
  { id:'COOP-003', module:'科技两点合作成果', name:'查询多篇共同论文', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(3),achievementTypes:['paper']}, expected:'共同论文2篇', assert:(h,p)=>h===200&&p.data?.summary?.papers===2 },
  { id:'COOP-004', module:'科技两点合作成果', name:'仅查询共同专利', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(6),achievementTypes:['patent']}, expected:'专利1项，其他类型为0', assert:(h,p)=>h===200&&p.data?.summary?.patents===1&&p.data.summary.papers===0 },
  { id:'COOP-005', module:'科技两点合作成果', name:'仅查询共同项目', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(7),achievementTypes:['project']}, expected:'项目1项，其他类型为0', assert:(h,p)=>h===200&&p.data?.summary?.projects===1&&p.data.summary.papers===0 },
  { id:'COOP-006', module:'科技两点合作成果', name:'无共同成果', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(20)}, expected:'三类数量均为0', assert:(h,p)=>h===200&&p.data?.summary?.papers===0&&p.data.summary.patents===0&&p.data.summary.projects===0 },
  { id:'COOP-007', module:'科技两点合作成果', name:'反向查询结果一致', endpoint:coop,
    body:{sourceExpertId:person(4),targetExpertId:person(1)}, expected:'与正向查询各类数量一致', assert:(h,p)=>h===200&&p.data?.summary?.papers===2&&p.data.summary.patents===2&&p.data.summary.projects===2 },
  { id:'COOP-008', module:'科技两点合作成果', name:'每类限制为1', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(4),limitPerType:1}, expected:'每一种成果最多返回1项', assert:(h,p)=>h===200&&p.data?.summary?.papers===1&&p.data.summary.patents===1&&p.data.summary.projects===1 },
  { id:'COOP-009', module:'科技两点合作成果', name:'开始年份过滤', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(3),achievementTypes:['paper'],timeRangeStart:'2022'}, expected:'仅保留2023年论文', assert:(h,p)=>h===200&&p.data?.summary?.papers===1&&String(p.data.items[0]?.time).startsWith('2023') },
  { id:'COOP-010', module:'科技两点合作成果', name:'结束年份过滤', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(3),achievementTypes:['paper'],timeRangeEnd:'2021'}, expected:'仅保留2021年论文', assert:(h,p)=>h===200&&p.data?.summary?.papers===1&&String(p.data.items[0]?.time).startsWith('2021') },
  { id:'COOP-011', module:'科技两点合作成果', name:'缺少时间成果查询', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(6),achievementTypes:['paper'],timeRangeStart:'2020',timeRangeEnd:'2025'}, expected:'时间缺失条目按当前规则保留', assert:(h,p)=>h===200&&p.data?.summary?.papers===1&&p.data.items[0]?.time===null },
  { id:'COOP-012', module:'科技两点合作成果', name:'不存在专家业务错误', endpoint:coop,
    body:{sourceExpertId:'person_expert_e2e_v1_999',targetExpertId:person(1)}, expected:'统一响应success=false且data为空', assert:(h,p)=>h===200&&p.success===false&&p.data===null },
  { id:'COOP-013', module:'科技两点合作成果', name:'缺陷-反向时间区间未校验', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(3),timeRangeStart:'2025',timeRangeEnd:'2020'}, expected:'应拒绝开始时间晚于结束时间', assert:(h,p)=>h===422||p.success===false },
  { id:'COOP-014', module:'科技两点合作成果', name:'缺陷-奖项字段未进入结果', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(4)}, expected:'有奖项的项目应使awards大于0', assert:(h,p)=>h===200&&p.data?.summary?.awards>0 },
  { id:'COOP-015', module:'科技两点合作成果', name:'缺陷-项目年份未参与时间过滤', endpoint:coop,
    body:{sourceExpertId:person(1),targetExpertId:person(7),achievementTypes:['project'],timeRangeEnd:'2020'}, expected:'2024年项目不应出现在截至2020年的结果中', assert:(h,p)=>h===200&&p.data?.summary?.projects===0 },

  { id:'ALUMNI-001', module:'科技专家两点校友关系', name:'同校同学历同期', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(7)}, expected:'命中同校、同学历、同期', assert:(h,p)=>h===200&&['同校','同学历','同期'].every(x=>p.data?.items?.[0]?.dimensions?.includes(x)) },
  { id:'ALUMNI-002', module:'科技专家两点校友关系', name:'同校不同学历同期', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(2)}, expected:'命中同校、同期，不命中同学历', assert:(h,p)=>h===200&&p.data?.items?.[0]?.dimensions?.includes('同校')&&!p.data.items[0].dimensions.includes('同学历') },
  { id:'ALUMNI-003', module:'科技专家两点校友关系', name:'同校同学历非同期', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(4)}, expected:'命中同校、同学历，不命中同期', assert:(h,p)=>h===200&&p.data?.items?.[0]?.dimensions?.includes('同学历')&&!p.data.items[0].dimensions.includes('同期') },
  { id:'ALUMNI-004', module:'科技专家两点校友关系', name:'不同院校不构成校友', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(57)}, expected:'total为0', assert:(h,p)=>h===200&&p.data?.total===0 },
  { id:'ALUMNI-005', module:'科技专家两点校友关系', name:'半角空格院校归一', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(71)}, expected:'归一后命中同校', assert:(h,p)=>h===200&&p.data?.items?.[0]?.dimensions?.includes('同校') },
  { id:'ALUMNI-006', module:'科技专家两点校友关系', name:'全角空格院校归一', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(72)}, expected:'NFKC归一后命中同校', assert:(h,p)=>h===200&&p.data?.items?.[0]?.dimensions?.includes('同校') },
  { id:'ALUMNI-007', module:'科技专家两点校友关系', name:'只有院校没有学历日期', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(75)}, expected:'只命中同校维度', assert:(h,p)=>h===200&&JSON.stringify(p.data?.items?.[0]?.dimensions)===JSON.stringify(['同校']) },
  { id:'ALUMNI-008', module:'科技专家两点校友关系', name:'没有院校字段', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(77)}, expected:'total为0', assert:(h,p)=>h===200&&p.data?.total===0 },
  { id:'ALUMNI-009', module:'科技专家两点校友关系', name:'列表limit为1', endpoint:alumni,
    body:{expertId:person(1),limit:1}, expected:'返回1条校友', assert:(h,p)=>h===200&&p.data?.items?.length===1 },
  { id:'ALUMNI-010', module:'科技专家两点校友关系', name:'列表limit为50', endpoint:alumni,
    body:{expertId:person(1),limit:50}, expected:'返回50条校友', assert:(h,p)=>h===200&&p.data?.items?.length===50 },
  { id:'ALUMNI-011', module:'科技专家两点校友关系', name:'院校过滤', endpoint:alumni,
    body:{expertId:person(1),school:'清华大学',limit:20}, expected:'返回结果共享院校均匹配清华大学', assert:(h,p)=>h===200&&p.data?.items?.length>0&&p.data.items.every((x:any)=>x.sharedInstitutions.some((s:string)=>s.includes('清华大学'))) },
  { id:'ALUMNI-012', module:'科技专家两点校友关系', name:'不存在专家业务错误', endpoint:alumni,
    body:{expertId:'person_expert_e2e_v1_999'}, expected:'统一响应success=false且data为空', assert:(h,p)=>h===200&&p.success===false&&p.data===null },
  { id:'ALUMNI-013', module:'科技专家两点校友关系', name:'同一专家业务校验', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(1)}, expected:'统一响应success=false且data为空', assert:(h,p)=>h===200&&p.success===false&&p.data===null },
  { id:'ALUMNI-014', module:'科技专家两点校友关系', name:'缺陷-中英文同校未交叉匹配', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(73)}, expected:'中英文名称指向同一院校，应命中同校', assert:(h,p)=>h===200&&p.data?.total===1 },
  { id:'ALUMNI-015', module:'科技专家两点校友关系', name:'缺陷-学历过滤匹配任一方', endpoint:alumni,
    body:{expertId:person(1),targetExpertId:person(2),educationStage:'硕士'}, expected:'源专家为博士，按硕士过滤不应返回该组合', assert:(h,p)=>h===200&&p.data?.total===0 },
]

test.describe.configure({ mode: 'serial' })
test('通过真实 Swagger UI 执行两个模块30条用例并逐条截图', async ({ page }) => {
  test.setTimeout(15 * 60_000)
  const out = path.resolve('../artifacts/expert-modules-swagger')
  const shots = path.join(out, 'screenshots')
  fs.mkdirSync(shots, { recursive: true })
  await page.setViewportSize({ width: 1600, height: 1100 })
  await page.goto('http://127.0.0.1:8003/docs', { waitUntil: 'networkidle' })
  const results: any[] = []

  for (const item of cases) {
    const op = page.locator('.opblock-post').filter({ has: page.locator('.opblock-summary-path', { hasText: item.endpoint }) }).first()
    await op.scrollIntoViewIfNeeded()
    if (!(await op.getAttribute('class'))?.includes('is-open')) await op.locator('.opblock-summary').click()
    const tryButton = op.getByRole('button', { name: 'Try it out', exact: true })
    if (await tryButton.count()) await tryButton.click()
    const textarea = op.locator('textarea.body-param__text')
    await textarea.fill(JSON.stringify(item.body, null, 2))
    const responsePromise = page.waitForResponse(r => r.url().endsWith(item.endpoint) && r.request().method() === 'POST')
    await op.locator('button.execute').click()
    const response = await responsePromise
    const http = response.status()
    let payload: any = await response.text()
    try { payload = JSON.parse(payload) } catch { /* keep raw evidence */ }
    await expect(op.locator('.live-responses-table')).toBeVisible({ timeout: 30_000 })
    await page.waitForTimeout(150)
    const passed = item.assert(http, payload)
    const screenshot = `${item.id}-${passed ? '无bug' : '有bug'}.png`
    await op.screenshot({ path: path.join(shots, screenshot) })
    results.push({ id:item.id, module:item.module, name:item.name, endpoint:item.endpoint, input:item.body,
      expected:item.expected, actualHttp:http, actualResponse:payload, result:passed?'无bug':'有bug', screenshot:`screenshots/${screenshot}` })
  }
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2))
  fs.writeFileSync(path.join(out, 'cases.json'), JSON.stringify(cases.map(({assert,...x})=>x), null, 2))
  expect(results).toHaveLength(30)
})
