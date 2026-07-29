import './styles/tokens.css'
import './styles/reset.css'
import './styles/global.css'
import './styles/readability.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'

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
  app.use(createPinia()).use(router).mount('#app')
} catch (error) {
  console.error(error)
  renderFatalError(error)
}
