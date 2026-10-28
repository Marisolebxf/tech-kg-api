import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useAuthStore } from '../stores/auth'

const POLL_INTERVAL = 2_000
const LOGIN_TIMEOUT = 5 * 60_000

/** 门户写 Cookie；身份只能由本系统后端验证，不能信任弹窗消息或 URL。 */
export function usePortalLogin(onAuthenticated: (target: string) => Promise<boolean>) {
  const auth = useAuthStore()
  const waiting = ref(false)
  const status = ref('')
  const error = ref('')
  let popup: Window | null = null
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  let deadlineTimer: ReturnType<typeof setTimeout> | undefined
  let attempt = 0
  let ready = false
  let checkingAttempt: number | null = null
  let target = '/overview'

  function stop() {
    attempt += 1
    ready = false
    waiting.value = false
    clearTimeout(pollTimer)
    clearTimeout(deadlineTimer)
    try { popup?.close() } catch { /* 门户隔离策略可能断开窗口引用。 */ }
    popup = null
  }

  function cancel() {
    stop()
    status.value = ''
    error.value = ''
  }

  async function check() {
    if (!waiting.value || !ready || checkingAttempt === attempt) return
    const current = attempt
    checkingAttempt = current
    clearTimeout(pollTimer)
    let delay = POLL_INTERVAL
    try {
      const profile = await auth.loadCurrentUser(true)
      if (current !== attempt) return
      if (auth.skipSilentLogin || auth.loggingOut) {
        cancel()
        return
      }
      if (profile) {
        // 先结束轮询，再导航；路由守卫仍执行原有身份和权限检查。
        const destination = target
        stop()
        status.value = ''
        try {
          if (!await onAuthenticated(destination)) error.value = '登录已完成，请再次点击“进入平台”继续。'
        } catch {
          error.value = '暂时无法进入系统，请再次点击“进入平台”重试。'
        }
        return
      }
      // COOP 也会让 closed=true，不能据此判定取消，更不能判定登录成功。
      status.value = popup?.closed
        ? '登录窗口已关闭或已切换。完成门户登录后，此页会自动继续；也可以取消后重试。'
        : '请在新窗口完成门户登录，此页会自动进入系统。'
    } catch {
      if (current === attempt) {
        status.value = '暂时无法确认登录状态，正在重试。请保持此页打开。'
        delay = 5_000
      }
    } finally {
      if (checkingAttempt === current) checkingAttempt = null
      if (current === attempt && waiting.value) pollTimer = setTimeout(() => { void check() }, delay)
    }
  }

  function start(next: string) {
    if (waiting.value) return
    error.value = ''
    status.value = ''
    // 必须在点击事件内、任何 await 之前打开，尤其是首次登录时。
    try { popup = window.open('about:blank', '_blank', 'popup,width=560,height=760') } catch { popup = null }
    if (!popup) {
      error.value = '浏览器阻止了登录窗口，请允许本站弹出窗口后再次点击“进入平台”。'
      return
    }
    try {
      popup.opener = null
      popup.document.title = '统一登录'
      popup.document.body.textContent = '正在打开统一登录，请稍候…'
    } catch { /* 浏览器可能限制访问新窗口，不影响后端验证流程。 */ }
    waiting.value = true
    status.value = '正在打开门户登录…'
    target = next
    const current = ++attempt
    deadlineTimer = setTimeout(() => {
      if (current !== attempt) return
      stop()
      status.value = ''
      error.value = '等待登录已超时，请重新点击“进入平台”。'
    }, LOGIN_TIMEOUT)

    void (async () => {
      try {
        const url = await auth.preparePortalLogin(next)
        if (current !== attempt) return
        if (!url) { cancel(); return }
        const destination = new URL(url, window.location.href)
        if (!['http:', 'https:'].includes(destination.protocol)) throw new Error('invalid login URL')
        popup!.location.replace(destination.href)
        ready = true
        status.value = '请在新窗口完成门户登录，此页会自动进入系统。'
        void check()
      } catch {
        if (current !== attempt) return
        stop()
        status.value = ''
        error.value = '无法打开门户登录，请刷新页面后重试。'
      }
    })()
  }

  function recheck() { void check() }
  function onVisibilityChange() { if (document.visibilityState === 'visible') recheck() }
  onMounted(() => {
    window.addEventListener('focus', recheck)
    window.addEventListener('pageshow', recheck)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })
  onBeforeUnmount(() => {
    stop()
    window.removeEventListener('focus', recheck)
    window.removeEventListener('pageshow', recheck)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { waiting, status, error, start, cancel }
}
