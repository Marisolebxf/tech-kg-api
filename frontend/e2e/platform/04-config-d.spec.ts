import { expect, test } from '@playwright/test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { api, apiMust, autoAcceptConfirms, waitFor } from './helpers'

const execFileAsync = promisify(execFile)

/** 从容器运行时读 env（敏感值不落文件）。 */
async function containerEnv(name: string): Promise<string> {
  const { stdout } = await execFileAsync('docker', ['exec', 'tech-kg-api-dev2', 'printenv', name], { timeout: 15_000 })
  return stdout.trim()
}

// D. 配置管理（/configurations）
test.describe.serial('D. 配置管理', () => {
  const LLM_NAME = 'e2e_llm'
  const MYSQL_NAME = 'e2e_mysql'
  let llmId = ''
  let mysqlId = ''

  test('D1 五类配置列表与筛选', async ({ page }) => {
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('配置分类').first()).toBeVisible()

    // 五个分类均可加载（LLM 类至少一条现网配置）
    for (const cat of ['语言模型', '向量模型', 'MySQL 数据源', '向量数据空间', '图数据空间']) {
      await page.getByRole('button', { name: cat, exact: false }).first().click()
      await waitFor(
        async () => (await page.locator('h2').first().innerText()).length > 0,
        { label: `${cat} 列表加载` },
      )
    }
    await page.getByRole('button', { name: '语言模型', exact: false }).first().click()
    // LLM 类至少一条现网配置（不点名——具体配置名会被用户改）
    await waitFor(
      async () => (await page.locator('tbody tr').count()) >= 1,
      { label: 'LLM 列表非空', timeout: 15_000 },
    )

    // 顶部搜索过滤
    await page.locator('input[placeholder="搜索名称、标识或地址"]').fill('model')
    await waitFor(
      async () => {
        const rows = page.locator('tbody tr')
        const n = await rows.count()
        return n > 0 && n < 10 ? n : null
      },
      { label: '搜索收敛' },
    )
    await page.locator('input[placeholder="搜索名称、标识或地址"]').fill('')
  })

  test('D2 新建 LLM 配置（验证连接门禁）', async ({ page, request }) => {
    test.setTimeout(180_000)
    const apiKey = await containerEnv('LLM_API_KEY')
    test.skip(!apiKey, 'api 容器未配 LLM_API_KEY')

    // 清理旧残留（幂等）
    const list = await apiMust<any>(request, 'GET', '/llm-config/llm-configs', undefined, '列 LLM')
    const items = Array.isArray(list) ? list : (list.items ?? [])
    for (const item of items) {
      if (item.name === LLM_NAME) await api(request, 'DELETE', `/llm-config/llm-configs/${item.id}`)
    }

    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '语言模型', exact: false }).first().click()
    await page.getByRole('button', { name: '＋ 新建配置' }).click()
    const dialog = page.locator('.config-create-dialog')
    await expect(dialog).toBeVisible()
    const field = (label: string) => dialog.locator('.arco-form-item', { hasText: label }).locator('input').first()

    await field('配置名称').fill(LLM_NAME)
    await field('Base URL').fill('https://open.bigmodel.cn/api/paas/v4')
    await field('模型').fill('glm-4.7-flash')
    await field('API Key').fill(apiKey)

    // 未验证前保存按钮文案为「验证通过后可保存」且不可提交
    const saveBtn = dialog.getByRole('button', { name: /验证通过后可保存|保存/ }).last()
    await expect(dialog.getByRole('button', { name: '验证通过后可保存' })).toBeVisible()

    // 验证连接 → 通过后可保存。智谱对外限流（429「该模型当前访问量过大」/
    // 1302 账号限流）是外部服务状态，非产品缺陷——重试 3 次仍限流则记环境 skip
    let verifiedOk = false
    let rateLimited = false
    for (let attempt = 0; attempt < 3; attempt++) {
      await dialog.getByRole('button', { name: '验证连接' }).click()
      const ok = await dialog
        .getByRole('button', { name: '保存', exact: true })
        .waitFor({ timeout: 45_000 })
        .then(() => true)
        .catch(() => false)
      if (ok) { verifiedOk = true; break }
      const bodyText = await page.locator('body').innerText().catch(() => '')
      if (/访问量过大|1302|限流|429/.test(bodyText)) { rateLimited = true; continue }
      await page.waitForTimeout(3000)
    }
    if (!verifiedOk) {
      test.skip(rateLimited, '智谱 LLM 外部限流（429/1302），验证连接不可用——环境问题非产品缺陷')
      throw new Error('验证连接 3 次未通过且非限流')
    }
    await saveBtn.click().catch(() => {})

    // 列表出现 e2e_llm 状态正常
    await waitFor(
      async () => (await page.getByText(LLM_NAME).first().isVisible().catch(() => false)),
      { label: '列表出现新配置' },
    )
    const after = await apiMust<any>(request, 'GET', '/llm-config/llm-configs', undefined, '复核')
    const afterItems = Array.isArray(after) ? after : (after.items ?? [])
    llmId = afterItems.find((i: any) => i.name === LLM_NAME)?.id ?? ''
    expect(llmId).toBeTruthy()
  })

  test('D3 配置详情抽屉：测试连接/设默认/停用/删除', async ({ page, request }) => {
    test.skip(!llmId, 'D2 未产出')
    test.setTimeout(180_000)
    autoAcceptConfirms(page)
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '语言模型', exact: false }).first().click()
    await page.getByText(LLM_NAME).first().click()

    const drawer = page.locator('.detail-drawer')
    await expect(drawer).toBeVisible({ timeout: 15_000 })
    await expect(drawer.getByText(LLM_NAME).first()).toBeVisible()

    // 测试连接 toast（智谱外部限流 429/1302 时重试，持续限流记环境 skip）
    let connOk = false
    let connRateLimited = false
    for (let attempt = 0; attempt < 3; attempt++) {
      await drawer.getByRole('button', { name: '测试连接' }).click()
      const ok = await waitFor(
        async () => (await page.getByText(/连接测试成功，延迟/).first().isVisible().catch(() => false)),
        { timeout: 45_000, label: `测试连接 toast（第 ${attempt + 1} 次）` },
      ).then(() => true).catch(() => false)
      if (ok) { connOk = true; break }
      const bodyText = await page.locator('body').innerText().catch(() => '')
      if (/访问量过大|1302|限流|429/.test(bodyText)) { connRateLimited = true; continue }
      await page.waitForTimeout(3000)
    }
    if (!connOk) {
      test.skip(connRateLimited, '智谱 LLM 外部限流，测试连接不可用——环境问题非产品缺陷')
      throw new Error('测试连接 3 次未成功且非限流')
    }

    // 设为默认
    await drawer.getByRole('button', { name: '设为默认' }).click()
    await waitFor(
      async () => (await page.getByText(/默认|设为默认成功/).first().isVisible().catch(() => false)),
      { label: '设默认反馈' },
    )
    // 停用 → 启用
    await drawer.getByRole('button', { name: '停用配置' }).click()
    await waitFor(
      async () => (await drawer.getByRole('button', { name: '启用配置' }).isVisible().catch(() => false)),
      { label: '停用→启用按钮翻转' },
    )
    await drawer.getByRole('button', { name: '启用配置' }).click()
    await waitFor(
      async () => (await drawer.getByRole('button', { name: '停用配置' }).isVisible().catch(() => false)),
      { label: '启用→停用按钮翻转' },
    )

    // 删除（window.confirm）
    await drawer.getByRole('button', { name: '删除', exact: true }).click()
    await waitFor(
      async () => {
        const after = await apiMust<any>(request, 'GET', '/llm-config/llm-configs', undefined, '复核删除')
        const items = Array.isArray(after) ? after : (after.items ?? [])
        return items.some((i: any) => i.id === llmId) ? null : true
      },
      { timeout: 30_000, label: '删除后列表消失' },
    )
  })

  test('D4 新建 MySQL 数据源 + 连接测试 + 资源选择器', async ({ page, request }) => {
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'MySQL 数据源', exact: false }).first().click()
    await page.getByRole('button', { name: '＋ 新建配置' }).click()
    const dialog = page.locator('.config-create-dialog')
    await expect(dialog).toBeVisible()
    const field = (label: string) => dialog.locator('.arco-form-item', { hasText: label }).locator('input').first()

    await field('配置名称').fill(MYSQL_NAME)
    await field('主机').fill('temporal-mysql-dev2')
    await field('端口').fill('3306')
    await field('默认库').fill('techkg_e2e')
    await field('用户名').fill('root')
    await field('密码').fill('temporal')
    await dialog.getByRole('button', { name: /保存|提交/ }).last().click()

    await waitFor(
      async () => (await page.getByText(MYSQL_NAME).first().isVisible().catch(() => false)),
      { label: '列表出现新数据源' },
    )
    const list = await apiMust<any>(request, 'GET', '/mysql-datasources', undefined, '复核')
    const items = Array.isArray(list) ? list : (list.items ?? [])
    // 同名残留可能多行（历史运行），按更新时间取最新一条
    const sameName = items.filter((i: any) => i.name === MYSQL_NAME)
      .sort((a: any, b: any) => String(b.updatedAt ?? '').localeCompare(String(a.updatedAt ?? '')))
    mysqlId = sameName[0]?.id ?? ''
    expect(mysqlId).toBeTruthy()

    // 详情「测试连接」成功 toast
    await page.getByText(MYSQL_NAME).first().click()
    const drawer = page.locator('.detail-drawer')
    await expect(drawer).toBeVisible({ timeout: 15_000 })
    await expect(drawer.getByText(MYSQL_NAME).first()).toBeVisible()
    await drawer.getByRole('button', { name: '测试连接' }).click()
    await waitFor(
      async () => (await page.getByText(/连接测试成功，延迟/).first().isVisible().catch(() => false)),
      { label: 'MySQL 测试连接 toast' },
    )

    // 资源选择器 API（供任务弹窗使用）
    const dbs = await apiMust<any>(request, 'GET', `/mysql-datasources/${mysqlId}/databases`, undefined, '列库')
    expect(dbs.items).toContain('techkg_e2e')
    const tables = await apiMust<any>(
      request,
      'GET',
      `/mysql-datasources/${mysqlId}/tables?database=techkg_e2e`,
      undefined,
      '列表',
    )
    expect(tables.items.map((t: any) => t.name)).toContain('widgets')
    const cols = await apiMust<any>(
      request,
      'GET',
      `/mysql-datasources/${mysqlId}/tables/widgets/columns?database=techkg_e2e`,
      undefined,
      '列列',
    )
    expect(cols.items.map((c: any) => c.name)).toContain('id')

    // 测试完删除
    autoAcceptConfirms(page)
    await drawer.getByRole('button', { name: '删除', exact: true }).click()
    await waitFor(
      async () => {
        const after = await apiMust<any>(request, 'GET', '/mysql-datasources', undefined, '复核删除')
        const its = Array.isArray(after) ? after : (after.items ?? [])
        return its.some((i: any) => i.id === mysqlId) ? null : true
      },
      { label: '数据源删除' },
    )
  })

  test('D5 图数据空间绑定/解绑', async ({ page, request }) => {
    test.skip(true, 'e2e_verify_space 已被 M 组用作空空间素材；本用例的绑定/解绑改在 M 组流程内覆盖（绑定状态切换）')
  })

  test('D6 Milvus / Embedding 配置冒烟', async ({ page, request }) => {
    test.setTimeout(240_000)
    const glmKey = process.env.E2E_GLM_EMBEDDING_KEY ?? (await containerEnv('LLM_API_KEY'))
    test.skip(!glmKey, '无可用 GLM key（E2E_GLM_EMBEDDING_KEY 未设）')

    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')

    // Milvus：新建 + 测试连接 + 删除
    await page.getByRole('button', { name: '向量数据空间', exact: false }).first().click()
    await page.getByRole('button', { name: '＋ 新建配置' }).click()
    let dialog = page.locator('.config-create-dialog')
    await expect(dialog).toBeVisible()
    await dialog.locator('.arco-form-item', { hasText: '配置名称' }).locator('input').first().fill('e2e_milvus')
    await dialog.locator('.arco-form-item', { hasText: 'URI' }).locator('input').first().fill('http://milvus:19530')
    await dialog.getByRole('button', { name: /保存|提交/ }).last().click()
    await waitFor(
      async () => (await page.getByText('e2e_milvus').first().isVisible().catch(() => false)),
      { label: 'milvus 配置入列' },
    )
    await page.getByText('e2e_milvus').first().click()
    let drawer = page.locator('.detail-drawer')
    await expect(drawer).toBeVisible({ timeout: 15_000 })
    await expect(drawer.getByText('e2e_milvus').first()).toBeVisible()
    await drawer.getByRole('button', { name: '测试连接' }).click()
    await waitFor(
      async () => (await page.getByText(/连接测试成功，延迟/).first().isVisible().catch(() => false)),
      { timeout: 60_000, label: 'milvus 测试连接' },
    )
    autoAcceptConfirms(page)
    await drawer.getByRole('button', { name: '删除', exact: true }).click()
    await waitFor(
      async () => !(await page.getByText('e2e_milvus').first().isVisible().catch(() => false)),
      { label: 'milvus 配置删除' },
    )

    // Embedding：新建 + 测试连接 + 删除
    await page.getByRole('button', { name: '向量模型', exact: false }).first().click()
    await page.getByRole('button', { name: '＋ 新建配置' }).click()
    dialog = page.locator('.config-create-dialog')
    await expect(dialog).toBeVisible()
    const field = (label: string) => dialog.locator('.arco-form-item', { hasText: label }).locator('input').first()
    await field('配置名称').fill('e2e_embedding')
    await field('Base URL').fill('https://open.bigmodel.cn/api/paas/v4')
    await field('模型').fill('embedding-3')
    await field('API Key').fill(glmKey)
    // 模型类配置走验证门禁：先验证连接，保存按钮解锁后提交
    await dialog.getByRole('button', { name: '验证连接' }).click()
    await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeVisible({ timeout: 90_000 })
    await dialog.getByRole('button', { name: '保存', exact: true }).click()
    await waitFor(
      async () => (await page.getByText('e2e_embedding').first().isVisible().catch(() => false)),
      { label: 'embedding 配置入列' },
    )
    await page.getByText('e2e_embedding').first().click()
    drawer = page.locator('.detail-drawer')
    await expect(drawer).toBeVisible({ timeout: 15_000 })
    await expect(drawer.getByText('e2e_embedding').first()).toBeVisible()
    await drawer.getByRole('button', { name: '测试连接' }).click()
    await waitFor(
      async () => (await page.getByText(/连接测试成功，延迟/).first().isVisible().catch(() => false)),
      { timeout: 90_000, label: 'embedding 测试连接' },
    )
    await drawer.getByRole('button', { name: '删除', exact: true }).click()
    await waitFor(
      async () => !(await page.getByText('e2e_embedding').first().isVisible().catch(() => false)),
      { label: 'embedding 配置删除' },
    )
  })
})
