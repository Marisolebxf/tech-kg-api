<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Popover as APopover } from '@arco-design/web-vue'
import { IconSearch } from '@arco-design/web-vue/es/icon'

import {
  browseEntities,
  countEntityList,
  entitySearchErrorMessage,
  getEntitySearchTypes,
  searchEntityList,
  type EntityListResult,
  type EntityTypeCount,
} from '../../api/entitySearch'
import { currentGraphSpace } from '../../api/currentGraphSpace'
import ListPagination from '../../components/list-pagination.vue'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import { useToast } from '../../composables/use-toast'
import { useGraphSpaceStore } from '../../stores/graphSpace'

const tableScrollActive = ref(false)
let tableScrollTimer: ReturnType<typeof setTimeout> | undefined
function handleTableScroll() {
  tableScrollActive.value = true
  clearTimeout(tableScrollTimer)
  tableScrollTimer = setTimeout(() => { tableScrollActive.value = false }, 700)
}
onUnmounted(() => { clearTimeout(tableScrollTimer) })

const { showToast } = useToast()

const PROPERTY_CHIP_LIMIT = 4

const keyword = ref('')
const appliedKeyword = ref('')
const entityType = ref('')
// 图空间跟随平台总览页的全局选择器（本页不再有空间筛选控件）
const space = computed(() => currentGraphSpace())
const graphSpaceStore = useGraphSpaceStore()
const pageSize = ref(10)
const page = ref(1)

const types = ref<EntityTypeCount[]>([])
const result = ref<EntityListResult | null>(null)
const loading = ref(false)
const searchError = ref('')
let searchVersion = 0
const PAGE_CACHE_TTL = 60_000
const pageCache = new Map<string, { expires: number; result: EntityListResult }>()
const pendingPages = new Map<string, Promise<EntityListResult>>()
let cacheVersion = 0
let countController: AbortController | undefined
let countScope = ''
const knownTotals = new Map<string, number>()

function stopCount() {
  countController?.abort()
  countController = undefined
  countScope = ''
}

function totalKey(request: PageRequest, data: EntityListResult) {
  return JSON.stringify([request.keyword, request.space, request.entityType, data.generation, data.matchMode])
}

function applyTotal(key: string, total: number) {
  for (const cached of pageCache.values()) {
    const data = cached.result
    if (JSON.stringify([data.keyword, data.graphSpace, data.entityType, data.generation, data.matchMode]) === key) {
      data.total = total
      data.totalStatus = 'ready'
    }
  }
  if (result.value && totalKey({ keyword: appliedKeyword.value, space: space.value || null,
    entityType: entityType.value || null, limit: pageSize.value, offset: 0 }, result.value) === key) {
    result.value = { ...result.value, total, totalStatus: 'ready' }
  }
}

function startTotal(request: PageRequest, data: EntityListResult) {
  if (!request.keyword || data.total != null) return
  const key = totalKey(request, data)
  const known = knownTotals.get(key)
  if (known != null) { applyTotal(key, known); return }
  if (countScope === key && countController) return
  stopCount()
  countScope = key
  const controller = new AbortController()
  countController = controller
  void countEntityList({ keyword: request.keyword, space: request.space, entityType: request.entityType,
    generation: data.generation, matchMode: data.matchMode }, controller.signal).then(count => {
    if (controller.signal.aborted || key !== countScope) return
    if (knownTotals.size >= 20) knownTotals.delete(knownTotals.keys().next().value!)
    knownTotals.set(key, count.total)
    applyTotal(key, count.total)
  }).catch(() => {
    if (!controller.signal.aborted && key === countScope && result.value) {
      result.value = { ...result.value, totalStatus: 'error' }
    }
  }).finally(() => {
    if (countController === controller) countController = undefined
  })
}

function retryTotal() {
  // Refresh the page too: the index revision may have changed while counting.
  clearPageCache()
  void doSearch()
}

type PageRequest = { keyword: string; space: string | null; entityType: string | null; limit: number; offset: number }

function clearPageCache() {
  ++cacheVersion
  stopCount()
  knownTotals.clear()
  pageCache.clear()
  pendingPages.clear()
}

function loadPage(request: PageRequest): Promise<EntityListResult> {
  const key = JSON.stringify(request)
  const cached = pageCache.get(key)
  if (cached && cached.expires > Date.now()) return Promise.resolve(cached.result)
  const pending = pendingPages.get(key)
  if (pending) return pending
  const version = cacheVersion
  const { keyword: text, ...scope } = request
  const promise = (text ? searchEntityList(request) : browseEntities(scope)).then(data => {
    if (version === cacheVersion) {
      if (pageCache.size >= 20) pageCache.delete(pageCache.keys().next().value!)
      pageCache.set(key, { expires: Date.now() + PAGE_CACHE_TTL, result: data })
    }
    return data
  }).finally(() => {
    if (pendingPages.get(key) === promise) pendingPages.delete(key)
  })
  pendingPages.set(key, promise)
  return promise
}

onUnmounted(() => { ++searchVersion; clearPageCache() })

const items = computed(() => result.value?.items ?? [])
const isBrowseMode = computed(() => !appliedKeyword.value)
const paginationTotal = computed(() => {
  if (!result.value) return 0
  return result.value.total
    ?? (result.value.returned ?? result.value.items.length) + (page.value - 1) * pageSize.value
      + (result.value.hasMore ? 1 : 0)
})
const totalPages = computed(() => {
  return Math.max(Math.ceil(paginationTotal.value / pageSize.value), 1)
})

async function loadEntityTypes() {
  const selectedSpace = space.value
  try {
    const typeItems = await getEntitySearchTypes(selectedSpace || null)
    if (selectedSpace !== space.value) return
    types.value = typeItems
    if (entityType.value && !typeItems.some(type => type.name === entityType.value)) {
      entityType.value = ''
    }
  } catch (error) {
    showToast(entitySearchErrorMessage(error), 'error')
  }
}

function resetPagingAndSearch() {
  clearPageCache()
  appliedKeyword.value = keyword.value.trim()
  page.value = 1
  void doSearch()
}

async function doSearch() {
  const version = ++searchVersion
  const request: PageRequest = {
    keyword: appliedKeyword.value,
    space: space.value || null,
    entityType: entityType.value || null,
    limit: pageSize.value,
    offset: (page.value - 1) * pageSize.value,
  }
  loading.value = true
  searchError.value = ''
  try {
    const nextResult = await loadPage(request)
    if (version === searchVersion) {
      result.value = nextResult
      startTotal(request, nextResult)
      // 仅预取下一页；与用户翻页共享进行中的请求，失败不影响当前页。
      if (nextResult.total != null && request.offset + request.limit < nextResult.total) {
        void loadPage({ ...request, offset: request.offset + request.limit }).catch(() => {})
      }
    }
  } catch (error) {
    if (version === searchVersion) {
      result.value = null
      searchError.value = entitySearchErrorMessage(error)
    }
  } finally {
    if (version === searchVersion) loading.value = false
  }
}

function onEntityTypeChange() {
  resetPagingAndSearch()
}

function onPageSizeChange(next: number) {
  pageSize.value = next
  page.value = 1
  void doSearch()
}

function goPage(next: number) {
  if (next < 1 || next > totalPages.value || loading.value) return
  page.value = next
  void doSearch()
}

function propertyEntries(item: EntityListResult['items'][number]): Array<[string, string]> {
  return Object.entries(item.properties || {})
}

function visiblePropertyEntries(item: EntityListResult['items'][number]): Array<[string, string]> {
  return propertyEntries(item).slice(0, PROPERTY_CHIP_LIMIT)
}

function hiddenPropertyEntries(item: EntityListResult['items'][number]): Array<[string, string]> {
  return propertyEntries(item).slice(PROPERTY_CHIP_LIMIT)
}

function propertyOverflow(item: EntityListResult['items'][number]): number {
  return hiddenPropertyEntries(item).length
}

onMounted(() => {
  void loadEntityTypes()
  void doSearch()
})

// 全局图空间切换：重置分页与关键词后按新空间重查
watch(
  () => graphSpaceStore.current,
  () => {
    clearPageCache()
    ++searchVersion
    result.value = null
    loading.value = true
    page.value = 1
    keyword.value = ''
    appliedKeyword.value = ''
    const selectedSpace = space.value
    void loadEntityTypes().then(() => {
      if (selectedSpace === space.value) void doSearch()
    })
  },
)
</script>

<template>
  <main class="entity-page">
    <section class="entity-toolbar-shell" aria-label="实体检索">
      <div class="entity-toolbar">
        <div class="entity-toolbar__left">
          <a-select
            id="entity-filter-type"
            v-model="entityType"
            class="entity-filter-select"
            placeholder="全部"
            aria-label="实体类型"
            allow-clear
            :scrollbar="false"
            @change="onEntityTypeChange"
          >
            <a-option v-for="t in types" :key="t.name" :value="t.name" :label="t.name">
              <span class="entity-type-option" :title="t.name">{{ t.name }}</span>
            </a-option>
          </a-select>
        </div>
        <div class="entity-toolbar__right">
          <a-input
            id="entity-filter-name"
            v-model="keyword"
            class="entity-search-input"
            :max-length="SEARCH_KEYWORD_MAX_LENGTH"
            aria-label="查询当前图空间的实体名称、ID或属性关键词；留空则分页浏览全部实体"
            placeholder="输入实体名称 / 属性关键词"
            @keyup.enter="resetPagingAndSearch"
          >
            <template #prefix><IconSearch /></template>
          </a-input>
          <button class="kg-button" type="button" :disabled="loading" @click="resetPagingAndSearch">
            {{ loading ? '查询中...' : '查询' }}
          </button>
        </div>
      </div>
    </section>

    <section class="entity-shell entity-result-shell" aria-label="实体列表">
      <div v-if="loading && !items.length" class="entity-empty">加载中...</div>
      <div v-else-if="searchError" class="entity-empty" role="alert">
        <span>{{ searchError }}</span>
        <button class="kg-button" type="button" @click="doSearch">重试</button>
      </div>
      <div v-else-if="!items.length" class="entity-empty">
        <template v-if="page > 1">当前页暂无实体，请返回上一页或重新查询</template>
        <template v-else>
        <template v-if="isBrowseMode">
          <template v-if="entityType">类型 {{ entityType }} 下暂无实体</template>
          <template v-else>当前图空间暂无实体</template>
        </template>
        <template v-else>
          未找到匹配「{{ appliedKeyword }}」的实体{{ entityType ? `（类型 ${entityType}）` : '' }}
        </template>
        </template>
      </div>
      <template v-else>
        <div class="entity-table-wrap" :class="{ 'entity-scroll--active': tableScrollActive }" :aria-busy="loading" @scroll.passive="handleTableScroll">
          <div v-if="loading" class="entity-loading" role="status">加载中...</div>
          <table>
            <thead>
              <tr>
                <th>实体名称</th>
                <th>ID</th>
                <th>实体类型</th>
                <th>公共属性</th>
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
                      <span
                        v-for="[key, value] in visiblePropertyEntries(item)"
                        :key="key"
                        class="entity-props__chip"
                        :title="`${key}: ${value}`"
                      >
                        <b>{{ key }}</b>
                        <em>{{ value }}</em>
                      </span>
                      <APopover
                        v-if="propertyOverflow(item)"
                        :trigger="['hover', 'click']"
                        position="bl"
                        content-class="entity-property-popover"
                      >
                        <button
                          type="button"
                          class="entity-props__more"
                          :aria-label="`查看其余 ${propertyOverflow(item)} 个公共属性`"
                        >
                          +{{ propertyOverflow(item) }}
                        </button>
                        <template #content>
                          <div class="entity-property-popover__content">
                            <p class="entity-property-popover__title">其他公共属性（{{ propertyOverflow(item) }}）</p>
                            <div class="entity-property-popover__grid">
                              <span
                                v-for="[key, value] in hiddenPropertyEntries(item)"
                                :key="key"
                                class="entity-property-popover__item"
                                :title="`${key}: ${value}`"
                              >
                                <b>{{ key }}</b>
                                <em>{{ value }}</em>
                              </span>
                            </div>
                          </div>
                        </template>
                      </APopover>
                      <span v-if="!propertyEntries(item).length" class="entity-props__empty">—</span>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </template>
      <ListPagination
        v-if="result && (items.length || page > 1 || result.totalStatus === 'pending' || result.totalStatus === 'error')"
        :total="paginationTotal"
        :page="page"
        :page-size="pageSize"
        :disabled="loading"
        :show-jumper="false"
        :size-at-end="true"
        :sliding-pages="true"
        @change="goPage"
        @change-size="onPageSizeChange"
      >
        <template #summary>
          <span class="entity-pagination__info">
            <template v-if="result.totalStatus === 'pending'">统计中</template>
            <template v-else-if="result.totalStatus === 'error'">
              统计失败 <button class="kg-button" type="button" @click="retryTotal">重新统计</button>
            </template>
            <template v-else>共 {{ result.total ?? paginationTotal }} 个实体</template>
          </span>
        </template>
      </ListPagination>
    </section>
  </main>
</template>

<style scoped>
.entity-page{display:flex;height:100%;min-height:0;overflow:hidden;flex-direction:column;color:#1d2129}
.entity-shell{display:flex;flex:1;min-height:0;flex-direction:column;border:1px solid #e5e6eb;border-radius:6px;background:#fff}
.entity-toolbar-shell{flex:0 0 auto}
.entity-result-shell{margin-top:16px}
.entity-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px 16px}
.entity-toolbar__left,.entity-toolbar__right{display:flex;min-width:0;align-items:center;gap:8px}
.entity-toolbar__left{flex-wrap:wrap}
.entity-toolbar button{flex-shrink:0;white-space:nowrap}
.entity-toolbar__right{min-width:0;flex:1 1 320px;justify-content:flex-end}
.entity-empty{flex:1;display:grid;place-items:center;padding:40px 16px;color:#86909c;font-size:13px;line-height:22px;text-align:center}
.entity-table-wrap{flex:1;min-height:0;overflow:auto;scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:transparent transparent}
.entity-loading{position:sticky;top:0;z-index:2;padding:6px 16px;background:#edf4ff;color:#165dff;font-size:12px;line-height:20px}
.entity-table-wrap:hover,.entity-table-wrap.entity-scroll--active{scrollbar-color:rgba(78,89,105,.55) transparent}
.entity-table-wrap::-webkit-scrollbar{width:8px;height:8px}
.entity-table-wrap::-webkit-scrollbar-track{background:transparent}
.entity-table-wrap::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background-color:transparent;background-clip:padding-box}
.entity-table-wrap:hover::-webkit-scrollbar-thumb,.entity-table-wrap.entity-scroll--active::-webkit-scrollbar-thumb{background-color:rgba(78,89,105,.55)}
.entity-table-wrap::-webkit-scrollbar-thumb:hover{background-color:rgba(78,89,105,.8)}
.entity-table-wrap table{width:100%;border-collapse:collapse;font-size:14px;line-height:22px}
.entity-table-wrap th{position:sticky;top:0;z-index:1;background:#f7f8fa;color:#1d2129;font-weight:500;text-align:left}
.entity-table-wrap th,.entity-table-wrap td{padding:10px 16px;border-bottom:1px solid #f2f3f5;vertical-align:middle}
.entity-table-wrap td{color:#344763}
/* 名称列对齐 Schema 页：td b 压回常规字重（Schema 页 DESIGN_RULES 同款），避免加粗显黑显大 */
.entity-table-wrap td b{font-weight:400}
/* ID 列与其他列字号统一 14px（此前 13px 显小）；不加蓝色背景块，长 ID 允许换行 */
.entity-table-wrap td code{color:inherit;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;word-break:normal;overflow-wrap:anywhere}
.entity-table-wrap td:first-child{min-width:160px}
.entity-table-wrap td:nth-child(2){min-width:240px}
.entity-type-chip{display:inline-flex;padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:12px;line-height:18px;white-space:nowrap}
.entity-props-cell{width:440px;min-width:360px;max-width:480px}
.entity-props{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;--entity-property-fill:#f2f3f5}
.entity-props__chip{display:flex;align-items:center;gap:4px;min-width:0;box-sizing:border-box;height:28px;padding:4px 8px;border:0;border-radius:4px;background:var(--entity-property-fill);font-size:12px;line-height:20px;white-space:nowrap}
.entity-props__chip b{flex:0 1 auto;min-width:0;overflow:hidden;color:#4e5969;font-weight:500;text-overflow:ellipsis}
.entity-props__chip b::after{content:":"}
.entity-props__chip em{flex:1;min-width:0;overflow:hidden;color:#1d2129;font-style:normal;text-overflow:ellipsis}
.entity-props__more{box-sizing:border-box;justify-self:start;height:28px;min-height:28px!important;padding:4px 8px;border:0;border-radius:4px;background:var(--entity-property-fill);color:#165dff;font-size:12px!important;line-height:20px!important;cursor:pointer}
.entity-props__more:hover{background:#e5e6eb}
.entity-props__more:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
.entity-props__empty{color:#c9cdd4;font-size:12px}
.entity-pagination__info{min-width:0;overflow:hidden;margin-left:auto;color:#86909c;font-size:12px;line-height:20px;text-overflow:ellipsis;white-space:nowrap}
</style>

<style>
.app-workspace .entity-result-shell .entity-table-wrap td.entity-props-cell{padding-top:8px!important;padding-bottom:8px!important}
.app-workspace .entity-toolbar-shell #entity-filter-name.entity-search-input.arco-input-wrapper{box-sizing:border-box;width:280px;min-width:0;max-width:280px;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:1 1 180px}
.app-workspace .entity-toolbar-shell #entity-filter-name.entity-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .entity-toolbar-shell #entity-filter-name.entity-search-input.arco-input-wrapper:focus-within,.app-workspace .entity-toolbar-shell #entity-filter-name.entity-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .entity-toolbar-shell #entity-filter-name .arco-input-prefix{padding-right:8px;color:#4e5969}
.app-workspace .entity-toolbar-shell #entity-filter-name.arco-input-focus .arco-input-prefix{color:#165dff}
.app-workspace .entity-toolbar-shell #entity-filter-name .arco-input-prefix svg{width:16px;height:16px;font-size:16px}
.app-workspace .entity-toolbar-shell #entity-filter-name input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .entity-toolbar-shell #entity-filter-type.entity-filter-select.arco-select-view{display:inline-flex;box-sizing:border-box;align-items:center;width:160px;min-width:160px;max-width:160px;height:32px;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 0 160px}
.app-workspace .entity-toolbar-shell #entity-filter-type.entity-filter-select.arco-select-view:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .entity-toolbar-shell #entity-filter-type.entity-filter-select.arco-select-view:focus-within,.app-workspace .entity-toolbar-shell #entity-filter-type.entity-filter-select.arco-select-view-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .entity-toolbar-shell #entity-filter-type input.arco-select-view-input{box-sizing:border-box;width:100%;height:30px!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .entity-toolbar-shell #entity-filter-type .arco-select-view-input-hidden{position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}
.app-workspace .entity-toolbar-shell #entity-filter-type .arco-select-view-value{min-width:0;overflow:hidden;font-size:14px;line-height:22px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.app-workspace .entity-toolbar-shell #entity-filter-type :is(.arco-select-view-input,.arco-select-view-value){background:transparent!important}
.entity-property-popover{box-sizing:border-box;width:440px;max-width:calc(100vw - 48px);padding:12px 16px!important}
.entity-property-popover__content{max-height:240px;overflow:auto}
.entity-property-popover__title{margin:0 0 8px;color:#1d2129;font-size:13px;line-height:20px;font-weight:500}
.entity-property-popover__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.entity-property-popover__item{display:flex;box-sizing:border-box;align-items:center;min-width:0;gap:4px;padding:4px 8px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;color:#1d2129;font-size:12px;line-height:20px;white-space:nowrap}
.entity-property-popover__item b{flex:0 1 auto;min-width:0;overflow:hidden;color:#4e5969;font-weight:500;text-overflow:ellipsis}
.entity-property-popover__item b::after{content:":"}
.entity-property-popover__item em{flex:1;min-width:0;overflow:hidden;color:#1d2129;font-style:normal;text-overflow:ellipsis}
.entity-type-option{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
