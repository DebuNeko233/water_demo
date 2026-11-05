<script setup lang="ts">
import type { BackendStatus } from '../../../shared/bridge'

defineProps<{
  status: BackendStatus
  diagnostic: string
  retrying: boolean
}>()

defineEmits<{ retry: [] }>()
</script>

<template>
  <section v-if="status === 'offline' || status === 'failed'" class="connection-notice">
    <div>
      <strong>Python 后端{{ status === 'failed' ? '启动失败' : '暂未连接' }}</strong>
      <p>{{ diagnostic || '检查 Python 终端或应用日志了解详情。' }}</p>
    </div>
    <button class="secondary" :disabled="retrying" @click="$emit('retry')">
      {{ retrying ? '连接中…' : '重新连接' }}
    </button>
  </section>
</template>
