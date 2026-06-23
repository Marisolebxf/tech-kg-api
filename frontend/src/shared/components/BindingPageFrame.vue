<template>
  <iframe
    class="binding-page-frame"
    :src="PAGE_SOURCE_URL"
    :title="PAGE_TITLE"
    :loading="PAGE_FRAME_LOADING"
    :referrerpolicy="PAGE_FRAME_REFERRER_POLICY"
  />
</template>

<script setup lang="ts">
import {
  PAGE_FRAME_LOADING,
  PAGE_FRAME_REFERRER_POLICY,
  PAGE_SOURCE_URL,
  PAGE_TITLE,
} from '../config'
</script>

<style scoped>
.binding-page-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  background: #ffffff;
}
</style>
