<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { getOperationLogs, type OperationLogPage } from '../../api/auth'
import { SEARCH_KEYWORD_MAX_LENGTH, searchKeywordError } from '../../utils/searchInput'

const loading = ref(false)
const feedback = ref('')
const logs = ref<OperationLogPage>({ items: [], total: 0, page: 1, pageSize: 20, dataMode: 'live' })
const filters = reactive({ keyword: '', category: '', result: '' })

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function deviceLabel(value: string) {
  if (!value) return '未知设备'
  if (value.includes('Local development')) return '本地开发环境'
  if (value.includes('Windows')) return 'Windows 浏览器'
  if (value.includes('Macintosh')) return 'macOS 浏览器'
  if (value.includes('Android')) return 'Android 设备'
  if (value.includes('iPhone')) return 'iPhone'
  return value.length > 34 ? `${value.slice(0, 34)}…` : value
}

async function loadLogs(page = 1) {
  const keywordError = searchKeywordError(filters.keyword)
  if (keywordError) {
    feedback.value = keywordError
    return
  }
  loading.value = true
  feedback.value = ''
  try {
    logs.value = await getOperationLogs({
      page,
      pageSize: logs.value.pageSize,
      keyword: filters.keyword || undefined,
      category: filters.category || undefined,
      result: filters.result || undefined,
    })
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '操作记录加载失败。'
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.category = ''
  filters.result = ''
  void loadLogs(1)
}

onMounted(() => loadLogs())
</script>

<template>
  <div class="logs-page">
    <header class="logs-hero">
      <div><span>OPERATION AUDIT</span><p>查看当前账号在本平台的登录、会话刷新和安全操作。</p></div>
      <b :class="{ demo: logs.dataMode === 'mock' }">{{ logs.dataMode === 'mock' ? '演示记录' : 'Redis 审计记录' }}</b>
    </header>

    <section class="log-card">
      <header class="log-filter">
        <input aria-label="搜索操作、详情或 IP" v-model.trim="filters.keyword" type="search" :maxlength="SEARCH_KEYWORD_MAX_LENGTH" placeholder="搜索操作、详情或 IP" @keyup.enter="loadLogs(1)" />
        <select v-model="filters.category" aria-label="操作类型"><option value="">全部类型</option><option value="登录">登录</option><option value="安全">安全</option><option value="账号">账号</option></select>
        <select v-model="filters.result" aria-label="操作结果"><option value="">全部结果</option><option value="成功">成功</option><option value="失败">失败</option></select>
        <button type="button" @click="loadLogs(1)">查询</button><button class="secondary" type="button" @click="resetFilters">重置</button>
      </header>

      <p v-if="feedback" class="feedback is-error">{{ feedback }}</p>
      <p v-else-if="loading" class="feedback">正在读取操作记录…</p>

      <div class="table-wrap">
        <table>
          <thead><tr><th>操作时间</th><th>操作</th><th>类型</th><th>IP 地址</th><th>设备</th><th>结果</th><th>详情</th></tr></thead>
          <tbody>
            <tr v-for="item in logs.items" :key="item.id">
              <td>{{ formatTime(item.occurredAt) }}</td><td><strong>{{ item.action }}</strong></td><td><span class="category">{{ item.category }}</span></td><td><code>{{ item.ipAddress || '--' }}</code></td><td :title="item.userAgent">{{ deviceLabel(item.userAgent) }}</td><td><b :class="{ failed: item.result !== '成功' }">{{ item.result }}</b></td><td>{{ item.detail || '--' }}</td>
            </tr>
            <tr v-if="!loading && logs.items.length === 0"><td class="empty" colspan="7">当前筛选条件下没有操作记录</td></tr>
          </tbody>
        </table>
      </div>

      <footer><span>共 {{ logs.total }} 条记录</span><nav><button type="button" :disabled="logs.page <= 1 || loading" @click="loadLogs(logs.page - 1)">上一页</button><em>第 {{ logs.page }} 页</em><button type="button" :disabled="logs.page * logs.pageSize >= logs.total || loading" @click="loadLogs(logs.page + 1)">下一页</button></nav></footer>
    </section>
  </div>
</template>

<style scoped>
.logs-page { height:100%;padding:6px;overflow:auto;color:#243854; }.logs-hero { display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:24px 26px;border:1px solid #b9d5f7;border-radius:10px;background:linear-gradient(120deg,#edf5ff,#fff 56%,#eaf8ff);box-shadow:0 12px 28px rgba(48,105,194,.1); }.logs-hero span { color:#165dff;font-size:10px;font-weight:700;letter-spacing:.16em; }.logs-hero h1 { margin:7px 0 5px;font-size:25px; }.logs-hero p { margin:0;color:#71819a;font-size:12px; }.logs-hero>b { padding:6px 10px;border-radius:999px;background:#e8f8ef;color:#067647;font-size:9px; }.logs-hero>b.demo { background:#fff3d8;color:#b54708; }
.log-card { margin-top:14px;overflow:hidden;border:1px solid #c9ddf6;border-radius:9px;background:#fff;box-shadow:0 8px 22px rgba(48,105,194,.07); }.log-filter { display:flex;gap:8px;padding:13px;border-bottom:1px solid #e2ebf6;background:#fbfdff; }.log-filter input { min-width:230px;flex:1; }.log-filter input,.log-filter select { height:34px;padding:0 10px;border:1px solid #cbdaf0;border-radius:6px;background:#fff;color:#344766;font-size:10px;outline:none; }.log-filter input:focus,.log-filter select:focus { border-color:#75a7ef;box-shadow:0 0 0 3px #eaf2ff; }.log-filter button { height:34px;padding:0 16px;border:1px solid #165dff;border-radius:6px;background:#165dff;color:#fff;font-size:10px;cursor:pointer; }.log-filter button.secondary { border-color:#cbdaf0;background:#fff;color:#526783; }
.feedback { margin:0;padding:12px 14px;border-bottom:1px solid #e4edf8;background:#edf5ff;color:#175cd3;font-size:10px; }.feedback.is-error { background:#fff0ee;color:#b42318; }.table-wrap { overflow:auto; }table { width:100%;border-collapse:collapse;white-space:nowrap; }th { padding:11px 13px;background:#f5f8fc;color:#67758b;font-size:9px;font-weight:600;text-align:left; }td { max-width:240px;padding:13px;border-top:1px solid #edf2f8;color:#526783;font-size:10px;overflow:hidden;text-overflow:ellipsis; }td strong { color:#263853;font-size:11px; }.category { padding:3px 7px;border-radius:999px;background:#eaf2ff;color:#175cd3; }td code { color:#526783;font-size:9px; }td>b { color:#067647;font-size:9px; }td>b.failed { color:#b42318; }.empty { height:150px;color:#98a2b3;text-align:center; }
.log-card>footer { display:flex;align-items:center;justify-content:space-between;padding:11px 13px;border-top:1px solid #e2ebf6;background:#fbfdff;color:#7a899f;font-size:9px; }.log-card footer nav { display:flex;align-items:center;gap:8px; }.log-card footer button { height:28px;padding:0 10px;border:1px solid #cbdaf0;border-radius:5px;background:#fff;color:#526783;font-size:9px;cursor:pointer; }.log-card footer button:disabled { cursor:not-allowed;opacity:.45; }.log-card footer em { font-style:normal; }
@media (max-width:900px) { .logs-hero { align-items:flex-start;flex-direction:column; }.log-filter { flex-wrap:wrap; }.log-filter input { min-width:100%; }.log-filter select { flex:1; } }
</style>
