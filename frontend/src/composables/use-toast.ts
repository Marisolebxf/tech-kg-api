import { ref } from 'vue'

interface ToastItem {
  id: number
  message: string
  tone: 'success' | 'info' | 'warning' | 'error'
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

export function useToast() {
  function showToast(message: string, tone: ToastItem['tone'] = 'success', duration = 2800) {
    const id = nextId++
    toasts.value = [...toasts.value, { id, message, tone }]
    if (duration > 0) {
      window.setTimeout(() => {
        toasts.value = toasts.value.filter((item) => item.id !== id)
      }, duration)
    }
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter((item) => item.id !== id)
  }

  return { toasts, showToast, dismissToast }
}
