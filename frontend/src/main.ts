import '@arco-design/web-vue/dist/arco.css'
import './styles/tokens.css'
import './styles/reset.css'
import './styles/global.css'
import './styles/readability.css'
import './styles/overview-scrollbars.css'
import './styles/gkx-theme.css'
import './styles/design-rules.css'
import './styles/detail-scrollbars.css'
import './styles/platform-scrollbar-appearance.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ArcoVue from '@arco-design/web-vue'

import App from './App.vue'
import { router } from './router'
import { failPageLoading } from './portal/pageLoading'

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

function renderFatalError() {
  const target = document.querySelector('#app')
  if (!target) return
  if (failPageLoading()) return
  // Fallback for an older cached HTML document without the independent startup shell.
  const section = document.createElement('section')
  const title = document.createElement('h1')
  title.textContent = '页面暂时无法加载'
  const message = document.createElement('p')
  message.textContent = '请重新加载页面，或通过左侧菜单切换其他业务。'
  const retry = document.createElement('button')
  retry.type = 'button'
  retry.textContent = '重新加载'
  retry.addEventListener('click', () => window.location.reload())
  section.append(title, message, retry)
  target.replaceChildren(section)
}

try {
  const app = createApp(App)
  app.config.errorHandler = (error) => {
    console.error(error)
    renderFatalError()
  }
  app.use(createPinia()).use(router).use(ArcoVue).mount('#app')
  // 初始身份和空间由路由守卫统一准备；登录页独立检查已有会话。
} catch (error) {
  console.error(error)
  renderFatalError()
}
