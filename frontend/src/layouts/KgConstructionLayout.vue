<script setup lang="ts">
import ModuleSidebar from '../components/kg/ModuleSidebar.vue'
</script>

<template>
  <main class="app-frame">
    <div class="breadcrumb"></div>
    <section class="workspace">
      <ModuleSidebar />
      <section class="main-card">
        <div class="inner-card">
          <slot />
        </div>
      </section>
    </section>
  </main>
</template>
