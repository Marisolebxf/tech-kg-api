<template>
  <AppShell :title="PAGE_ARIA_LABEL">
    <BindingPageFrame />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '../shared/layouts/AppShell.vue'
import BindingPageFrame from '../shared/components/BindingPageFrame.vue'
import { PAGE_ARIA_LABEL } from '../shared/config'
</script>
