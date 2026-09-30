import { ref } from 'vue'

interface ToastItem {
  id: number
  message: string
  /** Arco 全局提示四态：info/success/warning/error（每种状态带对应提示符） */
  tone: 'success' | 'info' | 'warning' | 'error'
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

export function useToast() {
  function showToast(message: string, tone: ToastItem['tone'] = 'success') {
    const id = nextId++
    toasts.value = [...toasts.value, { id, message, tone }]
    window.setTimeout(() => {
      toasts.value = toasts.value.filter((item) => item.id !== id)
    }, 2800)
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter((item) => item.id !== id)
  }

  return { toasts, showToast, dismissToast }
}
