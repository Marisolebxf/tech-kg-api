import '@arco-design/web-vue/dist/arco.css'
import './styles/tokens.css'
import './styles/reset.css'
import './styles/global.css'
import './styles/readability.css'
import './styles/gkx-theme.css'
import './styles/design-rules.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ArcoVue from '@arco-design/web-vue'

import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'

const scrollingTimers = new WeakMap<Element, number>()

function revealScrollbar(target: EventTarget | null) {
  const element =
    target instanceof Element
      ? target
      : document.scrollingElement ?? document.documentElement
  element.classList.add('kg-is-scrolling')
  const previousTimer = scrollingTimers.get(element)
  if (previousTimer) {
    window.clearTimeout(previousTimer)
  }
  scrollingTimers.set(
    element,
    window.setTimeout(() => {
      element.classList.remove('kg-is-scrolling')
      scrollingTimers.delete(element)
    }, 900),
  )
}

window.addEventListener('scroll', (event) => revealScrollbar(event.target), true)
window.addEventListener('wheel', (event) => revealScrollbar(event.target), { passive: true, capture: true })
window.addEventListener('touchmove', (event) => revealScrollbar(event.target), { passive: true, capture: true })

function renderFatalError(error: unknown) {
  const target = document.querySelector('#app')
  if (!target) return
  const message = error instanceof Error ? error.message : String(error)
  target.innerHTML = `
    <div style="min-height:100vh;display:grid;place-items:center;background:#f5f7fb;color:#1d2129;font-family:Arial,'Microsoft YaHei',sans-serif;">
      <section style="width:min(720px,calc(100vw - 48px));padding:24px;border:1px solid #fecdca;border-radius:8px;background:#fff7f6;">
        <h1 style="margin:0 0 12px;font-size:20px;color:#b42318;">页面启动异常</h1>
        <p style="margin:0;line-height:1.6;color:#912018;word-break:break-word;">${message}</p>
      </section>
    </div>
  `
}

try {
  const app = createApp(App)
  app.config.errorHandler = (error) => {
    console.error(error)
    renderFatalError(error)
  }
  app.use(createPinia()).use(router).use(ArcoVue).mount('#app')
  // AUTH_ENABLED=false 时路由守卫短路放行，不会加载 profile——导致 isAdmin 判定
  // 恒为 false、admin 按钮（实体列表「重建索引」等）在免登录部署里不可见。
  // 启动时无条件补拉一次：后端 /auth/me 在免登录态返回 dev 管理员身份。
  void useAuthStore().loadCurrentUser().catch(() => undefined)
} catch (error) {
  console.error(error)
  renderFatalError(error)
}
