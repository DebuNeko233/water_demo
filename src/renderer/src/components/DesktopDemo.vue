<script setup lang="ts">
import { ref } from 'vue'
import { openLogDirectory, selectFile } from '../services/desktop'
import type { LogTarget } from '../../../shared/bridge'
import { createLogger } from '../services/logger'

const selectedFile = ref('')
const error = ref('')
const log = createLogger('DesktopDemo')

async function chooseFile(): Promise<void> {
  error.value = ''
  try {
    const chosen = await selectFile()
    selectedFile.value = chosen ?? '已取消选择'
    // 只记录操作结果，不写用户所选文件的完整路径。
    log.info(chosen === null ? 'File selection cancelled' : 'File selected')
  } catch (caught) {
    error.value = String(caught)
    log.warn('File picker failed')
  }
}

async function openLogs(target: LogTarget): Promise<void> {
  error.value = ''
  try {
    await openLogDirectory(target)
  } catch (caught) {
    error.value = String(caught)
    log.warn('Unable to open log directory')
  }
}
</script>

<template>
  <section id="ipc" class="card">
    <div class="panel-heading"><h2>Electron IPC 示例</h2><span>preload bridge</span></div>
    <p class="description">文件选择由 Electron 主进程执行，Vue 不直接访问 Node.js。</p>
    <button class="secondary" @click="chooseFile">选择文件</button>
    <p class="small wrap-text">{{ selectedFile || '尚未选择文件' }}</p>
    <div class="task-buttons">
      <button class="text-button" @click="openLogs('electron')">打开前端日志</button>
      <button class="text-button" @click="openLogs('python')">打开后端日志</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
