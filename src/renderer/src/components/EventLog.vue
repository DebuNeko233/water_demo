<script setup lang="ts">
import type { BackendEvent } from '../../../shared/bridge'

defineProps<{ events: BackendEvent[] }>()
</script>

<template>
  <section class="card">
    <div class="panel-heading"><h2>WebSocket 实时事件</h2><span>最近 12 条</span></div>
    <div class="event-log">
      <p v-if="!events.length" class="muted">等待 WebSocket 事件…</p>
      <p v-for="message in events" :key="message.sequence">
        {{ message.event }} · {{ JSON.stringify(message.data) }}
      </p>
    </div>
  </section>
</template>
