<script setup lang="ts">
import { navigationItems, type PageId } from '../navigation'

defineProps<{ activePage: PageId }>()
const emit = defineEmits<{ navigate: [page: PageId] }>()
</script>

<template>
  <aside class="sidebar">
    <div class="brand"><span class="logo">P</span> SampleApp</div>
    <nav aria-label="示例页面">
      <button
        v-for="item in navigationItems"
        :key="item.id"
        type="button"
        class="nav-item"
        :class="{ selected: activePage === item.id }"
        :aria-current="activePage === item.id ? 'page' : undefined"
        @click="emit('navigate', item.id)"
      >
        <span class="nav-symbol" aria-hidden="true">{{ item.icon }}</span>
        {{ item.label }}
      </button>
    </nav>
    <div class="sidebar-note">Python + Electron + Vue<br />通用桌面应用模板</div>
  </aside>
</template>
