import { getCurrentInstance, onUnmounted, ref } from 'vue'

interface ToastItem {
  id: number
  message: string
  /** Arco 全局提示四态：info/success/warning/error（每种状态带对应提示符） */
  tone: 'success' | 'info' | 'warning' | 'error'
}

const toasts = ref<ToastItem[]>([])
let nextId = 0
const timers = new Map<number, number>()

export function useToast() {
  let active = true
  if (getCurrentInstance()) onUnmounted(() => { active = false })
  function showToast(message: string, tone: ToastItem['tone'] = 'success') {
    // 空间切换会卸载原页面，其未完成请求不应再向新页面推送提示。
    if (!active) return
    const id = nextId++
    while (toasts.value.length >= 3) dismissToast(toasts.value[0]!.id)
    toasts.value = [...toasts.value, { id, message, tone }]
    timers.set(id, window.setTimeout(() => dismissToast(id), tone === 'warning' || tone === 'error' ? 4500 : 3000))
  }

  function dismissToast(id: number) {
    window.clearTimeout(timers.get(id))
    timers.delete(id)
    toasts.value = toasts.value.filter((item) => item.id !== id)
  }

  return { toasts, showToast, dismissToast }
}
