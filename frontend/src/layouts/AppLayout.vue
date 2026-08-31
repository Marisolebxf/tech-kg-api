<script setup lang="ts">
import {
  IconHistory,
  IconSwap,
} from "@arco-design/web-vue/es/icon";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onErrorCaptured,
  onMounted,
  ref,
  watch,
} from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import figmaMenuFold from "../assets/icons/figma-menu-fold.svg";
import figmaMenuUnfold from "../assets/icons/figma-menu-unfold.svg";
import accountAvatar from "../assets/icons/account-menu/avatar-default.svg";
import accountCaret from "../assets/icons/account-menu/caret-down.svg";
import accountIcon from "../assets/icons/account-menu/icon-account.svg";
import accountLockIcon from "../assets/icons/account-menu/icon-lock.svg";
import accountLogoutIcon from "../assets/icons/account-menu/icon-logout.svg";
import accountMemberStar from "../assets/icons/account-menu/icon-member-star.svg";
import iconMessage from "../assets/icons/icon-message.svg";
import iconBook from "../assets/icons/icon-book.svg";
import navOverview from "../assets/icons/nav-overview.svg";
import navGraph from "../assets/icons/nav-graph.svg";
import navSchema from "../assets/icons/nav-schema.svg";
import navQuery from "../assets/icons/nav-query.svg";
import navReview from "../assets/icons/nav-review.svg";
import navServices from "../assets/icons/nav-services.svg";
import navTasks from "../assets/icons/nav-tasks.svg";
import navTools from "../assets/icons/nav-tools.svg";
import { useAppStore } from "../stores/app";
import { useAuthStore } from "../stores/auth";
import logoKg from "../assets/images/logo-kg.png";

const route = useRoute();
const router = useRouter();
// BASE_URL 为 './' 或 '/xxx/'（都以 / 结尾）；扁平单段路由下相对解析恒指向站点根下的 docs/
const docsHref = `${import.meta.env.BASE_URL}docs/`;
const appStore = useAppStore();
const authStore = useAuthStore();
const currentUser = computed(() => authStore.profile?.user);
const userAvatar = computed(() => currentUser.value?.avatar || accountAvatar);
const isAdminUser = computed(() =>
  import.meta.env.VITE_AUTH_ENABLED === "false" || authStore.isAdmin,
);
const userRoleName = computed(() =>
  isAdminUser.value ? "管理员" : "普通用户",
);
const userDisplayName = computed(() =>
  currentUser.value?.nickname || currentUser.value?.username || userRoleName.value,
);
const userRoleDescription = computed(() =>
  isAdminUser.value ? "系统管理与审核权限" : "知识图谱业务服务",
);
const isAdminArea = computed(() => route.path.startsWith("/admin"));
const pageTitle = computed(() => String(route.meta.title ?? "亿级知识图谱"));
const routeError = ref("");
const serviceNavCollapsed = ref(false);
const alertDrawerOpen = ref(false);
const alertPreviewOpen = ref(false);
const userMenuOpen = ref(false);
const userEntryRef = ref<HTMLElement | null>(null);
const assistantEntryRef = ref<HTMLButtonElement | null>(null);
const accountFeedback = ref("");
const assistantOpen = ref(false);
const isMobile = ref(false);
const mobileNavOpen = ref(false);
const sidebarCollapsed = computed(() => appStore.collapsed && !isMobile.value);
const assistantPosition = ref({ x: 0, y: 0 });
const assistantViewport = ref({ width: 1440, height: 900 });
const businessServiceTitle = "科技专家/人才知识推理构建服务";
// 问答小助手（已隐藏）
// const assistantDragging = ref(false)
// const assistantDragMoved = ref(false)
// let assistantDragOrigin = { pointerX: 0, pointerY: 0, x: 0, y: 0 }
// const assistantQuestion = ref('')
// const assistantMessages = ref<Array<{ role: 'assistant' | 'user'; content: string; sources?: string[] }>>([
//   { role: 'assistant', content: '可询问专家、机构、论文关系，或查询任务与异常。' },
// ])
const alertItems = ref<
  Array<{
    id: string;
    blocked: boolean;
    module: string;
    title: string;
    meta: string;
    time: string;
    status: string;
    hasReviewDetail: boolean;
    detailTo: string;
    reviewTo: string;
  }>
>([]);
const serviceNavItems = [
  {
    to: "/expert-direct",
    label: "科技专家/人才直接关系",
    fullLabel: "科技专家/人才直接关系",
  },
  {
    to: "/node-indirect",
    label: "科技单节点间接关系",
    fullLabel: "科技单节点间接关系",
  },
  {
    to: "/two-point-achievement",
    label: "科技两点合作成果",
    fullLabel: "科技两点合作成果",
  },
  {
    to: "/expert-colleague",
    label: "科技专家同事关系",
    fullLabel: "科技专家同事关系",
  },
  {
    to: "/expert-alumni",
    label: "科技专家校友关系",
    fullLabel: "科技专家校友关系",
  },
  {
    to: "/paper-cooperation",
    label: "科技专家论文合作关系",
    fullLabel: "科技专家论文合作关系",
  },
  {
    to: "/enterprise-relation",
    label: "重点关注科技企业关系",
    fullLabel: "重点关注科技企业关系",
  },
  {
    to: "/industry-chain-event",
    label: "科技产业链点TOP-N事件关系",
    fullLabel: "科技产业链点TOP-N事件关系",
  },
  {
    to: "/industry-chain-panorama",
    label: "科技产业链全景图",
    fullLabel: "科技产业链全景图",
  },
];
const showServiceNavItems = computed(
  () => !sidebarCollapsed.value && !serviceNavCollapsed.value,
);
const isBusinessServiceRoute = computed(() =>
  serviceNavItems.some((item) => item.to === route.path),
);
const currentServiceNavItem = computed(() =>
  serviceNavItems.find((item) => item.to === route.path),
);
const breadcrumbItems = computed(() => {
  if (route.query.breadcrumb === "business-service")
    return [
      { label: "页面总览", to: "/overview" },
      { label: businessServiceTitle },
    ];
  if (currentServiceNavItem.value)
    return [
      { label: "页面总览", to: "/overview" },
      { label: businessServiceTitle, to: "/business-service" },
      { label: currentServiceNavItem.value.fullLabel },
    ];
  return [{ label: pageTitle.value }];
});

function navIconStyle(icon: string) {
  return { "--nav-icon": `url("${icon}")` };
}

function refreshSubNavOverflow() {
  const wraps = document.querySelectorAll<HTMLElement>(".app-nav__marquee");
  wraps.forEach((wrap) => {
    const label = wrap.querySelector<HTMLElement>(".app-nav__marquee-label");
    if (!label) return;
    const overflow = Math.ceil(label.scrollWidth - wrap.clientWidth);
    if (overflow > 1) {
      const pixelsPerSecond = 24;
      const movingPart = 0.8;
      const duration = overflow / (pixelsPerSecond * movingPart);
      wrap.classList.add("is-overflowing");
      wrap.style.setProperty("--sub-scroll-distance", `-${overflow + 1}px`);
      wrap.style.setProperty("--marquee-duration", `${duration.toFixed(2)}s`);
    } else {
      wrap.classList.remove("is-overflowing");
      wrap.style.removeProperty("--sub-scroll-distance");
      wrap.style.removeProperty("--marquee-duration");
    }
  });
}

watch([() => appStore.collapsed, serviceNavCollapsed, () => route.path], () => {
  if (showServiceNavItems.value) {
    void nextTick(refreshSubNavOverflow);
  }
});
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
  routeError.value = error instanceof Error ? error.message : String(error);
  return false;
});

function openAlertDrawer() {
  alertPreviewOpen.value = false;
  userMenuOpen.value = false;
  assistantOpen.value = false;
  alertDrawerOpen.value = true;
}

function toggleUserMenu() {
  alertPreviewOpen.value = false;
  const willOpen = !userMenuOpen.value;
  if (willOpen) accountFeedback.value = "";
  userMenuOpen.value = willOpen;
}

async function switchPortal() {
  userMenuOpen.value = false;
  await router.push(isAdminArea.value ? "/overview" : "/admin/reviews");
}

async function handleAccountAction(
  action: "个人中心" | "账号与安全" | "操作记录" | "退出登录",
) {
  userMenuOpen.value = false;
  if (action === "个人中心") {
    await router.push("/user-center");
    return;
  }
  if (action === "账号与安全") {
    await router.push("/account-security");
    return;
  }
  if (action === "操作记录") {
    await router.push("/operation-logs");
    return;
  }
  if (action === "退出登录") {
    accountFeedback.value = "正在安全退出系统。";
    await authStore.logout();
    await router.replace("/login");
    return;
  }
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
  const entryWidth = assistantEntryRef.value?.offsetWidth ?? 126;
  const entryHeight = assistantEntryRef.value?.offsetHeight ?? 42;
  return {
    x: Math.max(
      8,
      Math.min(assistantViewport.value.width - entryWidth - 8, position.x),
    ),
    y: Math.max(
      8,
      Math.min(assistantViewport.value.height - entryHeight - 8, position.y),
    ),
  };
}

function placeAssistantAtDefault() {
  assistantPosition.value = clampAssistantPosition({
    x: Number.POSITIVE_INFINITY,
    y: Number.POSITIVE_INFINITY,
  });
}

function handleViewportResize() {
  const mobile = window.matchMedia("(max-width: 767px)").matches;
  if (!mobile) mobileNavOpen.value = false;
  isMobile.value = mobile;
  assistantViewport.value = {
    width: window.innerWidth,
    height: window.innerHeight,
  };
  assistantPosition.value = clampAssistantPosition(assistantPosition.value);
  void nextTick(refreshSubNavOverflow);
}

function handleVisibilityChange() {
  if (document.visibilityState === "visible") handleViewportResize();
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (userMenuOpen.value && !userEntryRef.value?.contains(event.target as Node))
    userMenuOpen.value = false;
}

function toggleNavigation() {
  if (isMobile.value) {
    mobileNavOpen.value = !mobileNavOpen.value;
    return;
  }
  appStore.toggleCollapsed();
}

function closeMobileNavigation() {
  mobileNavOpen.value = false;
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

watch(
  () => route.fullPath,
  () => {
    alertDrawerOpen.value = false;
    alertPreviewOpen.value = false;
    userMenuOpen.value = false;
    mobileNavOpen.value = false;
  },
);

onMounted(() => {
  isMobile.value = window.matchMedia("(max-width: 767px)").matches;
  assistantViewport.value = {
    width: window.innerWidth,
    height: window.innerHeight,
  };
  placeAssistantAtDefault();
  window.addEventListener("resize", handleViewportResize);
  window.addEventListener("focus", handleViewportResize);
  window.addEventListener("pageshow", handleViewportResize);
  window.visualViewport?.addEventListener("resize", handleViewportResize);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  window.requestAnimationFrame(handleViewportResize);
  void nextTick(refreshSubNavOverflow);
  void document.fonts.ready.then(refreshSubNavOverflow);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleViewportResize);
  window.removeEventListener("focus", handleViewportResize);
  window.removeEventListener("pageshow", handleViewportResize);
  window.visualViewport?.removeEventListener("resize", handleViewportResize);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
});
</script>

<template>
  <div class="app-viewport">
    <div
      class="app-shell"
      :class="{
        'is-collapsed': appStore.collapsed && !isMobile,
        'is-mobile-nav-open': mobileNavOpen,
      }"
    >
      <button
        v-if="mobileNavOpen"
        class="app-sidebar-mask"
        type="button"
        aria-label="关闭导航"
        @click="closeMobileNavigation"
      />
      <aside class="app-sidebar" :aria-hidden="isMobile && !mobileNavOpen">
        <div class="app-brand">
          <img class="app-brand__logo" :src="logoKg" alt="知识图谱平台" />
          <div v-if="!sidebarCollapsed" class="app-brand__name">
            知识图谱平台
          </div>
        </div>

        <nav class="app-nav" aria-label="平台功能导航">
          <template v-if="isAdminArea">
            <div v-if="!sidebarCollapsed" class="app-nav__group">
              <span>工作台</span>
            </div>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/admin/corrections"
              :title="sidebarCollapsed ? '修正记录' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navReview)"
                aria-hidden="true"
              ></span
              ><span v-if="!sidebarCollapsed">修正记录</span>
            </RouterLink>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/admin/reviews"
              :title="sidebarCollapsed ? '审核与同步' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navTasks)"
                aria-hidden="true"
              ></span
              ><span v-if="!sidebarCollapsed">审核与同步</span>
            </RouterLink>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/admin/members"
              :title="sidebarCollapsed ? '成员管理' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navTools)"
                aria-hidden="true"
              ></span
              ><span v-if="!sidebarCollapsed">成员管理</span>
            </RouterLink>
          </template>
          <template v-else>
            <div v-if="!sidebarCollapsed" class="app-nav__group">
              <span>工作台</span>
            </div>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/overview"
              :title="sidebarCollapsed ? '平台总览' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navOverview)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">平台总览</span>
            </RouterLink>

            <div v-if="!sidebarCollapsed" class="app-nav__group">
              <span>图谱建设与治理</span>
            </div>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/schema"
              :title="sidebarCollapsed ? 'Schema 管理' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navSchema)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">Schema 管理</span>
            </RouterLink>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/graph-build"
              :title="sidebarCollapsed ? '图谱构建' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navGraph)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">图谱构建</span>
            </RouterLink>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/manual-review"
              :title="sidebarCollapsed ? '人工审核' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navReview)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">人工审核</span>
            </RouterLink>

            <div v-if="!sidebarCollapsed" class="app-nav__group">
              <span>平台管理</span>
            </div>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/configurations"
              :title="sidebarCollapsed ? '配置管理' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navTools)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">配置管理</span>
            </RouterLink>

            <div v-if="!sidebarCollapsed" class="app-nav__group">
              <span>查询与服务</span>
            </div>
            <RouterLink
              class="app-nav__item app-nav__item--top app-nav__item--leaf"
              active-class="app-nav__item--active"
              to="/graph-query"
              :title="sidebarCollapsed ? '图谱查询' : undefined"
            >
              <span
                class="app-nav__icon"
                :style="navIconStyle(navQuery)"
                aria-hidden="true"
              ></span>
              <span v-if="!sidebarCollapsed">图谱查询</span>
            </RouterLink>
            <div class="app-nav__service-group">
              <button
                class="app-nav__item app-nav__item--top app-nav__item--button"
                :class="{
                  'app-nav__item--open': !serviceNavCollapsed,
                  'app-nav__item--context': isBusinessServiceRoute,
                }"
                type="button"
                :title="sidebarCollapsed ? businessServiceTitle : undefined"
                :aria-expanded="
                  sidebarCollapsed ? undefined : !serviceNavCollapsed
                "
                @click="serviceNavCollapsed = !serviceNavCollapsed"
              >
                <span
                  class="app-nav__icon"
                  :style="navIconStyle(navServices)"
                  aria-hidden="true"
                ></span>
                <span v-if="!sidebarCollapsed" class="app-nav__service-title app-nav__marquee"><span class="app-nav__service-title-label app-nav__marquee-label">{{ businessServiceTitle }}</span></span>
                <svg
                  v-if="!sidebarCollapsed"
                  class="app-nav__arrow"
                  viewBox="0 0 16 16"
                  aria-hidden="true"
                >
                  <path d="m4 6 4 4 4-4" />
                </svg>
              </button>
              <template v-if="showServiceNavItems">
                <RouterLink
                  v-for="item in serviceNavItems"
                  :key="item.to"
                  class="app-nav__item app-nav__item--sub"
                  active-class="app-nav__item--active"
                  :to="item.to"
                  :title="item.fullLabel"
                >
                  <span class="app-nav__sub-wrap app-nav__marquee"
                    ><span class="app-nav__sub-label app-nav__marquee-label">{{
                      item.label
                    }}</span></span
                  >
                </RouterLink>
              </template>
              <aside
                v-if="sidebarCollapsed"
                class="app-nav__flyout"
                :aria-label="`${businessServiceTitle}子功能`"
              >
                <strong>{{ businessServiceTitle }}</strong>
                <RouterLink
                  v-for="item in serviceNavItems"
                  :key="`flyout-${item.to}`"
                  active-class="app-nav__flyout-item--active"
                  :to="item.to"
                  >{{ item.fullLabel }}</RouterLink
                >
              </aside>
            </div>
          </template>
        </nav>
      </aside>

      <main
        class="app-main"
        :class="{ 'is-overview-page': route.path === '/overview' }"
      >
        <div class="app-top-actions">
          <button
            class="app-shell__menu"
            type="button"
            :aria-label="isMobile ? (mobileNavOpen ? '关闭导航' : '打开导航') : appStore.collapsed ? '展开导航' : '收起导航'"
            :aria-expanded="isMobile ? mobileNavOpen : undefined"
            @click="toggleNavigation"
          >
            <img
              :src="appStore.collapsed ? figmaMenuUnfold : figmaMenuFold"
              alt=""
              aria-hidden="true"
            />
            <span v-if="isMobile">目录</span>
          </button>
          <div class="app-top-actions__right">
            <a
              class="app-docs-link"
              :href="docsHref"
              target="_blank"
              rel="noopener"
              aria-label="打开文档中心（新标签页）"
              title="文档中心"
            >
              <img :src="iconBook" alt="" aria-hidden="true" />
            </a>
            <div
              class="app-alert-entry"
              @mouseenter="alertPreviewOpen = !alertDrawerOpen"
              @mouseleave="alertPreviewOpen = false"
            >
              <button
                class="app-alert-bell"
                type="button"
                :aria-label="`${alertItems.length} 条消息通知`"
                :aria-expanded="alertDrawerOpen"
                @click="openAlertDrawer"
              >
                <img :src="iconMessage" alt="" aria-hidden="true" />
                <b v-if="alertItems.length">{{ alertItems.length }}</b>
              </button>
              <aside
                v-if="alertPreviewOpen"
                class="alert-preview"
                aria-label="消息通知概览"
              >
                <header>
                  <div><strong>消息通知</strong></div>
                </header>
                <div class="notification-empty">
                  {{
                    alertItems.length
                      ? `${alertItems.length} 条新消息`
                      : "暂无消息"
                  }}
                </div>
              </aside>
            </div>
            <div ref="userEntryRef" class="app-user-entry">
              <button
                class="app-top-actions__user"
                type="button"
                :aria-label="`当前登录用户：${userRoleName}${userDisplayName}`"
                :aria-expanded="userMenuOpen"
                @click="toggleUserMenu"
              >
                <img
                  class="app-user-avatar"
                  :src="userAvatar"
                  alt=""
                  aria-hidden="true"
                />
                <span><strong>{{ userRoleName }}</strong></span>
                <img
                  class="app-user-caret"
                  :src="accountCaret"
                  alt=""
                  aria-hidden="true"
                />
              </button>
              <aside
                v-if="userMenuOpen"
                class="app-user-menu"
                aria-label="账号菜单"
              >
                <header>
                  <div class="app-user-menu__identity">
                    <div class="app-user-menu__title">
                      <strong>{{ userDisplayName }}</strong>
                      <b :class="{ 'is-admin': isAdminUser }">
                        <img
                          :src="accountMemberStar"
                          alt=""
                          aria-hidden="true"
                        />
                        <span>{{ userRoleName }}</span>
                      </b>
                    </div>
                    <span class="app-user-menu__description">{{
                      userRoleDescription
                    }}</span>
                  </div>
                </header>
                <nav>
                  <button
                    v-if="isAdminUser"
                    class="portal-switch"
                    type="button"
                    @click="switchPortal"
                  >
                    <IconSwap class="app-user-menu__icon" />
                    <span>{{ isAdminArea ? "返回用户端" : "进入管理端" }}</span>
                  </button>
                  <button
                    :class="{ active: route.path === '/user-center' }"
                    type="button"
                    @click="handleAccountAction('个人中心')"
                  >
                    <img
                      class="app-user-menu__icon"
                      :src="accountIcon"
                      alt=""
                      aria-hidden="true"
                    />
                    <span>账号信息</span>
                  </button>
                  <button
                    :class="{ active: route.path === '/account-security' }"
                    type="button"
                    @click="handleAccountAction('账号与安全')"
                  >
                    <img
                      class="app-user-menu__icon"
                      :src="accountLockIcon"
                      alt=""
                      aria-hidden="true"
                    />
                    <span>账号与安全</span>
                  </button>
                  <button
                    :class="{ active: route.path === '/operation-logs' }"
                    type="button"
                    @click="handleAccountAction('操作记录')"
                  >
                    <IconHistory class="app-user-menu__icon" />
                    <span>操作记录</span>
                  </button>
                  <button
                    type="button"
                    @click="handleAccountAction('退出登录')"
                  >
                    <img
                      class="app-user-menu__icon"
                      :src="accountLogoutIcon"
                      alt=""
                      aria-hidden="true"
                    />
                    <span>退出登录</span>
                  </button>
                </nav>
                <footer v-if="accountFeedback">{{ accountFeedback }}</footer>
              </aside>
            </div>
          </div>
        </div>
        <section class="app-stage">
          <div class="app-breadcrumb" aria-label="当前位置">
            <template
              v-for="(item, index) in breadcrumbItems"
              :key="`${item.label}-${index}`"
            >
              <span
                v-if="index > 0"
                class="app-breadcrumb__separator"
                aria-hidden="true"
                >/</span
              >
              <RouterLink
                v-if="item.to"
                class="app-breadcrumb__history"
                :to="item.to"
                >{{ item.label }}</RouterLink
              >
              <span v-else class="app-breadcrumb__current" aria-current="page">
                {{ item.label }}
              </span>
            </template>
          </div>
          <section class="app-workspace" :aria-label="pageTitle">
            <div v-if="routeError" class="route-error">
              <strong>页面渲染异常</strong>
              <span>{{ routeError }}</span>
            </div>
            <RouterView v-else />
          </section>
        </section>
      </main>
      <button
        v-if="alertDrawerOpen"
        class="alert-drawer-mask"
        type="button"
        aria-label="关闭消息通知"
        @click="alertDrawerOpen = false"
      />
      <aside v-if="alertDrawerOpen" class="alert-drawer" aria-label="消息通知">
        <header>
          <div>
            <h2>消息通知</h2>
            <p>
              {{
                alertItems.length
                  ? `${alertItems.length} 条新消息`
                  : "暂无新消息"
              }}
            </p>
          </div>
          <button
            type="button"
            aria-label="关闭"
            @click="alertDrawerOpen = false"
          >
            ×
          </button>
        </header>
        <div class="alert-drawer__list">
          <p v-if="!alertItems.length" class="notification-empty">暂无消息</p>
          <article v-for="item in alertItems" :key="item.id" class="alert-item">
            <i></i>
            <div>
              <span
                >{{ item.module }}<em>{{ item.time }}</em></span
              ><strong>{{ item.title }}</strong>
              <p>{{ item.meta }}</p>
              <small>{{ item.status }}</small>
              <nav>
                <template v-if="item.hasReviewDetail"
                  ><RouterLink :to="item.detailTo">查看详情</RouterLink
                  ><RouterLink class="primary" :to="item.reviewTo"
                    >处理</RouterLink
                  ></template
                ><button v-else type="button" disabled>查看详情</button>
              </nav>
            </div>
          </article>
        </div>
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
  scrollbar-gutter: auto;
  background: var(--gkx-bg-page);
}

.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  scrollbar-gutter: auto;
  background: var(--gkx-bg-page);
  transition: grid-template-columns 0.2s ease;
}

.app-shell.is-collapsed {
  grid-template-columns: var(--sidebar-width-collapsed) minmax(0, 1fr);
}

.app-sidebar {
  z-index: 30;
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  padding: 0 16px 16px;
  overflow: visible;
  color: var(--text-primary);
  background: var(--gkx-bg-page);
  box-shadow: none;
}

.app-sidebar::before {
  display: none;
}

.app-sidebar > * {
  position: relative;
}

.app-brand {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--header-height);
  padding: 0;
  border-bottom: 0;
}

.app-brand__logo {
  box-sizing: border-box;
  width: 32px;
  height: 32px;
  padding: 2px;
  object-fit: contain;
}

.app-brand__name {
  flex: 0 0 auto;
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
  color: var(--gkx-text-primary);
  white-space: nowrap;
}

.app-shell.is-collapsed .app-brand {
  justify-content: center;
}

.app-shell.is-collapsed .app-nav__item {
  grid-template-columns: 20px;
  justify-content: center;
  width: 52px;
  min-height: 40px;
  margin-left: 0;
  padding-inline: 0;
  transform: none;
}

.app-shell.is-collapsed .app-nav__item--active {
  width: 52px;
  margin-left: 0;
}

.app-shell.is-collapsed .app-nav__item--open {
  margin-top: 0;
}

.app-nav {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding: 0 4px 14px 0;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: none;
}

.app-nav::-webkit-scrollbar {
  display: none;
}

.app-nav::-webkit-scrollbar-track {
  background: transparent;
}

.app-nav::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: rgba(84, 139, 220, 0.42);
}

.app-shell.is-collapsed .app-nav {
  overflow: visible;
}

.app-nav::after {
  display: none;
}

.app-nav__item {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 14px;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  color: #1d2129;
  font-size: 14px;
  line-height: 22px;
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
  border-color: var(--gkx-primary);
  background: rgba(255, 255, 255, 0.72);
}

.app-nav__item:hover {
  color: var(--gkx-primary);
  border-color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.56);
}

.app-nav__item:focus-visible,
.app-shell__menu:focus-visible {
  outline: none;
}

.app-nav__group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 16px 8px 8px;
  padding-top: 0;
  border-top: 0;
  color: var(--gkx-text-tertiary);
  font-size: 12px;
  line-height: 20px;
  font-weight: 500;
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
  letter-spacing: 0.02em;
}

.app-nav__icon {
  display: block;
  width: 20px;
  height: 20px;
  align-self: center;
  justify-self: center;
  background: currentColor;
  color: #4e5969;
  -webkit-mask-image: var(--nav-icon);
  mask-image: var(--nav-icon);
  -webkit-mask-position: center;
  mask-position: center;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-size: 16px 16px;
  mask-size: 16px 16px;
}

.app-nav__arrow {
  width: 16px;
  height: 16px;
  justify-self: end;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  transform: rotate(-90deg);
  transition: transform 0.16s ease;
}

.app-nav__item--leaf {
  grid-template-columns: 20px minmax(0, 1fr);
}

.app-nav__item--open .app-nav__arrow {
  transform: rotate(0);
}

.app-nav__item--active {
  position: relative;
  z-index: 1;
  grid-template-columns: 1fr;
  width: 100%;
  margin-left: 0;
  color: var(--gkx-primary);
  border-color: #fff;
  background:
    linear-gradient(
      106deg,
      rgba(255, 255, 255, 0) 39%,
      rgba(22, 93, 255, 0.2) 114%
    ),
    rgba(255, 255, 255, 0.48);
  box-shadow: 0 1px 12px rgba(83, 98, 144, 0.08);
}

.app-nav__item--active .app-nav__icon,
.app-nav__item--active .app-nav__arrow {
  color: var(--gkx-primary);
}

.app-nav__item--context {
  color: var(--gkx-primary);
  font-weight: 500;
}

.app-nav__item--context .app-nav__icon,
.app-nav__item--context .app-nav__arrow,
.app-nav__item:hover .app-nav__icon,
.app-nav__item:hover .app-nav__arrow {
  color: var(--gkx-primary);
}

.app-nav__item--top.app-nav__item--active {
  grid-template-columns: 20px minmax(0, 1fr) 14px;
  width: 100%;
  margin-left: 0;
}

.app-nav__item--top.app-nav__item--leaf.app-nav__item--active {
  grid-template-columns: 20px minmax(0, 1fr);
}

.app-shell.is-collapsed .app-nav__item.app-nav__item--active {
  grid-template-columns: 20px;
  justify-content: center;
}

.app-nav__item--sub {
  position: relative;
  z-index: 1;
  grid-template-columns: minmax(0, 1fr);
  width: 100%;
  height: 40px;
  min-height: 40px;
  margin: 2px 0;
  padding: 0 12px 0 40px;
  border-color: transparent;
  background: transparent;
  color: var(--gkx-text-secondary);
  font-size: 14px;
  line-height: 22px;
}

.app-nav__sub-wrap {
  display: flex;
  align-items: center;
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.app-nav__sub-label {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  height: 100%;
  line-height: 22px;
  white-space: nowrap;
  will-change: transform;
}

.app-nav__service-title {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.app-nav__service-title-label {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  height: 100%;
  white-space: nowrap;
  will-change: transform;
}

.app-nav__marquee.is-overflowing:hover .app-nav__marquee-label,
.app-nav__item:focus-visible .app-nav__marquee.is-overflowing .app-nav__marquee-label {
  animation: app-nav-marquee var(--marquee-duration, 5s) linear infinite alternate;
}

@keyframes app-nav-marquee {
  0%, 10% { transform: translateX(0); }
  90%, 100% { transform: translateX(var(--sub-scroll-distance, 0)); }
}

@media (prefers-reduced-motion: reduce) {
  .app-nav__marquee.is-overflowing:hover .app-nav__marquee-label,
  .app-nav__item:focus-visible .app-nav__marquee.is-overflowing .app-nav__marquee-label {
    animation: none;
  }
}

.app-nav__service-group {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.app-nav__flyout {
  position: absolute;
  z-index: 80;
  top: 0;
  left: calc(100% + 12px);
  display: grid;
  width: 190px;
  padding: 8px;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(29, 33, 41, 0.14);
  opacity: 0;
  pointer-events: none;
  transform: translateX(-4px);
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}

.app-nav__service-group:hover .app-nav__flyout,
.app-nav__service-group:focus-within .app-nav__flyout {
  opacity: 1;
  pointer-events: auto;
  transform: none;
}

.app-nav__flyout strong {
  padding: 6px 8px;
  color: #1d2129;
  font-size: 14px;
  line-height: 22px;
  font-weight: 500;
}

.app-nav__flyout a {
  display: flex;
  align-items: center;
  min-height: 36px;
  padding: 0 8px;
  border-radius: 4px;
  color: #4e5969;
  font-size: 14px;
  line-height: 22px;
  text-decoration: none;
}

.app-nav__flyout a:hover,
.app-nav__flyout .app-nav__flyout-item--active {
  background: #e8f3ff;
  color: #165dff;
}

.app-shell.is-collapsed .app-nav__item--context {
  border-color: #fff;
  background: rgba(255, 255, 255, 0.72);
}

.app-nav__item--sub span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-nav__item--sub.app-nav__item--active {
  color: var(--gkx-primary);
  border: 1px solid rgba(255, 255, 255, 0.92);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: none;
}

.app-main {
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 0 0 var(--space-16) 0;
  overflow: hidden;
  scrollbar-gutter: auto;
}

.app-top-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  height: var(--header-height);
  margin-bottom: 0;
  padding: 0;
}

.app-shell__menu {
  display: inline-grid;
  place-items: center;
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
}

.app-shell__menu:hover {
  background: rgba(255, 255, 255, 0.56);
}

.app-shell__menu img {
  display: block;
  width: 24px;
  height: 24px;
}

.app-top-actions__user {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 4px 8px 4px 4px;
  border: 0;
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.48);
  color: #1d2129;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
}

.app-top-actions__user > .app-user-avatar {
  display: block;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}
.app-top-actions__user > span {
  display: inline-flex;
  align-items: center;
  line-height: 22px;
}
.app-top-actions__user strong {
  color: #1d2129;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}
.app-top-actions__user > .app-user-caret {
  display: block;
  flex: 0 0 12px;
  width: 12px;
  height: 12px;
  margin-left: 2px;
  object-fit: contain;
}
.app-top-actions__user[aria-expanded="true"]:focus-visible {
  outline: none;
}
.app-user-entry {
  position: relative;
  z-index: 38;
}
.app-user-menu {
  position: absolute;
  z-index: 48;
  top: 45px;
  right: 0;
  width: 200px;
  overflow: hidden;
  border: 0;
  border-radius: 4px;
  background: #fff;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  color: #1d2129;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
.app-user-menu > header {
  padding: 16px 16px 12px;
  border-bottom: 1px solid #e5e6eb;
  background: #fff;
}
.app-user-menu__identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.app-user-menu__title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.app-user-menu__title > strong {
  min-width: 0;
  overflow: hidden;
  color: #1d2129;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-user-menu__title > b {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
  height: 20px;
  padding: 0 7px 0 4px;
  border-radius: 14px;
  background: linear-gradient(90deg, #ebbd8c 0%, #f7d9b5 100%);
  color: #7d5121;
  font-size: 12px;
  font-weight: 400;
  line-height: 20px;
}
.app-user-menu__title > b img {
  display: block;
  width: 14px;
  height: 14px;
}
.app-user-menu__description {
  overflow: hidden;
  color: #86909c;
  font-size: 12px;
  font-weight: 400;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-user-menu nav {
  display: grid;
  gap: 4px;
  padding: 8px 16px 16px;
}
.app-user-menu nav button {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  width: 168px;
  height: 32px;
  padding: 0 20px 0 8px;
  border: 0;
  border-radius: 4px;
  background: #fff;
  color: #1d2129;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}
.app-user-menu nav button:hover {
  background: #f2f3f5;
}
.app-user-menu nav button > .app-user-menu__icon {
  display: block;
  flex: 0 0 16px;
  width: 16px;
  height: 16px;
  color: #4e5969;
  object-fit: contain;
}
.app-user-menu nav button span {
  overflow: hidden;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-user-menu nav button.active {
  background: #e8f3ff;
}

.app-user-menu > footer {
  padding: 8px 16px 12px;
  border-top: 1px solid #e5e6eb;
  background: #fff;
  color: #86909c;
  font-size: 12px;
  line-height: 20px;
}

.app-top-actions__right {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
  margin-right: 16px;
}
.app-alert-entry {
  position: relative;
  z-index: 38;
  display: inline-flex;
}
.app-docs-link {
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 4px;
  color: #86909c;
  cursor: pointer;
}
.app-docs-link:hover {
  background: rgba(255, 255, 255, 0.48);
}
.app-docs-link > img {
  width: 16px;
  height: 16px;
  object-fit: contain;
  opacity: 0.72;
}
.app-alert-bell {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #86909c;
  cursor: pointer;
}
.app-alert-bell:hover,
.app-alert-bell[aria-expanded="true"] {
  background: rgba(255, 255, 255, 0.48);
}
.app-alert-bell > img {
  width: 16px;
  height: 16px;
  object-fit: contain;
  opacity: 0.72;
}
.app-alert-bell b {
  position: absolute;
  top: -3px;
  right: -4px;
  display: grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border: 2px solid #d8e7fc;
  border-radius: 9px;
  background: #d92d20;
  color: #fff;
  font-size: 9px;
  line-height: 1;
}
.alert-preview {
  position: absolute;
  z-index: 45;
  top: 38px;
  right: -8px;
  width: 350px;
  overflow: hidden;
  border: 1px solid #c8daf4;
  border-radius: 9px;
  background: #fff;
  box-shadow: 0 18px 45px rgba(34, 74, 132, 0.2);
  color: #263853;
}
.alert-preview::before {
  position: absolute;
  top: -6px;
  right: 17px;
  width: 11px;
  height: 11px;
  border-top: 1px solid #c8daf4;
  border-left: 1px solid #c8daf4;
  background: #fff;
  content: "";
  transform: rotate(45deg);
}
.alert-preview > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 14px;
  border-bottom: 1px solid #e1eaf6;
}
.alert-preview > header > div {
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-preview > header strong {
  font-size: 14px;
}
.alert-preview > header span {
  padding: 2px 6px;
  border-radius: 999px;
  background: #e9f8ef;
  color: #067647;
  font-size: 9px;
}
.alert-preview > header em {
  color: #7a899f;
  font-size: 9px;
  font-style: normal;
}
.alert-preview > section {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 7px;
  padding: 10px 12px;
  background: #f7faff;
}
.alert-preview > section article {
  display: grid;
  gap: 2px;
  padding: 9px;
  border: 1px solid #dce8f8;
  border-radius: 6px;
  background: #fff;
}
.alert-preview > section article strong {
  color: #165dff;
  font-size: 18px;
}
.alert-preview > section article.danger strong {
  color: #d92d20;
}
.alert-preview > section article span {
  color: #71809a;
  font-size: 9px;
}
.alert-preview > div {
  padding: 5px 12px 9px;
}
.alert-preview > div p {
  display: grid;
  grid-template-columns: 7px minmax(0, 1fr);
  gap: 9px;
  margin: 0;
  padding: 8px 2px;
  border-bottom: 1px solid #edf2f8;
}
.alert-preview > div p:last-child {
  border-bottom: 0;
}
.alert-preview > div p > i {
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: #f79009;
}
.alert-preview > div p span {
  display: grid;
  gap: 2px;
}
.alert-preview > div p strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.alert-preview > div p em {
  color: #8592a6;
  font-size: 9px;
  font-style: normal;
}

.alert-drawer-mask {
  position: fixed;
  z-index: 39;
  inset: 0;
  border: 0;
  background: rgba(16, 36, 76, 0.18);
  cursor: default;
}
.alert-drawer {
  position: fixed;
  z-index: 40;
  top: 0;
  right: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  width: 430px;
  height: 100vh;
  padding: 0;
  border-left: 1px solid #c8daf4;
  background: #f8fbff;
  box-shadow: -18px 0 42px rgba(34, 74, 132, 0.2);
}
.alert-drawer > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px 20px 15px;
  border-bottom: 1px solid #dce8f8;
  background: #fff;
}
.alert-drawer h2 {
  margin: 0;
  color: #152642;
  font-size: 19px;
}
.alert-drawer header p {
  margin: 4px 0 0;
  color: #73819a;
  font-size: 12px;
}
.alert-drawer header button {
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 5px;
  background: #f2f6fc;
  color: #60708b;
  font-size: 21px;
  cursor: pointer;
}
.alert-drawer__filter {
  display: flex;
  gap: 5px;
  padding: 10px 16px;
  border-bottom: 1px solid #dce8f8;
  background: #fff;
}
.alert-drawer__filter button {
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #66758f;
  font-size: 12px;
  cursor: pointer;
}
.alert-drawer__filter button.active {
  background: #eaf2ff;
  color: #165dff;
  font-weight: 600;
}
.alert-drawer__list {
  overflow: auto;
  padding: 10px;
}
.alert-item {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) 14px;
  gap: 10px;
  margin-bottom: 8px;
  padding: 13px 12px;
  border: 1px solid #dce8f8;
  border-radius: 8px;
  background: #fff;
  color: #263853;
  text-decoration: none;
}
.alert-item:hover {
  border-color: #8fb7f2;
  box-shadow: 0 6px 16px rgba(48, 105, 194, 0.09);
}
.alert-item > i {
  width: 7px;
  height: 7px;
  margin-top: 6px;
  border-radius: 50%;
  background: #2e90fa;
}
.alert-item > i.is-blocked {
  background: #d92d20;
  box-shadow: 0 0 0 4px #fee4e2;
}
.alert-item > div > span {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #77859b;
  font-size: 11px;
}
.alert-item > div > span em {
  margin-left: auto;
  font-style: normal;
}
.alert-item strong {
  display: block;
  margin-top: 7px;
  color: #233550;
  font-size: 13px;
  line-height: 20px;
}
.alert-item p {
  margin: 4px 0 0;
  color: #73819a;
  font-size: 11px;
}
.alert-item small {
  display: inline-flex;
  margin-top: 8px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #fff3d8;
  color: #b54708;
  font-size: 10px;
}
.alert-item small.is-blocked {
  background: #fee4e2;
  color: #b42318;
}
.alert-item small.is-processing {
  background: #eaf2ff;
  color: #175cd3;
}
.alert-item nav {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
  margin-top: 11px;
  padding-top: 10px;
  border-top: 1px solid #edf2f8;
}
.alert-item nav a {
  height: 30px;
  padding: 0 11px;
  border: 1px solid #cbdaf0;
  border-radius: 5px;
  background: #fff;
  color: #526783;
  font-size: 12px;
  line-height: 28px;
  text-decoration: none;
  white-space: nowrap;
}
.alert-item nav button {
  height: 30px;
  padding: 0 11px;
  border: 1px solid #d8e1ed;
  border-radius: 5px;
  background: #f7f9fc;
  color: #98a2b3;
  font-size: 12px;
  cursor: default;
}
.alert-item nav a.primary {
  border-color: #165dff;
  background: #165dff;
  color: #fff;
}
.alert-item nav a:hover {
  border-color: #8fb7f2;
  color: #165dff;
}
.alert-item nav a.primary:hover {
  border-color: #4080ff;
  background: #4080ff;
  color: #fff;
}
.alert-item__arrow {
  align-self: center;
  color: #8ea0b9;
  font-size: 22px;
}
.alert-drawer > footer {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 58px;
  padding: 11px 18px;
  border-top: 1px solid #dce8f8;
  background: #fff;
  box-shadow: 0 -8px 18px rgba(42, 77, 128, 0.06);
}
.alert-drawer > footer a {
  color: #165dff;
  font-size: 12px;
  text-decoration: none;
}
.alert-drawer > footer .footer-primary {
  height: 32px;
  padding: 0 12px;
  border-radius: 5px;
  background: #165dff;
  color: #fff;
  line-height: 32px;
}
.alert-preview,
.alert-preview *,
.alert-drawer,
.alert-drawer * {
  color: #1d2129;
}
.alert-preview .notification-empty,
.alert-drawer .notification-empty {
  margin: 0;
  padding: 24px 16px;
  color: #1d2129;
  font-size: 12px;
  text-align: center;
}
.alert-drawer {
  grid-template-rows: auto minmax(0, 1fr);
  background: #fff;
}
.alert-drawer header p,
.alert-drawer h2,
.alert-item > div > span,
.alert-item p,
.alert-item small,
.alert-item nav a,
.alert-drawer > footer a {
  color: #1d2129;
}
.alert-item > i,
.alert-item > i.is-blocked {
  background: #1d2129;
  box-shadow: none;
}
.alert-item small,
.alert-item small.is-blocked,
.alert-item small.is-processing {
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: #1d2129;
}
.knowledge-assistant-entry {
  position: fixed;
  z-index: 52;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 42px;
  padding: 0 14px 0 10px;
  border: 1px solid #8fb7f2;
  border-radius: 22px;
  background: #165dff;
  color: #fff;
  box-shadow: 0 10px 28px rgba(22, 93, 255, 0.28);
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.knowledge-assistant-entry:hover,
.knowledge-assistant-entry.active {
  background: #0f4fd9;
  transform: translateY(-1px);
}
.knowledge-assistant-entry svg {
  width: 24px;
  height: 24px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.knowledge-assistant-entry span {
  font-size: 11px;
  font-weight: 600;
}
.knowledge-assistant-entry.dragging {
  cursor: grabbing;
  transform: none;
  transition: none;
}
.knowledge-assistant {
  position: fixed;
  z-index: 51;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  overflow: hidden;
  border: 1px solid #b9d2f5;
  border-radius: 12px;
  background: #f7faff;
  box-shadow: 0 24px 64px rgba(31, 69, 125, 0.28);
}
.knowledge-assistant > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 14px;
  border-bottom: 1px solid #dce8f8;
  background: linear-gradient(110deg, #eef5ff, #fff);
}
.knowledge-assistant > header > div {
  display: flex;
  align-items: center;
  gap: 9px;
}
.knowledge-assistant > header i {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: #165dff;
  color: #fff;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
}
.knowledge-assistant > header span {
  display: grid;
  gap: 2px;
}
.knowledge-assistant > header strong {
  font-size: 13px;
}
.knowledge-assistant > header em {
  color: #72819a;
  font-size: 9px;
  font-style: normal;
}
.knowledge-assistant > header button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 5px;
  background: #edf3fb;
  color: #5f6f88;
  font-size: 19px;
  cursor: pointer;
}
.knowledge-assistant__messages {
  display: flex;
  min-height: 0;
  gap: 9px;
  padding: 13px;
  overflow: auto;
  flex-direction: column;
}
.knowledge-assistant__messages article {
  align-self: flex-start;
  max-width: 86%;
  padding: 10px 11px;
  border: 1px solid #d9e6f7;
  border-radius: 3px 10px 10px;
  background: #fff;
  color: #344761;
}
.knowledge-assistant__messages article.is-user {
  align-self: flex-end;
  border-color: #165dff;
  border-radius: 10px 3px 10px 10px;
  background: #165dff;
  color: #fff;
}
.knowledge-assistant__messages p {
  margin: 0;
  font-size: 11px;
  line-height: 18px;
}
.knowledge-assistant__messages article > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px solid #e7eef8;
}
.knowledge-assistant__messages article > div span {
  width: 100%;
  color: #8491a5;
  font-size: 8px;
}
.knowledge-assistant__messages article > div b {
  padding: 2px 6px;
  border-radius: 99px;
  background: #eaf2ff;
  color: #175cd3;
  font-size: 8px;
  font-weight: 500;
}
.knowledge-assistant__full {
  padding: 8px 13px;
  border-top: 1px solid #e2eaf5;
  background: #fff;
  color: #165dff;
  font-size: 9px;
  text-decoration: none;
}
.knowledge-assistant > form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 54px;
  gap: 8px;
  padding: 10px;
  border-top: 1px solid #dce8f8;
  background: #fff;
}
.knowledge-assistant textarea {
  box-sizing: border-box;
  height: 54px;
  padding: 8px 9px;
  border: 1px solid #bdd0ea;
  border-radius: 6px;
  color: #344761;
  font: 10px/16px inherit;
  resize: none;
}
.knowledge-assistant form button {
  border: 0;
  border-radius: 6px;
  background: #165dff;
  color: #fff;
  font-size: 10px;
  cursor: pointer;
}
.knowledge-assistant form button:disabled {
  background: #a9bee0;
  cursor: not-allowed;
}
@media (max-width: 620px) {
  .app-user-menu {
    right: -2px;
    width: min(200px, calc(100vw - 16px));
  }
}

.app-stage {
  position: relative;
  display: grid;
  margin-right: var(--space-16);
  grid-template-rows: 22px minmax(0, 1fr);
  gap: 16px;
  height: calc(100% - var(--header-height));
  padding: 16px 15px 16px 16px;
  border: 1px solid #fff;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.48);
  backdrop-filter: blur(8px);
  box-shadow: none;
  overflow: hidden;
  scrollbar-gutter: auto;
}


.app-stage::after {
  content: "";
  position: absolute;
  z-index: 1;
  inset: 0;
  border: 1px solid #fff;
  border-radius: inherit;
  pointer-events: none;
}

.app-breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  height: 22px;
  color: var(--gkx-text-secondary);
}

.app-breadcrumb__separator {
  flex: 0 0 auto;
  margin: 0;
  color: #86909c;
  font-size: 12px;
  line-height: 12px;
  text-align: center;
}

.app-breadcrumb__history {
  text-decoration: none;
  flex: 0 0 auto;
  color: #86909c;
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}

.app-breadcrumb__history:hover {
  color: var(--gkx-primary);
}

.app-breadcrumb__current {
  flex: 0 0 auto;
  color: #86909c;
  font-size: 12px;
  line-height: 20px;
  font-weight: 400;
  white-space: nowrap;
}

.app-workspace {
  min-width: 0;
  min-height: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  scrollbar-width: none;
}

.app-workspace::-webkit-scrollbar {
  display: none;
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
    min-height: 40px;
  }
}

@media (max-width: 1050px) {
  .app-top-actions__user span {
    display: none;
  }
  .alert-drawer {
    width: min(430px, 94vw);
  }
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
    font-size: 14px;
    line-height: 22px;
  }
}

@media (max-width: 767px) {
  .app-shell,
  .app-shell.is-collapsed {
    display: block;
  }

  .app-sidebar {
    position: fixed;
    z-index: 101;
    inset: 0 auto 0 0;
    width: min(82vw, 300px);
    padding: 0 12px 16px;
    background: #edf5ff;
    box-shadow: 12px 0 32px rgba(29, 33, 41, 0.18);
    visibility: hidden;
    transform: translateX(-105%);
    transition: transform 0.2s ease, visibility 0.2s;
  }

  .is-mobile-nav-open .app-sidebar {
    visibility: visible;
    transform: translateX(0);
  }

  .app-sidebar-mask {
    position: fixed;
    z-index: 100;
    inset: 0;
    padding: 0;
    border: 0;
    background: rgba(15, 23, 42, 0.42);
  }

  .app-main {
    width: 100%;
    padding: 0;
  }

  .app-top-actions {
    height: 52px;
    padding: 0 12px;
  }

  .app-shell__menu {
    display: inline-flex;
    flex: 0 0 auto;
    width: auto;
    height: 36px;
    padding: 0 10px 0 6px;
    gap: 4px;
    border: 1px solid rgba(22, 93, 255, 0.18);
    background: rgba(255, 255, 255, 0.72);
    color: #344766;
    font-size: 14px;
  }

  .app-shell__menu img {
    width: 22px;
    height: 22px;
  }

  .app-top-actions__right {
    gap: 4px;
    margin-right: 0;
  }


  .app-stage {
    grid-template-rows: auto minmax(0, 1fr);
    margin-right: 0;
    gap: 8px;
    height: calc(100% - 52px);
    padding: 8px;
    border: 0;
    border-radius: 0;
  }

  .app-breadcrumb {
    width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .app-workspace {
    padding: 10px;
    border-radius: 6px;
  }

  .alert-drawer {
    width: 100vw;
  }
}
</style>
