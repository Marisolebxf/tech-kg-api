import { ref } from 'vue'

interface ToastItem {
  id: number
  message: string
  tone: 'success' | 'info' | 'warning'
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
