<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  browseEntities,
  canReindexEntityIndex,
  entitySearchErrorMessage,
  getEntityIndexStatus,
  getEntitySearchTypes,
  reindexEntities,
  searchEntities,
  type EntityIndexStatus,
  type EntityListResult,
  type EntityTypeCount,
} from '../../api/entitySearch'
import { listGraphSpaces } from '../../api/graphSearch'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import { useToast } from '../../composables/use-toast'

const { showToast } = useToast()

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const PROPERTY_CHIP_LIMIT = 6

const keyword = ref('')
const appliedKeyword = ref('')
const entityType = ref('')
const space = ref('')
const spaces = ref<string[]>([])
const pageSize = ref(10)
const page = ref(1)

const types = ref<EntityTypeCount[]>([])
const status = ref<EntityIndexStatus | null>(null)
const result = ref<EntityListResult | null>(null)
const loading = ref(false)
const reindexing = ref(false)
const expandedRows = ref<Set<string>>(new Set())

// 响应式跟随 auth store：profile 在路由守卫/启动钩子异步加载后才到位，
// setup 时一次性调用会把 admin 恒判为 false（免登录部署下按钮永不出现）
const isAdmin = computed(() => canReindexEntityIndex())
const items = computed(() => result.value?.items ?? [])
const isBrowseMode = computed(() => !appliedKeyword.value)
const totalPages = computed(() => {
  if (!result.value) return 1
  const total =
    result.value.total ?? (result.value.returned ?? result.value.items.length) + (page.value - 1) * pageSize.value
  return Math.max(Math.ceil(total / pageSize.value), 1)
})
const modeLabel = computed(() => {
  const mode = result.value?.mode
  if (mode === 'browse') return '浏览（图直查）'
  if (mode === 'hybrid') return '混合（语义+关键词）'
  if (mode === 'dense') return '语义'
  return '关键词'
})

const statusLine = computed(() => {
  const s = status.value
  if (!s || !s.indexed) return '实体索引尚未构建（浏览模式不受影响，关键词检索需先重建索引）'
  const updatedAt = s.updatedAt ? s.updatedAt.replace('T', ' ').slice(0, 19) : '—'
  return `已索引 ${s.entityCount} 个实体 · ${s.types.length} 种类型 · 空间 ${s.graphSpace ?? '—'} · 更新于 ${updatedAt}`
})

async function loadSpaces() {
  try {
    // http 拦截器已解包为 ApiResponse（运行时），axios 泛型声明与运行时不同，故做一次窄化断言
    const payload = (await listGraphSpaces()) as unknown as { data?: { spaces?: string[] } }
    spaces.value = payload.data?.spaces ?? []
  } catch {
    // 空间列表加载失败不阻塞页面（仍可用默认空间）
  }
}

async function loadIndexInfo() {
  try {
    const [typeItems, statusData] = await Promise.all([
      getEntitySearchTypes(space.value || null),
      getEntityIndexStatus(space.value || null),
    ])
    types.value = typeItems
    status.value = statusData
  } catch (error) {
    showToast(entitySearchErrorMessage(error), 'warning')
  }
}

function resetPagingAndSearch() {
  page.value = 1
  void doSearch()
}

async function doSearch() {
  if (loading.value) return
  const trimmed = keyword.value.trim()
  appliedKeyword.value = trimmed
  loading.value = true
  try {
    if (trimmed) {
      result.value = await searchEntities({
        keyword: trimmed,
        space: space.value || null,
        entityType: entityType.value || null,
        limit: pageSize.value,
        offset: (page.value - 1) * pageSize.value,
      })
    } else {
      // 空关键词：浏览模式——图空间直查分页（按 id 顺序取前几个）
      result.value = await browseEntities({
        space: space.value || null,
        entityType: entityType.value || null,
        limit: pageSize.value,
        offset: (page.value - 1) * pageSize.value,
      })
    }
  } catch (error) {
    showToast(entitySearchErrorMessage(error), 'warning')
  } finally {
    loading.value = false
  }
}

function onEntityTypeChange() {
  resetPagingAndSearch()
}

function onSpaceChange() {
  page.value = 1
  appliedKeyword.value = ''
  void loadIndexInfo().then(() => doSearch())
}

function onPageSizeChange() {
  page.value = 1
  void doSearch()
}

function goPage(next: number) {
  if (next < 1 || next > totalPages.value || loading.value) return
  page.value = next
  void doSearch()
}

async function reindex() {
  if (reindexing.value) return
  reindexing.value = true
  try {
    const data = await reindexEntities({ space: space.value || undefined })
    showToast(`索引重建完成：${data.entityCount} 个实体，耗时 ${data.durationSeconds}s`, 'success')
    await loadIndexInfo()
    if (appliedKeyword.value) await doSearch()
  } catch (error) {
    showToast(entitySearchErrorMessage(error), 'warning')
  } finally {
    reindexing.value = false
  }
}

function propertyEntries(item: EntityListResult['items'][number]): Array<[string, string]> {
  return Object.entries(item.properties || {})
}

function propertyChips(item: EntityListResult['items'][number]): string[] {
  return propertyEntries(item)
    .slice(0, PROPERTY_CHIP_LIMIT)
    .map(([key, value]) => `${key}: ${value}`)
}

function propertyOverflow(item: EntityListResult['items'][number]): number {
  return Math.max(propertyEntries(item).length - PROPERTY_CHIP_LIMIT, 0)
}

function toggleRowDetail(vid: string) {
  const next = new Set(expandedRows.value)
  if (next.has(vid)) {
    next.delete(vid)
  } else {
    next.add(vid)
  }
  expandedRows.value = next
}

onMounted(() => {
  void loadSpaces()
  void loadIndexInfo().then(() => doSearch())
})
</script>

<template>
  <main class="entity-page">
    <section class="entity-shell entity-toolbar-shell" aria-label="实体检索">
      <div class="entity-toolbar">
        <div class="entity-toolbar__title">
          <strong>实体列表</strong>
          <span>{{ statusLine }}</span>
        </div>
        <div class="entity-toolbar__actions">
          <a-select
            v-model="space"
            class="entity-toolbar__space"
            placeholder="默认图空间"
            allow-clear
            popup-container=".entity-toolbar-shell"
            @change="onSpaceChange"
          >
            <a-option v-for="item in spaces" :key="item" :value="item">{{ item }}</a-option>
          </a-select>
          <button
            v-if="isAdmin"
            class="entity-btn"
            type="button"
            :disabled="reindexing"
            :title="'按当前图空间全量重建 Milvus 混合索引（语义 + BM25 关键词）'"
            @click="reindex"
          >
            {{ reindexing ? '索引重建中...' : '重建索引' }}
          </button>
        </div>
      </div>
      <div class="entity-filters">
        <label class="entity-filters__search">
          <span aria-hidden="true">⌕</span>
          <input aria-label="输入实体名称 / 属性关键词（语义 + 关键词混合检索）；留空则分页浏览全部实体"
            v-model="keyword"
            :maxlength="SEARCH_KEYWORD_MAX_LENGTH"
            placeholder="输入实体名称 / 属性关键词（语义 + 关键词混合检索）；留空则分页浏览全部实体"
            @keyup.enter="resetPagingAndSearch"
          />
        </label>
        <button class="entity-btn entity-btn--primary" type="button" :disabled="loading" @click="resetPagingAndSearch">
          {{ loading ? '检索中...' : '搜索' }}
        </button>
        <a-select
          v-model="entityType"
          class="entity-filters__type"
          placeholder="实体类型"
          allow-clear
          popup-container=".entity-toolbar-shell"
          @change="onEntityTypeChange"
        >
          <a-option v-for="t in types" :key="t.name" :value="t.name">
            {{ t.name }}（{{ t.count }}）
          </a-option>
        </a-select>
      </div>
      <p v-if="status && !status.bm25Ready && status.indexed" class="entity-hint">
        BM25 关键词条目缺失（仅语义检索可用），重建索引可恢复混合检索能力。
      </p>
    </section>

    <section class="entity-shell entity-result-shell" aria-label="实体列表">
      <div v-if="loading" class="entity-empty">加载中...</div>
      <div v-else-if="!items.length" class="entity-empty">
        <template v-if="isBrowseMode">
          <template v-if="entityType">类型 {{ entityType }} 下暂无实体</template>
          <template v-else>当前图空间暂无实体</template>
        </template>
        <template v-else>
          未找到匹配「{{ appliedKeyword }}」的实体{{ entityType ? `（类型 ${entityType}）` : '' }}
        </template>
      </div>
      <template v-else>
        <div class="entity-table-wrap">
          <table>
            <thead>
              <tr>
                <th>实体名称</th>
                <th>ID</th>
                <th>实体类型</th>
                <th>公共属性</th>
                <th>{{ isBrowseMode ? '' : '相关度' }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="item in items" :key="item.vid">
                <tr>
                  <td><b>{{ item.name || '（未命名）' }}</b></td>
                  <td><code>{{ item.entityId || item.vid }}</code></td>
                  <td><span class="entity-type-chip">{{ item.entityType }}</span></td>
                  <td class="entity-props-cell">
                    <div class="entity-props">
                      <span v-for="chip in propertyChips(item)" :key="chip" class="entity-props__chip" :title="chip">{{ chip }}</span>
                      <button
                        v-if="propertyOverflow(item)"
                        type="button"
                        class="entity-props__more"
                        title="展开全部属性"
                        @click="toggleRowDetail(item.vid)"
                      >
                        +{{ propertyOverflow(item) }}
                      </button>
                      <span v-if="!propertyEntries(item).length" class="entity-props__empty">—</span>
                    </div>
                  </td>
                  <td>{{ item.score ?? '' }}</td>
                </tr>
                <tr v-if="expandedRows.has(item.vid)" class="entity-detail-row">
                  <td :colspan="5">
                    <div class="entity-detail">
                      <span v-for="[key, value] in propertyEntries(item)" :key="key" class="entity-detail__item">
                        <code>{{ key }}</code><em>{{ value }}</em>
                      </span>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <footer class="entity-pagination">
          <div class="entity-pagination__size">
            <span>每页</span>
            <a-select
              :model-value="pageSize"
              class="entity-pagination__size-select"
              popup-container=".entity-result-shell"
              @change="(value: number | string | boolean | Record<string, unknown> | Array<number | string | boolean | Record<string, unknown>> | undefined) => { pageSize = Number(value) || 10; onPageSizeChange() }"
            >
              <a-option v-for="size in PAGE_SIZE_OPTIONS" :key="size" :value="size">{{ size }}</a-option>
            </a-select>
            <span>条</span>
          </div>
          <span class="entity-pagination__info">
            第 {{ page }} / {{ totalPages }} 页 · 检索模式：{{ modeLabel }}
            <template v-if="isBrowseMode && result?.total != null"> · 共 {{ result.total }} 个实体</template>
          </span>
          <div class="entity-pagination__actions">
            <button type="button" :disabled="page <= 1 || loading" @click="goPage(page - 1)">上一页</button>
            <button type="button" :disabled="page >= totalPages || loading" @click="goPage(page + 1)">下一页</button>
          </div>
        </footer>
      </template>
    </section>
  </main>
</template>

<style scoped>
.entity-page{display:flex;height:100%;min-height:0;overflow:hidden;flex-direction:column;padding:2px 2px 18px;color:#1d2129}
.entity-shell{display:flex;flex:1;min-height:0;flex-direction:column;border:1px solid #e5e6eb;border-radius:6px;background:#fff}
.entity-toolbar-shell{flex:0 0 auto}
.entity-result-shell{margin-top:12px}
.entity-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 16px;border-bottom:1px solid #f2f3f5}
.entity-toolbar__title{display:flex;flex-direction:column;gap:2px}
.entity-toolbar__title strong{font-size:16px;line-height:24px;font-weight:600}
.entity-toolbar__title span{font-size:12px;line-height:20px;color:#86909c}
.entity-toolbar__actions{display:flex;align-items:center;gap:10px}
.entity-toolbar__space{width:150px;flex:0 0 auto}
.entity-toolbar__space :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:13px;line-height:22px}
.entity-btn{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;cursor:pointer;white-space:nowrap}
.entity-btn:hover{border-color:#165dff;color:#165dff}
.entity-btn--primary{height:40px;padding:0 28px;border-color:#165dff;background:#165dff;color:#fff;font-size:15px}
.entity-btn--primary:hover{background:#0e4ed8;color:#fff}
.entity-btn:disabled{opacity:.6;cursor:not-allowed}
.entity-filters{display:flex;align-items:center;gap:12px;padding:12px 16px}
.entity-filters__search{display:flex;align-items:center;gap:10px;flex:1;min-width:280px;height:40px;padding:0 16px;border:1.5px solid #c9dcf8;border-radius:6px;background:#f7faff;color:#165dff;transition:border-color .16s ease,background .16s ease,box-shadow .16s ease}
.entity-filters__search:focus-within{border-color:#165dff;background:#fff;box-shadow:0 0 0 3px rgba(22,93,255,.12)}
.entity-filters__search span{font-size:17px;line-height:1}
.entity-filters__search input{flex:1;min-width:0;border:0;outline:0;font-size:15px;line-height:24px;color:#1d2129;background:transparent}
.entity-filters__search input::placeholder{color:#a9b7cf}
.entity-filters__type{width:190px;flex:0 0 auto}
.entity-filters__type :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:13px;line-height:22px}
.entity-filters__type :deep(.arco-select-view-single){height:32px;min-height:32px}
.entity-hint{margin:0;padding:8px 16px;border-top:1px dashed #ffe4ba;background:#fff7e8;color:#b54708;font-size:12px;line-height:20px}
.entity-empty{flex:1;display:grid;place-items:center;padding:40px 16px;color:#86909c;font-size:13px;line-height:22px;text-align:center}
.entity-table-wrap{flex:1;min-height:0;overflow:auto}
.entity-table-wrap table{width:100%;border-collapse:collapse;font-size:14px;line-height:22px}
.entity-table-wrap th{position:sticky;top:0;z-index:1;background:#f7f8fa;color:#1d2129;font-weight:500;text-align:left}
.entity-table-wrap th,.entity-table-wrap td{padding:10px 16px;border-bottom:1px solid #f2f3f5;vertical-align:middle}
.entity-table-wrap td code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:12px;word-break:break-all}
.entity-type-chip{display:inline-flex;padding:1px 10px;border-radius:999px;background:#eef5ff;color:#165dff;font-size:12px;line-height:18px;white-space:nowrap}
.entity-props-cell{max-width:420px}
.entity-props{display:flex;flex-wrap:wrap;gap:4px}
.entity-props__chip{display:inline-flex;max-width:180px;overflow:hidden;padding:1px 8px;border:1px solid #d6e2f5;border-radius:999px;background:#f4f8ff;color:#3a5686;font-size:11px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}
.entity-props__more{padding:1px 8px;border:1px solid #bcd4f7;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:11px;line-height:18px;cursor:pointer}
.entity-props__more:hover{background:#dcebff}
.entity-props__empty{color:#c9cdd4;font-size:12px}
.entity-detail-row>td{background:#f9fbff}
.entity-detail{display:flex;flex-wrap:wrap;gap:8px 18px}
.entity-detail__item{display:inline-flex;align-items:center;gap:6px;font-size:12px;line-height:20px;color:#4e5969;white-space:nowrap}
.entity-detail__item code{padding:1px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px}
.entity-detail__item em{color:#86909c;font-style:normal;font-size:11px;word-break:break-all}
.entity-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;border-top:1px solid #f2f3f5}
.entity-pagination__size{display:flex;align-items:center;gap:6px;color:#86909c;font-size:12px;line-height:20px}
.entity-pagination__size-select{width:72px}
.entity-pagination__size-select :deep(.arco-select-view){box-sizing:border-box;width:100%;height:28px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:12px;line-height:20px}
.entity-pagination__info{color:#86909c;font-size:12px;line-height:20px}
.entity-pagination__actions{display:flex;gap:8px}
.entity-pagination__actions button{height:28px;padding:0 12px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:12px;cursor:pointer}
.entity-pagination__actions button:hover:not(:disabled){border-color:#165dff;color:#165dff}
.entity-pagination__actions button:disabled{opacity:.5;cursor:not-allowed}
</style>
