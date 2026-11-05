<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from './components/AppSidebar.vue'
import HomeView from './views/HomeView.vue'
import type { PageId } from './navigation'

const activePage = ref<PageId>('overview')
</script>

<template>
  <div class="layout">
    <AppSidebar :active-page="activePage" @navigate="activePage = $event" />
    <HomeView :active-page="activePage" />
  </div>
</template>
