import { ref } from 'vue'

import { formatNow } from './useDeveloperExamples'

export function useModuleTest() {
  const loading = ref(false)
  const error = ref('')
  const lastTestTime = ref(formatNow())

  async function runWithLoading(task: () => Promise<void>) {
    loading.value = true
    error.value = ''
    try {
      await task()
      lastTestTime.value = formatNow()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      loading.value = false
    }
  }

  return { loading, error, lastTestTime, runWithLoading }
}
