<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const message = ref('')
const timestamp = ref('')
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/business/hello')
    message.value = data.message
    timestamp.value = data.timestamp
  } catch (e: any) {
    error.value = e.message || 'Request failed'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section id="center">
    <h1>Tech KG Engine</h1>

    <div v-if="loading" class="status">Loading...</div>

    <div v-else-if="error" class="status error">{{ error }}</div>

    <div v-else class="result">
      <p class="message">{{ message }}</p>
      <p class="timestamp">{{ timestamp }}</p>
    </div>
  </section>

  <div class="ticks"></div>
  <section id="spacer"></section>
</template>

<style scoped>
.result {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.message {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-h);
}

.timestamp {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--text);
}

.status {
  font-size: 18px;
  color: var(--text);
}

.status.error {
  color: #e74c3c;
}
</style>
