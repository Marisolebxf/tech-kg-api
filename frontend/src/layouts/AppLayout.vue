<script setup lang="ts">
import { computed, onBeforeUnmount, onErrorCaptured, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import iconMenuCollapse from '../assets/icons/icon-menu-collapse.svg'
import iconSidebarArrow from '../assets/icons/icon-sidebar-arrow.svg'
import navOverview from '../assets/icons/nav-overview.svg'
import navQuery from '../assets/icons/nav-query.svg'
import navReview from '../assets/icons/nav-review.svg'
import navSchema from '../assets/icons/nav-schema.svg'
import navServices from '../assets/icons/nav-services.svg'
import navTasks from '../assets/icons/nav-tasks.svg'
// import navFlow from '../assets/icons/nav-flow.svg'
import navTools from '../assets/icons/nav-tools.svg'
import { useAppStore } from '../stores/app'
import avatarBen from '../assets/images/avatar-ben.png'
import logoKg from '../assets/images/logo-kg.png'
import { getReviewPriority, reviewRecords } from '../views/platform/manual-review-data'

const route = useRoute()
const appStore = useAppStore()
const pageTitle = computed(() => String(route.meta.title ?? '亿级知识图谱'))
const showPageContext = computed(() => !route.path.startsWith('/processing-instance/') && !route.path.startsWith('/manual-review/task/') && !route.path.startsWith('/task-detail/'))
const activePrimaryNav = computed(() => {
  if (route.path.startsWith('/manual-review')) return 'manual-review'
  if (route.path === '/tasks' || route.path.startsWith('/processing-instance/') || route.path.startsWith('/task-detail/')) return 'tasks'
  return ''
})
const routeError = ref('')
const serviceNavCollapsed = ref(false)
const alertDrawerOpen = ref(false)
const alertPreviewOpen = ref(false)
const userMenuOpen = ref(false)
const userEntryRef = ref<HTMLElement | null>(null)
const assistantEntryRef = ref<HTMLButtonElement | null>(null)
const accountFeedback = ref('')
const assistantOpen = ref(false)
const assistantPosition = ref({ x: 0, y: 0 })
const assistantViewport = ref({ width: 1440, height: 900 })
// 问答小助手（已隐藏）
// const assistantDragging = ref(false)
// const assistantDragMoved = ref(false)
// let assistantDragOrigin = { pointerX: 0, pointerY: 0, x: 0, y: 0 }
// const assistantQuestion = ref('')
// const assistantMessages = ref<Array<{ role: 'assistant' | 'user'; content: string; sources?: string[] }>>([
//   { role: 'assistant', content: '可询问专家、机构、论文关系，或查询任务与异常。' },
// ])
const alertItems = computed(() => reviewRecords.filter((record) => record.status !== '已完成').map((record) => {
  const priority = getReviewPriority(record)
  return {
    id: record.id,
    blocked: priority.level === 'P0',
    module: record.module,
    title: `${record.object}：${record.type}`,
    meta: `${record.id} · ${record.node} · ${record.evidence}`,
    time: record.updatedAt,
    status: record.status,
    hasReviewDetail: true,
    detailTo: `/processing-instance/${record.id}`,
    reviewTo: `/manual-review/task/${record.id}`,
  }
}))
const blockedAlertCount = computed(() => alertItems.value.filter((item) => item.blocked).length)
const serviceNavItems = [
  { to: '/expert-direct', label: '科技专家/人才直接关系', fullLabel: '科技专家/人才直接关系' },
  { to: '/node-indirect', label: '科技单节点间接关系', fullLabel: '科技单节点间接关系' },
  { to: '/two-point-achievement', label: '科技两点合作成果', fullLabel: '科技两点合作成果' },
  { to: '/expert-colleague', label: '科技专家同事关系', fullLabel: '科技专家同事关系' },
  { to: '/expert-alumni', label: '科技专家校友关系', fullLabel: '科技专家校友关系' },
  { to: '/paper-cooperation', label: '科技专家论文合作关系', fullLabel: '科技专家论文合作关系' },
  { to: '/enterprise-relation', label: '重点关注科技企业关系', fullLabel: '重点关注科技企业关系' },
  { to: '/industry-chain-event', label: '科技产业链点TOP-N事件关系', fullLabel: '科技产业链点TOP-N事件关系' },
  { to: '/industry-chain-panorama', label: '科技产业链全景图', fullLabel: '科技产业链全景图' },
]
const showServiceNavItems = computed(() => (
  !appStore.collapsed && !serviceNavCollapsed.value
))
// 问答小助手（已隐藏）
// const assistantEntryStyle = computed(() => ({ left: `${assistantPosition.value.x}px`, top: `${assistantPosition.value.y}px` }))
// const assistantPanelStyle = computed(() => {
//   const viewportWidth = assistantViewport.value.width
//   const viewportHeight = assistantViewport.value.height
//   const width = Math.min(390, viewportWidth - 20)
//   const height = Math.min(560, viewportHeight - 120)
//   return {
//     left: `${Math.max(10, Math.min(viewportWidth - width - 10, assistantPosition.value.x + 118 - width))}px`,
//     top: `${Math.max(10, Math.min(viewportHeight - height - 10, assistantPosition.value.y - height - 10))}px`,
//     width: `${width}px`,
//     height: `${height}px`,
//   }
// })

onErrorCaptured((error) => {
  routeError.value = error instanceof Error ? error.message : String(error)
  return false
})

function openAlertDrawer() {
  alertPreviewOpen.value = false
  userMenuOpen.value = false
  assistantOpen.value = false
  alertDrawerOpen.value = true
}

function toggleUserMenu() {
  alertPreviewOpen.value = false
  userMenuOpen.value = !userMenuOpen.value
}

function handleAccountAction(action: '个人中心' | '账号与安全' | '操作记录' | '退出登录') {
  accountFeedback.value = action === '退出登录' ? '正在安全退出系统。' : `已打开${action}。`
}

// 问答小助手（已隐藏）
// function toggleAssistant() {
//   if (assistantDragMoved.value) {
//     assistantDragMoved.value = false
//     return
//   }
//   alertDrawerOpen.value = false
//   userMenuOpen.value = false
//   assistantOpen.value = !assistantOpen.value
// }

// function startAssistantDrag(event: PointerEvent) {
//   assistantDragging.value = true
//   assistantDragMoved.value = false
//   assistantDragOrigin = { pointerX: event.clientX, pointerY: event.clientY, x: assistantPosition.value.x, y: assistantPosition.value.y }
//   ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
// }

// function moveAssistantDrag(event: PointerEvent) {
//   if (!assistantDragging.value) return
//   const deltaX = event.clientX - assistantDragOrigin.pointerX
//   const deltaY = event.clientY - assistantDragOrigin.pointerY
//   if (Math.abs(deltaX) + Math.abs(deltaY) > 4) assistantDragMoved.value = true
//   assistantPosition.value = clampAssistantPosition({
//     x: assistantDragOrigin.x + deltaX,
//     y: assistantDragOrigin.y + deltaY,
//   })
// }

// function stopAssistantDrag(event: PointerEvent) {
//   assistantDragging.value = false
//   const target = event.currentTarget as HTMLElement
//   if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
// }

function clampAssistantPosition(position: { x: number; y: number }) {
  const entryWidth = assistantEntryRef.value?.offsetWidth ?? 126
  const entryHeight = assistantEntryRef.value?.offsetHeight ?? 42
  return {
    x: Math.max(8, Math.min(assistantViewport.value.width - entryWidth - 8, position.x)),
    y: Math.max(8, Math.min(assistantViewport.value.height - entryHeight - 8, position.y)),
  }
}

function placeAssistantAtDefault() {
  assistantPosition.value = clampAssistantPosition({ x: Number.POSITIVE_INFINITY, y: Number.POSITIVE_INFINITY })
}

function handleViewportResize() {
  assistantViewport.value = { width: window.innerWidth, height: window.innerHeight }
  assistantPosition.value = clampAssistantPosition(assistantPosition.value)
}

function handleVisibilityChange() {
  if (document.visibilityState === 'visible') handleViewportResize()
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (userMenuOpen.value && !userEntryRef.value?.contains(event.target as Node)) userMenuOpen.value = false
}

// 问答小助手（已隐藏）
// function askAssistant() {
//   const question = assistantQuestion.value.trim()
//   if (!question) return
//   assistantMessages.value.push({ role: 'user', content: question })
//   assistantQuestion.value = ''
//   if (question.includes('异常') || question.includes('审核') || question.includes('任务')) {
//     assistantMessages.value.push({ role: 'assistant', content: '当前有 2 个阻断批次需要人工审核，共隔离 711 条异常记录。其中图谱构建批次 326 条，数据处理批次 385 条。', sources: ['任务中心', '人工处理', '异常通知'] })
//     return
//   }
//   if (question.includes('张明远') || question.includes('专家')) {
//     assistantMessages.value.push({ role: 'assistant', content: '检索结果显示，张明远近五年的核心合作方向集中在智能计算与芯片设计，主要合作机构包括中国科学院自动化研究所和华南智能芯片有限公司。', sources: ['专家实体', '论文合作记录', '项目与专利记录'] })
//     return
//   }
//   assistantMessages.value.push({ role: 'assistant', content: '已从统一知识图谱中检索相关实体、关系和来源记录。您可以进入完整知识检索页继续限定时间、业务域或上传参考文档进行分析。', sources: ['统一知识图谱', 'Schema v1.8'] })
// }

watch(() => route.fullPath, () => {
  alertDrawerOpen.value = false
  alertPreviewOpen.value = false
  userMenuOpen.value = false
})

onMounted(() => {
  assistantViewport.value = { width: window.innerWidth, height: window.innerHeight }
  placeAssistantAtDefault()
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('focus', handleViewportResize)
  window.addEventListener('pageshow', handleViewportResize)
  window.visualViewport?.addEventListener('resize', handleViewportResize)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  window.requestAnimationFrame(handleViewportResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('focus', handleViewportResize)
  window.removeEventListener('pageshow', handleViewportResize)
  window.visualViewport?.removeEventListener('resize', handleViewportResize)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})
</script>

<template>
  <div class="app-viewport">
    <div class="app-shell" :class="{ 'is-collapsed': appStore.collapsed }">
        <aside class="app-sidebar">
          <div class="app-brand">
            <img class="app-brand__logo" :src="logoKg" alt="知识图谱平台" />
            <div v-if="!appStore.collapsed" class="app-brand__name">知识图谱平台</div>
            <button
              class="app-brand__menu"
              type="button"
              :aria-label="appStore.collapsed ? '展开导航' : '收起导航'"
              @click="appStore.toggleCollapsed()"
            >
              <img :src="iconMenuCollapse" alt="" aria-hidden="true" />
            </button>
          </div>

          <nav class="app-nav" aria-label="平台功能导航">
            <div v-if="!appStore.collapsed" class="app-nav__group"><span>工作台</span></div>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" active-class="app-nav__item--active" to="/overview" :title="appStore.collapsed ? '平台总览' : undefined">
              <img class="app-nav__icon" :src="navOverview" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">平台总览</span>
            </RouterLink>

            <div v-if="!appStore.collapsed" class="app-nav__group"><span>图谱建设与治理</span></div>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" active-class="app-nav__item--active" to="/schema" :title="appStore.collapsed ? 'Schema 管理' : undefined">
              <img class="app-nav__icon" :src="navSchema" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">Schema 管理</span>
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" :class="{ 'app-nav__item--active': activePrimaryNav === 'tasks' }" active-class="app-nav__item--active" to="/tasks" :title="appStore.collapsed ? '图谱构建' : undefined">
              <img class="app-nav__icon" :src="navTasks" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">图谱构建</span>
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" :class="{ 'app-nav__item--active': activePrimaryNav === 'manual-review' }" active-class="app-nav__item--active" to="/manual-review" :title="appStore.collapsed ? '人工处理' : undefined">
              <img class="app-nav__icon" :src="navReview" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">人工处理</span>
            </RouterLink>
            <!-- 抽取 Pipeline 入口暂时隐藏，需要时取消注释恢复
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" active-class="app-nav__item--active" to="/pipelines" :title="appStore.collapsed ? '抽取 Pipeline' : undefined">
              <img class="app-nav__icon" :src="navFlow" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">抽取 Pipeline</span>
            </RouterLink>
            -->

            <div v-if="!appStore.collapsed" class="app-nav__group"><span>平台管理</span></div>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" active-class="app-nav__item--active" to="/configurations" :title="appStore.collapsed ? '配置管理' : undefined">
              <img class="app-nav__icon" :src="navTools" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">配置管理</span>
            </RouterLink>

            <div v-if="!appStore.collapsed" class="app-nav__group"><span>查询与服务</span></div>
            <RouterLink class="app-nav__item app-nav__item--top app-nav__item--leaf" active-class="app-nav__item--active" to="/graph-query" :title="appStore.collapsed ? '图谱查询' : undefined">
              <img class="app-nav__icon" :src="navQuery" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">图谱查询</span>
            </RouterLink>
            <button
              class="app-nav__item app-nav__item--top app-nav__item--button"
              :class="{ 'app-nav__item--open': !serviceNavCollapsed }"
              type="button"
              :title="appStore.collapsed ? '业务服务' : undefined"
              :aria-expanded="!serviceNavCollapsed"
              @click="serviceNavCollapsed = !serviceNavCollapsed"
            >
              <img class="app-nav__icon" :src="navServices" alt="" aria-hidden="true" />
              <span v-if="!appStore.collapsed">业务服务</span>
              <img v-if="!appStore.collapsed" class="app-nav__arrow" :src="iconSidebarArrow" alt="" aria-hidden="true" />
            </button>
            <RouterLink
              v-for="(item, index) in serviceNavItems"
              :key="item.to"
              v-if="showServiceNavItems"
              class="app-nav__item app-nav__item--sub"
              active-class="app-nav__item--active"
              :to="item.to"
              :title="item.fullLabel"
            >
              <em>{{ String(index + 1).padStart(2, '0') }}</em>
              <span>{{ item.label }}</span>
            </RouterLink>
          </nav>

        </aside>

        <main class="app-main" :class="{ 'is-overview-page': route.path === '/overview' }">
          <div class="app-top-actions">
            <span v-if="showPageContext" class="app-top-actions__context">{{ pageTitle }}</span>
            <div class="app-top-actions__right">
              <div class="app-alert-entry" @mouseenter="alertPreviewOpen = !alertDrawerOpen" @mouseleave="alertPreviewOpen = false">
                <button class="app-alert-bell" type="button" :aria-label="`${alertItems.length} 条异常与人工处理通知`" :aria-expanded="alertDrawerOpen" @click="openAlertDrawer">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
                  <b>{{ alertItems.length }}</b>
                </button>
                <aside v-if="alertPreviewOpen" class="alert-preview" aria-label="异常与人工处理概览">
                  <header><div><strong>异常与人工处理</strong><span>实时更新</span></div></header>
                  <section><article><strong>{{ alertItems.length }}</strong><span>待处理</span></article><article class="danger"><strong>{{ blockedAlertCount }}</strong><span>阻断流程</span></article></section>
                </aside>
              </div>
              <div ref="userEntryRef" class="app-user-entry">
                <button class="app-top-actions__user" type="button" aria-label="当前登录用户：图谱管理员张建图" :aria-expanded="userMenuOpen" @click="toggleUserMenu">
                  <img :src="avatarBen" alt="" aria-hidden="true" />
                  <span><strong>张建图</strong><em>图谱管理员</em></span>
                  <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
                </button>
                <aside v-if="userMenuOpen" class="app-user-menu">
                  <header><img :src="avatarBen" alt="" /><div><strong>张建图</strong><span>图谱管理员</span></div><b>管理员</b></header>
                  <nav>
                    <button type="button" @click="handleAccountAction('个人中心')"><i>人</i><span>个人中心</span></button>
                    <button type="button" @click="handleAccountAction('账号与安全')"><i>安</i><span>账号与安全</span></button>
                    <button type="button" @click="handleAccountAction('操作记录')"><i>录</i><span>操作记录</span></button>
                    <button class="danger" type="button" @click="handleAccountAction('退出登录')"><i>退</i><span>退出登录</span></button>
                  </nav>
                  <footer v-if="accountFeedback">{{ accountFeedback }}</footer>
                </aside>
              </div>
            </div>
          </div>
          <section class="app-workspace" :aria-label="pageTitle">
            <div v-if="routeError" class="route-error">
              <strong>页面渲染异常</strong>
              <span>{{ routeError }}</span>
            </div>
            <RouterView v-else />
          </section>
        </main>
        <button v-if="alertDrawerOpen" class="alert-drawer-mask" type="button" aria-label="关闭告警抽屉" @click="alertDrawerOpen = false" />
        <aside v-if="alertDrawerOpen" class="alert-drawer" aria-label="异常与人工处理通知">
          <header><div><h2>异常与人工处理</h2><p>{{ alertItems.length }} 条待处理，与人工审核队列同步</p></div><button type="button" aria-label="关闭" @click="alertDrawerOpen = false">×</button></header>
          <div class="alert-drawer__list">
            <article v-for="item in alertItems" :key="item.id" class="alert-item">
              <i></i>
              <div><span>{{ item.module }}<em>{{ item.time }}</em></span><strong>{{ item.title }}</strong><p>{{ item.meta }}</p><small>待人工处理</small><nav><template v-if="item.hasReviewDetail"><RouterLink :to="item.detailTo">查看详情</RouterLink><RouterLink class="primary" :to="item.reviewTo">人工处理</RouterLink></template><button v-else type="button" disabled>查看详情</button></nav></div>
            </article>
          </div>
          <footer><RouterLink to="/tasks">查看全部任务</RouterLink><RouterLink class="footer-primary" to="/manual-review">查看处理队列 →</RouterLink></footer>
        </aside>
        <!-- 问答小助手（已隐藏）
        <aside v-if="assistantOpen" class="knowledge-assistant" :style="assistantPanelStyle" aria-label="知识图谱助手">
          <header><div><i>AI</i><span><strong>知识图谱助手</strong></span></div><button type="button" aria-label="关闭知识助手" @click="assistantOpen=false">×</button></header>
          <div class="knowledge-assistant__messages">
            <article v-for="(message, index) in assistantMessages" :key="index" :class="`is-${message.role}`">
              <p>{{ message.content }}</p>
              <div v-if="message.sources"><span>证据来源</span><b v-for="source in message.sources" :key="source">{{ source }}</b></div>
            </article>
          </div>
          <RouterLink class="knowledge-assistant__full" to="/graph-tools">进入完整知识检索问答 →</RouterLink>
          <form @submit.prevent="askAssistant"><textarea v-model="assistantQuestion" placeholder="请输入要查询的问题，例如：当前有哪些异常需要处理？" @keydown.enter.exact.prevent="askAssistant" /><button type="submit" :disabled="!assistantQuestion.trim()">发送</button></form>
        </aside>
        <button ref="assistantEntryRef" class="knowledge-assistant-entry" type="button" :class="{ active: assistantOpen, dragging: assistantDragging }" :style="assistantEntryStyle" :aria-expanded="assistantOpen" aria-label="打开知识图谱助手，可拖动调整位置" @pointerdown="startAssistantDrag" @pointermove="moveAssistantDrag" @pointerup="stopAssistantDrag" @pointercancel="stopAssistantDrag" @click="toggleAssistant">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="6" width="16" height="13" rx="4"/><path d="M9 6V4h6v2M8.5 12h.01M15.5 12h.01M9 16h6"/></svg>
          <span>{{ assistantOpen ? '收起助手' : '知识助手' }}</span>
        </button>
        -->
      </div>
  </div>
</template>

<style scoped>
.app-viewport {
  width: 100vw;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: #dcecff;
}

.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  width: 100%;
  height: 100%;
  background:
    linear-gradient(135deg, #dbeaff 0%, #eef6ff 45%, #e0f1ff 100%);
  transition: grid-template-columns 0.2s ease;
}

.app-shell.is-collapsed {
  grid-template-columns: var(--sidebar-width-collapsed) minmax(0, 1fr);
}

.app-sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  padding: 18px 14px 14px;
  overflow: hidden;
  color: var(--text-primary);
  border-right: 1px solid rgba(132, 178, 246, 0.82);
  background:
    linear-gradient(180deg, rgba(232, 243, 255, 0.98) 0%, rgba(213, 232, 255, 0.98) 58%, rgba(199, 224, 255, 0.98) 100%),
    #dcecff;
  box-shadow: 16px 0 36px rgba(48, 105, 194, 0.18);
}

.app-sidebar::before {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.075) 1px, transparent 1px),
    linear-gradient(rgba(22, 93, 255, 0.075) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.62), transparent 78%);
  pointer-events: none;
  content: "";
}

.app-sidebar > * {
  position: relative;
}

.app-brand {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(84, 139, 220, 0.22);
}

.app-brand__logo {
  width: 34px;
  height: 34px;
  object-fit: contain;
}

.app-brand__name {
  flex: 0 0 auto;
  font-size: 18px;
  line-height: 25px;
  font-weight: 700;
  color: #10264c;
  white-space: nowrap;
}

.app-brand__menu {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-left: auto;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.app-brand__menu img {
  width: 18px;
  height: 18px;
  object-fit: contain;
  opacity: 0.72;
}

.app-brand__menu:hover {
  background: rgba(255, 255, 255, 0.72);
}

.app-shell.is-collapsed .app-brand {
  justify-content: center;
}

.app-shell.is-collapsed .app-brand__menu {
  margin-left: 0;
}

.app-shell.is-collapsed .app-nav__item {
  grid-template-columns: 22px;
  justify-content: center;
  padding-inline: 0;
}

.app-shell.is-collapsed .app-nav__item--active {
  width: calc(100% - 12px);
  margin-left: 6px;
}

.app-nav {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 16px;
  padding-bottom: 14px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(84, 139, 220, .38) transparent;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: none;
}

.app-nav::-webkit-scrollbar {
  display: none;
}

.app-nav::after {
  display: none;
}

.app-nav__item {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) 14px;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #243b63;
  font-size: 16px;
  line-height: 23px;
  white-space: nowrap;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.app-nav__item--button {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  border-color: transparent;
  background: transparent;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

.app-nav__item--button:focus {
  outline: none;
}

.app-nav__item--button:focus-visible {
  border-color: rgba(86, 149, 239, 0.52);
  background: rgba(255, 255, 255, 0.62);
}

.app-nav__item:hover {
  color: #165dff;
  border-color: rgba(86, 149, 239, 0.52);
  background: rgba(255, 255, 255, 0.86);
}

.app-nav__group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 20px 8px 8px;
  padding-top: 14px;
  border-top: 1px solid rgba(111, 151, 207, 0.18);
  color: #567198;
  font-size: 14px;
  line-height: 22px;
  font-weight: 600;
  letter-spacing: 0;
}

.app-nav__group:first-child {
  margin-top: 6px;
  padding-top: 0;
  border-top: 0;
}

.app-nav__group em {
  color: #91a5c0;
  font-size: 10px;
  font-style: normal;
  font-weight: 400;
  letter-spacing: .02em;
}

.app-nav__icon {
  width: 19px;
  height: 19px;
  align-self: center;
  justify-self: center;
  object-fit: contain;
  opacity: 0.82;
}

.app-nav__arrow {
  width: 14px;
  height: 14px;
  justify-self: end;
  object-fit: contain;
  opacity: 0.52;
  transition: transform 0.16s ease;
}

.app-nav__item--leaf {
  grid-template-columns: 22px minmax(0, 1fr);
}

.app-nav__item--open {
  margin-top: 8px;
}

.app-nav__item--open .app-nav__arrow {
  transform: rotate(90deg);
}

.app-nav__item--active {
  position: relative;
  z-index: 1;
  grid-template-columns: 1fr;
  width: min(218px, calc(100% - 24px));
  margin-left: 24px;
  color: #165dff;
  border-color: rgba(87, 150, 242, 0.76);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(218, 235, 255, 0.96)),
    #f7fbff;
  box-shadow:
    inset 3px 0 0 #165dff,
    0 10px 24px rgba(22, 93, 255, 0.18);
}

.app-nav__item--active .app-nav__icon,
.app-nav__item--active .app-nav__arrow {
  opacity: 1;
}

.app-nav__item--top.app-nav__item--active {
  grid-template-columns: 22px minmax(0, 1fr) 14px;
  width: 100%;
  margin-left: 0;
}

.app-nav__item--top.app-nav__item--leaf.app-nav__item--active {
  grid-template-columns: 22px minmax(0, 1fr);
}

.app-nav__item--sub {
  position: relative;
  z-index: 1;
  grid-template-columns: 32px minmax(0, 1fr);
  width: min(224px, calc(100% - 30px));
  min-height: 44px;
  margin: 4px 0 4px 30px;
  padding: 0 12px;
  border-color: rgba(179, 209, 255, 0.42);
  background: rgba(255, 255, 255, 0.42);
  color: #2e4770;
  font-size: 15px;
  line-height: 22px;
}

.app-nav__item--sub em {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  border-radius: 999px;
  background: rgba(22, 93, 255, 0.08);
  color: #4c74b4;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}

.app-nav__item--sub span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-nav__item--sub.app-nav__item--active {
  color: var(--primary);
  border: 1px solid rgba(87, 150, 242, 0.72);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(226, 239, 255, 0.96)),
    #eef5ff;
  box-shadow: inset 3px 0 0 #165dff, 0 8px 18px rgba(22, 93, 255, 0.12);
}

.app-nav__item--sub.app-nav__item--active em {
  background: var(--primary);
  color: #fff;
}

.app-main {
  min-width: 0;
  height: 100%;
  padding: 18px 20px;
  overflow: hidden;
}

.app-top-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  height: 34px;
  margin-bottom: 8px;
}

.app-top-actions__user {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(191, 215, 250, .96);
  border-radius: 6px;
  background: rgba(255, 255, 255, .84);
  color: #344766;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
}

.app-top-actions__user>img { width:22px;height:22px;border-radius:50%;object-fit:cover; }
.app-top-actions__user>span { display:grid;gap:0;line-height:1.15; }
.app-top-actions__user strong { color:#344766;font-size:12px;font-weight:600; }
.app-top-actions__user em { color:#7890b5;font-size:9px;font-style:normal; }
.app-top-actions__user>i { color:#7890b5;font-size:10px;font-style:normal; }
.app-top-actions__user>svg { width:14px;height:14px;fill:none;stroke:#7890b5;stroke-width:1.6;transition:transform .2s; }
.app-top-actions__user[aria-expanded="true"] { border-color:#8fb7f2;background:#fff;box-shadow:0 5px 14px rgba(44,91,157,.1); }
.app-top-actions__user[aria-expanded="true"]>svg { transform:rotate(180deg); }
.app-user-entry { position:relative;z-index:38; }
.app-user-menu { position:absolute;z-index:48;top:39px;right:0;width:250px;overflow:hidden;border:1px solid #c8daf4;border-radius:9px;background:#fff;box-shadow:0 18px 45px rgba(34,74,132,.2);color:#263853; }
.app-user-menu::before { position:absolute;top:-6px;right:25px;width:11px;height:11px;border-top:1px solid #c8daf4;border-left:1px solid #c8daf4;background:#fff;content:"";transform:rotate(45deg); }
.app-user-menu>header { position:relative;display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;padding:14px;border-bottom:1px solid #e4ecf6;background:#fbfdff; }
.app-user-menu>header img { width:34px;height:34px;border-radius:50%;object-fit:cover; }
.app-user-menu>header div { display:grid;gap:3px; }.app-user-menu>header strong { font-size:13px; }.app-user-menu>header span { color:#75839a;font-size:10px; }.app-user-menu>header b { padding:2px 6px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:9px;font-weight:500; }
.app-user-menu>p { margin:0;padding:10px 14px;border-bottom:1px solid #e9eff7;color:#718098;font-size:10px;line-height:17px; }
.app-user-menu nav { display:grid;padding:6px; }.app-user-menu nav button { display:flex;align-items:center;justify-content:flex-start;gap:10px;height:40px;padding:0 10px;border:0;border-radius:5px;background:#fff;color:#344766;text-align:left;cursor:pointer; }.app-user-menu nav button:hover { background:#f1f6fd;color:#165dff; }.app-user-menu nav button i { display:grid;place-items:center;width:22px;height:22px;border-radius:5px;background:#edf3fb;color:#526783;font-size:9px;font-style:normal; }.app-user-menu nav button span { font-size:11px; }.app-user-menu nav button.danger { margin-top:5px;border-top:1px solid #e8eef6;border-radius:0 0 5px 5px; }.app-user-menu nav button.danger span,.app-user-menu nav button.danger i { color:#b42318; }
.app-user-menu>footer { padding:9px 13px;border-top:1px solid #e4ecf6;background:#f7faff;color:#526783;font-size:9px;line-height:15px; }

.app-top-actions__context { color: #65738a; font-size: 13px; }
.app-top-actions__right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.app-alert-entry { position: relative; z-index: 38; display: inline-flex; }
.app-alert-bell { position: relative; display: inline-grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 1px solid rgba(191,215,250,.96); border-radius: 7px; background: rgba(255,255,255,.9); color: #40516c; cursor: pointer; }
.app-alert-bell:hover,.app-alert-bell[aria-expanded="true"] { border-color: #8fb7f2; background: #fff; color: #165dff; }
.app-alert-bell svg { width: 19px; height: 19px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.app-alert-bell b { position: absolute; top: -6px; right: -7px; display: grid; place-items: center; min-width: 18px; height: 18px; padding: 0 4px; border: 2px solid #eaf3ff; border-radius: 10px; background: #d92d20; color: #fff; font-size: 10px; line-height: 1; }
.alert-preview { position:absolute;z-index:45;top:38px;right:-8px;width:350px;overflow:hidden;border:1px solid #c8daf4;border-radius:9px;background:#fff;box-shadow:0 18px 45px rgba(34,74,132,.2);color:#263853; }
.alert-preview::before { position:absolute;top:-6px;right:17px;width:11px;height:11px;border-top:1px solid #c8daf4;border-left:1px solid #c8daf4;background:#fff;content:"";transform:rotate(45deg); }
.alert-preview>header { display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #e1eaf6; }
.alert-preview>header>div { display:flex;align-items:center;gap:8px; }
.alert-preview>header strong { font-size:14px; }
.alert-preview>header span { padding:2px 6px;border-radius:999px;background:#e9f8ef;color:#067647;font-size:9px; }
.alert-preview>header em { color:#7a899f;font-size:9px;font-style:normal; }
.alert-preview>section { display:grid;grid-template-columns:repeat(2,1fr);gap:7px;padding:10px 12px;background:#f7faff; }
.alert-preview>section article { display:grid;gap:2px;padding:9px;border:1px solid #dce8f8;border-radius:6px;background:#fff; }
.alert-preview>section article strong { color:#165dff;font-size:18px; }
.alert-preview>section article.danger strong { color:#d92d20; }
.alert-preview>section article span { color:#71809a;font-size:9px; }
.alert-preview>div { padding:5px 12px 9px; }
.alert-preview>div p { display:grid;grid-template-columns:7px minmax(0,1fr);gap:9px;margin:0;padding:8px 2px;border-bottom:1px solid #edf2f8; }
.alert-preview>div p:last-child { border-bottom:0; }
.alert-preview>div p>i { width:7px;height:7px;margin-top:5px;border-radius:50%;background:#f79009; }
.alert-preview>div p span { display:grid;gap:2px; }
.alert-preview>div p strong { overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap; }
.alert-preview>div p em { color:#8592a6;font-size:9px;font-style:normal; }

.alert-drawer-mask { position: fixed; z-index: 39; inset: 0; border: 0; background: rgba(16,36,76,.18); cursor: default; }
.alert-drawer { position: fixed; z-index: 40; top: 0; right: 0; display: grid; grid-template-rows: auto auto minmax(0,1fr) auto; width: 430px; height: 100vh; padding: 0; border-left: 1px solid #c8daf4; background: #f8fbff; box-shadow: -18px 0 42px rgba(34,74,132,.2); }
.alert-drawer>header { display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 20px 15px; border-bottom: 1px solid #dce8f8; background: #fff; }
.alert-drawer h2 { margin: 0; color: #152642; font-size: 19px; }
.alert-drawer header p { margin: 4px 0 0; color: #73819a; font-size: 12px; }
.alert-drawer header button { width: 30px; height: 30px; border: 0; border-radius: 5px; background: #f2f6fc; color: #60708b; font-size: 21px; cursor: pointer; }
.alert-drawer__filter { display: flex; gap: 5px; padding: 10px 16px; border-bottom: 1px solid #dce8f8; background: #fff; }
.alert-drawer__filter button { height: 28px; padding: 0 10px; border: 0; border-radius: 5px; background: transparent; color: #66758f; font-size: 12px; cursor: pointer; }
.alert-drawer__filter button.active { background: #eaf2ff; color: #165dff; font-weight: 600; }
.alert-drawer__list { overflow: auto; padding: 10px; }
.alert-item { display: grid; grid-template-columns: 8px minmax(0,1fr) 14px; gap: 10px; margin-bottom: 8px; padding: 13px 12px; border: 1px solid #dce8f8; border-radius: 8px; background: #fff; color: #263853; text-decoration: none; }
.alert-item:hover { border-color: #8fb7f2; box-shadow: 0 6px 16px rgba(48,105,194,.09); }
.alert-item>i { width: 7px; height: 7px; margin-top: 6px; border-radius: 50%; background: #2e90fa; }
.alert-item>i.is-blocked { background: #d92d20; box-shadow: 0 0 0 4px #fee4e2; }
.alert-item>div>span { display: flex; align-items: center; gap: 7px; color: #77859b; font-size: 11px; }
.alert-item>div>span em { margin-left: auto; font-style: normal; }
.alert-item strong { display: block; margin-top: 7px; color: #233550; font-size: 13px; line-height: 20px; }
.alert-item p { margin: 4px 0 0; color: #73819a; font-size: 11px; }
.alert-item small { display: inline-flex; margin-top: 8px; padding: 2px 7px; border-radius: 999px; background: #fff3d8; color: #b54708; font-size: 10px; }
.alert-item small.is-blocked { background:#fee4e2;color:#b42318; }
.alert-item small.is-processing { background:#eaf2ff;color:#175cd3; }
.alert-item nav { display:flex;justify-content:flex-end;gap:7px;margin-top:11px;padding-top:10px;border-top:1px solid #edf2f8; }
.alert-item nav a { height:30px;padding:0 11px;border:1px solid #cbdaf0;border-radius:5px;background:#fff;color:#526783;font-size:12px;line-height:28px;text-decoration:none;white-space:nowrap; }
.alert-item nav button { height:30px;padding:0 11px;border:1px solid #d8e1ed;border-radius:5px;background:#f7f9fc;color:#98a2b3;font-size:12px;cursor:default; }
.alert-item nav a.primary { border-color:#165dff;background:#165dff;color:#fff; }
.alert-item nav a:hover { border-color:#8fb7f2;color:#165dff; }
.alert-item nav a.primary:hover { border-color:#4080ff;background:#4080ff;color:#fff; }
.alert-item__arrow { align-self: center; color: #8ea0b9; font-size: 22px; }
.alert-drawer>footer { position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; min-height: 58px; padding: 11px 18px; border-top: 1px solid #dce8f8; background: #fff; box-shadow: 0 -8px 18px rgba(42,77,128,.06); }
.alert-drawer>footer a { color: #165dff; font-size: 12px; text-decoration: none; }
.alert-drawer>footer .footer-primary { height: 32px; padding: 0 12px; border-radius: 5px; background: #165dff; color: #fff; line-height: 32px; }
.knowledge-assistant-entry { position:fixed;z-index:52;display:flex;align-items:center;gap:7px;height:42px;padding:0 14px 0 10px;border:1px solid #8fb7f2;border-radius:22px;background:#165dff;color:#fff;box-shadow:0 10px 28px rgba(22,93,255,.28);cursor:grab;touch-action:none;user-select:none; }
.knowledge-assistant-entry:hover,.knowledge-assistant-entry.active { background:#0f4fd9;transform:translateY(-1px); }.knowledge-assistant-entry svg { width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round; }.knowledge-assistant-entry span { font-size:11px;font-weight:600; }
.knowledge-assistant-entry.dragging { cursor:grabbing;transform:none;transition:none; }.knowledge-assistant { position:fixed;z-index:51;display:grid;grid-template-rows:auto minmax(0,1fr) auto auto;overflow:hidden;border:1px solid #b9d2f5;border-radius:12px;background:#f7faff;box-shadow:0 24px 64px rgba(31,69,125,.28); }
.knowledge-assistant>header { display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #dce8f8;background:linear-gradient(110deg,#eef5ff,#fff); }.knowledge-assistant>header>div { display:flex;align-items:center;gap:9px; }.knowledge-assistant>header i { display:grid;place-items:center;width:30px;height:30px;border-radius:9px;background:#165dff;color:#fff;font-size:10px;font-style:normal;font-weight:700; }.knowledge-assistant>header span { display:grid;gap:2px; }.knowledge-assistant>header strong { font-size:13px; }.knowledge-assistant>header em { color:#72819a;font-size:9px;font-style:normal; }.knowledge-assistant>header button { width:28px;height:28px;border:0;border-radius:5px;background:#edf3fb;color:#5f6f88;font-size:19px;cursor:pointer; }
.knowledge-assistant__messages { display:flex;min-height:0;gap:9px;padding:13px;overflow:auto;flex-direction:column; }.knowledge-assistant__messages article { align-self:flex-start;max-width:86%;padding:10px 11px;border:1px solid #d9e6f7;border-radius:3px 10px 10px;background:#fff;color:#344761; }.knowledge-assistant__messages article.is-user { align-self:flex-end;border-color:#165dff;border-radius:10px 3px 10px 10px;background:#165dff;color:#fff; }.knowledge-assistant__messages p { margin:0;font-size:11px;line-height:18px; }.knowledge-assistant__messages article>div { display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin-top:8px;padding-top:7px;border-top:1px solid #e7eef8; }.knowledge-assistant__messages article>div span { width:100%;color:#8491a5;font-size:8px; }.knowledge-assistant__messages article>div b { padding:2px 6px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:8px;font-weight:500; }
.knowledge-assistant__full { padding:8px 13px;border-top:1px solid #e2eaf5;background:#fff;color:#165dff;font-size:9px;text-decoration:none; }
.knowledge-assistant>form { display:grid;grid-template-columns:minmax(0,1fr) 54px;gap:8px;padding:10px;border-top:1px solid #dce8f8;background:#fff; }.knowledge-assistant textarea { box-sizing:border-box;height:54px;padding:8px 9px;border:1px solid #bdd0ea;border-radius:6px;color:#344761;font:10px/16px inherit;resize:none; }.knowledge-assistant form button { border:0;border-radius:6px;background:#165dff;color:#fff;font-size:10px;cursor:pointer; }.knowledge-assistant form button:disabled { background:#a9bee0;cursor:not-allowed; }
@media(max-width:620px){.app-user-menu{right:-2px;width:270px}}

.app-workspace {
  height: calc(100% - 42px);
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: hidden;
}

.route-error {
  display: grid;
  align-content: center;
  gap: 10px;
  height: 100%;
  padding: 32px;
  color: #b42318;
  background: #fff7f6;
  border: 1px solid #fecdca;
  border-radius: var(--radius-md);
}

.route-error strong {
  font-size: 18px;
}

.route-error span {
  color: #912018;
  overflow-wrap: anywhere;
}

@media (max-height: 820px), (max-width: 1500px) {
  .app-nav::after {
    top: 126px;
  }

  .app-nav__item {
    min-height: 44px;
  }

  .app-nav__item--sub,
  .app-nav__item--active {
    width: min(218px, calc(100% - 30px));
  }
}

@media (max-width: 1050px) {
  .app-top-actions__user span { display: none; }
  .alert-drawer { width: min(430px, 94vw); }
}

@media (max-height: 720px) {
  .app-sidebar {
    padding-bottom: 12px;
  }

  .app-nav {
    padding-bottom: 10px;
  }

  .app-nav__item {
    min-height: 40px;
    font-size: 16px;
    line-height: 23px;
  }

  .app-nav__item--sub,
  .app-nav__item--active {
    width: min(218px, calc(100% - 30px));
  }
}
</style>
