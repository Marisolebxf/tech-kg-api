<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import iconMenuCollapse from '../assets/icons/icon-menu-collapse.svg'
import iconMessage from '../assets/icons/icon-message.svg'
import iconSidebarArrow from '../assets/icons/icon-sidebar-arrow.svg'
import navFlow from '../assets/icons/nav-flow.svg'
import navGraph from '../assets/icons/nav-graph.svg'
import navReasoning from '../assets/icons/nav-reasoning.svg'
import avatarBen from '../assets/images/avatar-ben.png'
import logoKg from '../assets/images/logo-kg.png'

const route = useRoute()
const pageTitle = computed(() => String(route.meta.title ?? '亿级知识图谱'))
</script>

<template>
  <div class="app-viewport">
    <div class="app-shell">
        <aside class="app-sidebar">
          <div class="app-brand">
            <img class="app-brand__logo" :src="logoKg" alt="知识图谱平台" />
            <div class="app-brand__name">知识图谱平台</div>
            <img class="app-brand__menu" :src="iconMenuCollapse" alt="" aria-hidden="true" />
          </div>

          <nav class="app-nav">
            <a class="app-nav__item" href="#">
              <img class="app-nav__icon" :src="navFlow" alt="" aria-hidden="true" />
              <span>流程编排</span>
              <img class="app-nav__arrow" :src="iconSidebarArrow" alt="" aria-hidden="true" />
            </a>
            <a class="app-nav__item" href="#">
              <img class="app-nav__icon" :src="navGraph" alt="" aria-hidden="true" />
              <span>图谱服务</span>
              <img class="app-nav__arrow" :src="iconSidebarArrow" alt="" aria-hidden="true" />
            </a>
            <a class="app-nav__item app-nav__item--open" href="#">
              <img class="app-nav__icon" :src="navReasoning" alt="" aria-hidden="true" />
              <span>知识推理服务</span>
              <img class="app-nav__arrow" :src="iconSidebarArrow" alt="" aria-hidden="true" />
            </a>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/expert-direct">
              科技专家直接关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/node-indirect">
              科技节点间接关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/two-point-achievement">
              科技两点合作成果
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/expert-colleague">
              科技专家同事关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/expert-alumni">
              科技专家校友关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/paper-cooperation">
              专家论文合作关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/enterprise-relation">
              重点科技企业关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/industry-chain-event">
              产业链点事件关系
            </RouterLink>
            <RouterLink class="app-nav__item app-nav__item--sub" active-class="app-nav__item--active" to="/industry-chain-panorama">
              科技产业链全景图
            </RouterLink>
          </nav>

          <div class="app-user">
            <img class="app-user__avatar" :src="avatarBen" alt="" aria-hidden="true" />
            <span>Ben</span>
            <img class="app-user__message" :src="iconMessage" alt="" aria-hidden="true" />
          </div>
        </aside>

        <main class="app-main">
          <section class="app-workspace" :aria-label="pageTitle">
            <RouterView />
          </section>
        </main>
      </div>
  </div>
</template>

<style scoped>
.app-viewport {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #f5f5f5;
}

.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  width: 100%;
  height: 100%;
  background:
    radial-gradient(circle at 12% 84%, rgba(255, 255, 255, 0.26), rgba(255, 255, 255, 0) 24%),
    radial-gradient(circle at 52% 8%, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0) 30%),
    linear-gradient(90deg, #cfe4ff 0%, #c6deff 26%, #b9d5ff 58%, #a9cbfb 100%),
    #b5d3fc;
}

.app-sidebar {
  position: relative;
  height: 100%;
  padding: 24px 24px 76px 40px;
  overflow-y: auto;
  color: var(--text-primary);
  background:
    radial-gradient(circle at 78% 64%, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 34%),
    linear-gradient(180deg, rgba(214, 232, 255, 0.72) 0%, rgba(192, 219, 255, 0.56) 58%, rgba(207, 228, 255, 0.72) 100%);
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding-bottom: var(--space-24);
  border-bottom: 1px solid rgba(22, 93, 255, 0.08);
}

.app-brand__logo {
  width: 38px;
  height: 38px;
  object-fit: contain;
}

.app-brand__name {
  flex: 0 0 auto;
  font-size: 20px;
  line-height: 26px;
  font-weight: 600;
  white-space: nowrap;
}

.app-brand__menu {
  width: 18px;
  height: 18px;
  margin-left: auto;
  object-fit: contain;
}

.app-nav {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-12);
  margin-top: 28px;
}

.app-nav::after {
  position: absolute;
  top: 150px;
  bottom: 12px;
  left: 20px;
  width: 1px;
  background: rgba(22, 93, 255, 0.12);
  content: "";
}

.app-nav__item {
  display: grid;
  grid-template-columns: 18px max-content 1fr;
  align-items: center;
  gap: var(--space-12);
  min-height: 42px;
  padding: 0 var(--space-12);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 17px;
  line-height: 22px;
  white-space: nowrap;
}

.app-nav__icon {
  width: 18px;
  height: 18px;
  align-self: center;
  justify-self: center;
  object-fit: contain;
}

.app-nav__arrow {
  width: 10px;
  height: 10px;
  justify-self: end;
  object-fit: contain;
  opacity: 0.72;
}

.app-nav__item--open {
  margin-top: var(--space-12);
}

.app-nav__item--open .app-nav__arrow {
  transform: rotate(90deg);
}

.app-nav__item--active {
  position: relative;
  z-index: 1;
  grid-template-columns: 1fr;
  width: 160px;
  margin-left: 32px;
  color: var(--primary);
  border: 1px solid rgba(255, 255, 255, 0.56);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.42));
  box-shadow: 0 8px 18px rgba(72, 132, 214, 0.12);
}

.app-nav__item--sub {
  position: relative;
  z-index: 1;
  grid-template-columns: 1fr;
  width: 160px;
  margin-left: 32px;
  background: transparent;
}

.app-nav__item--sub.app-nav__item--active {
  color: var(--primary);
  border: 1px solid rgba(255, 255, 255, 0.56);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.42));
  box-shadow: 0 8px 18px rgba(72, 132, 214, 0.12);
}

.app-user {
  position: absolute;
  right: 24px;
  bottom: 24px;
  left: 40px;
  display: inline-flex;
  align-items: center;
  gap: var(--space-8);
  font-size: 16px;
  line-height: 24px;
}

.app-user__avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  object-fit: cover;
}

.app-user__message {
  width: 20px;
  height: 20px;
  margin-left: auto;
  object-fit: contain;
}

.app-main {
  min-width: 0;
  height: 100%;
  padding: 16px 16px 16px 28px;
  overflow: hidden;
}

.app-workspace {
  height: 100%;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: var(--radius-shell);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(255, 255, 255, 0.92)),
    var(--surface);
  box-shadow:
    0 0 0 14px rgba(255, 255, 255, 0.2),
    0 0 0 15px rgba(117, 171, 244, 0.22),
    0 22px 48px rgba(48, 105, 194, 0.22);
  overflow: hidden;
}
</style>
