<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="denied-page">
    <div class="denied-page__code">403</div>
    <h1>当前账号没有管理端权限</h1>
    <p>你仍可进入用户端进行图谱查询、关系分析并提交人工修正申请。</p>
    <a-button type="primary" @click="router.replace('/overview')">返回用户端</a-button>
  </section>
</template>

<style scoped>
.denied-page{display:grid;place-items:center;align-content:center;gap:12px;min-height:100%;text-align:center}.denied-page__code{color:var(--gkx-primary);font-size:64px;font-weight:700;line-height:1}.denied-page h1{margin:0;font-size:22px}.denied-page p{max-width:520px;margin:0 0 8px;color:var(--gkx-text-secondary);line-height:1.7}
</style>
