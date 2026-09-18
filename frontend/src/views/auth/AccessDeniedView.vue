<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="denied-page">
    <h1>当前账号没有管理员权限</h1>
    <p>该页面仅对平台管理员开放。你仍可使用图谱查询、业务服务等其他功能。</p>
    <a-button type="primary" @click="router.replace('/overview')">返回平台总览</a-button>
  </section>
</template>

<style scoped>
.denied-page{display:grid;place-items:center;align-content:center;gap:12px;min-height:100%;text-align:center}.denied-page h1{margin:0;font-size:22px}.denied-page p{max-width:520px;margin:0 0 8px;color:var(--gkx-text-secondary);line-height:1.7}
</style>
