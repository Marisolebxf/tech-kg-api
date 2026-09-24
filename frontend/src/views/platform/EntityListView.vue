<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Popover as APopover } from '@arco-design/web-vue'
import { IconSearch } from '@arco-design/web-vue/es/icon'

import {
  browseEntities,
  entitySearchErrorMessage,
  getEntityIndexStatus,
  getEntitySearchTypes,
  searchEntities,
  type EntityIndexStatus,
  type EntityListResult,
  type EntityTypeCount,
} from '../../api/entitySearch'
import { currentGraphSpace } from '../../api/currentGraphSpace'
import ListPagination from '../../components/list-pagination.vue'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import { useToast } from '../../composables/use-toast'
import { useGraphSpaceStore } from '../../stores/graphSpace'

const { showToast } = useToast()

const PROPERTY_CHIP_LIMIT = 4

const keyword = ref('')
const appliedKeyword = ref('')
const entityType = ref('')
// 图空间跟随右上角全局选择器（本页不再有空间筛选控件）
const space = computed(() => currentGraphSpace())
const graphSpaceStore = useGraphSpaceStore()
const pageSize = ref(10)
const page = ref(1)

const types = ref<EntityTypeCount[]>([])
const status = ref<EntityIndexStatus | null>(null)
const result = ref<EntityListResult | null>(null)
const loading = ref(false)
const searchError = ref('')

const items = computed(() => result.value?.items ?? [])
const isBrowseMode = computed(() => !appliedKeyword.value)
const paginationTotal = computed(() => {
  if (!result.value) return 0
  return result.value.total
    ?? (result.value.returned ?? result.value.items.length) + (page.value - 1) * pageSize.value
})
const totalPages = computed(() => {
  return Math.max(Math.ceil(paginationTotal.value / pageSize.value), 1)
})
const modeLabel = computed(() => {
  const mode = result.value?.mode
  if (mode === 'browse') return '浏览（图直查）'
  if (mode === 'graph-exact') return '精确匹配'
  if (mode === 'hybrid') return '混合（语义+关键词）'
  if (mode === 'dense') return '语义'
  return '关键词'
})

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
  searchError.value = ''
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
    result.value = null
    searchError.value = entitySearchErrorMessage(error)
  } finally {
    loading.value = false
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
  void loadIndexInfo().then(() => doSearch())
})

// 全局图空间切换：重置分页与关键词后按新空间重查
watch(
  () => graphSpaceStore.current,
  () => {
    page.value = 1
    appliedKeyword.value = ''
    void loadIndexInfo().then(() => doSearch())
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
            placeholder="实体类型"
            allow-clear
            :scrollbar="false"
            @change="onEntityTypeChange"
          >
            <a-option v-for="t in types" :key="t.name" :value="t.name">
              {{ t.name }}（{{ t.count }}）
            </a-option>
          </a-select>
        </div>
        <div class="entity-toolbar__right">
          <a-input
            id="entity-filter-name"
            v-model="keyword"
            class="entity-search-input"
            :max-length="SEARCH_KEYWORD_MAX_LENGTH"
            aria-label="输入实体名称 / 属性关键词（语义 + 关键词混合检索）；留空则分页浏览全部实体"
            placeholder="输入实体名称 / 属性关键词"
            @keyup.enter="resetPagingAndSearch"
          >
            <template #prefix><IconSearch /></template>
          </a-input>
          <button class="kg-button" type="button" :disabled="loading" @click="resetPagingAndSearch">
            {{ loading ? '检索中...' : '搜索' }}
          </button>
        </div>
      </div>
      <p v-if="status?.milvusReachable === false" class="entity-hint">
        Milvus 当前不可用，已降级为 VID/已建图属性索引的精确查询。
      </p>
      <p v-else-if="status && !status.bm25Ready && status.indexed" class="entity-hint">
        BM25 关键词条目缺失（仅语义检索可用），可通过图谱构建任务的实体索引重建恢复混合检索能力。
      </p>
    </section>

    <section class="entity-shell entity-result-shell" aria-label="实体列表">
      <div v-if="loading" class="entity-empty">加载中...</div>
      <div v-else-if="searchError" class="entity-empty" role="alert">
        <span>{{ searchError }}</span>
        <button class="kg-button" type="button" @click="doSearch">重试</button>
      </div>
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
                  <td>{{ item.score ?? '' }}</td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <ListPagination
          :total="paginationTotal"
          :page="page"
          :page-size="pageSize"
          :disabled="loading"
          @change="goPage"
          @change-size="onPageSizeChange"
        >
          <template #summary>
            <span class="entity-pagination__info">
              <template v-if="isBrowseMode && result?.total != null">共 {{ result.total }} 个实体 · </template>第 {{ page }} / {{ totalPages }} 页 · 检索模式：{{ modeLabel }}
            </span>
          </template>
        </ListPagination>
      </template>
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
.entity-hint{margin:0;padding:8px 16px;border-top:1px dashed #ffe4ba;background:#fff7e8;color:#b54708;font-size:12px;line-height:20px}
.entity-empty{flex:1;display:grid;place-items:center;padding:40px 16px;color:#86909c;font-size:13px;line-height:22px;text-align:center}
.entity-table-wrap{flex:1;min-height:0;overflow:auto}
.entity-table-wrap table{width:100%;border-collapse:collapse;font-size:14px;line-height:22px}
.entity-table-wrap th{position:sticky;top:0;z-index:1;background:#f7f8fa;color:#1d2129;font-weight:500;text-align:left}
.entity-table-wrap th,.entity-table-wrap td{padding:10px 16px;border-bottom:1px solid #f2f3f5;vertical-align:middle}
.entity-table-wrap td code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:12px;word-break:normal;overflow-wrap:anywhere}
.entity-table-wrap td:first-child{min-width:160px}
.entity-table-wrap td:nth-child(2){min-width:240px}
.entity-type-chip{display:inline-flex;padding:1px 10px;border-radius:999px;background:#eef5ff;color:#165dff;font-size:12px;line-height:18px;white-space:nowrap}
.entity-props-cell{width:440px;min-width:360px;max-width:480px}
.entity-props{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.entity-props__chip{display:flex;align-items:center;gap:4px;min-width:0;padding:4px 8px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;font-size:12px;line-height:20px;white-space:nowrap}
.entity-props__chip b{flex:0 1 auto;min-width:0;overflow:hidden;color:#4e5969;font-weight:500;text-overflow:ellipsis}
.entity-props__chip b::after{content:":"}
.entity-props__chip em{flex:1;min-width:0;overflow:hidden;color:#1d2129;font-style:normal;text-overflow:ellipsis}
.entity-props__more{justify-self:start;padding:4px 8px;border:1px solid #bcd4f7;border-radius:4px;background:#eaf2ff;color:#165dff;font-size:12px;line-height:20px;cursor:pointer}
.entity-props__more:hover{background:#dcebff}
.entity-props__empty{color:#c9cdd4;font-size:12px}
.entity-pagination__info{min-width:0;overflow:hidden;color:#86909c;font-size:12px;line-height:20px;text-overflow:ellipsis;white-space:nowrap}
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
</style>
