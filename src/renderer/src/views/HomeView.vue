<script setup lang="ts">
import { computed } from 'vue'
import { navigationItems, type PageId } from '../navigation'
import BackendNotice from '../components/BackendNotice.vue'
import DesktopDemo from '../components/DesktopDemo.vue'
import EchoDemo from '../components/EchoDemo.vue'
import EventLog from '../components/EventLog.vue'
import TaskDemo from '../components/TaskDemo.vue'
import { useBackendConnection } from '../composables/useBackendConnection'
import { useBackendEvents } from '../composables/useBackendEvents'

const props = defineProps<{ activePage: PageId }>()
// 页面导航只切换内容显示，不销毁任务和表单组件，才能保留状态。
const currentPage = computed(
  () => navigationItems.find((item) => item.id === props.activePage) ?? navigationItems[0],
)

const { status, diagnostic, retrying, retry } = useBackendConnection()
const { events } = useBackendEvents()
</script>

<template>
  <main id="overview" class="content">
    <header class="topbar">
      <div>
        <p class="eyebrow">DEVELOPER STARTER</p>
        <h1>{{ currentPage.label }}</h1>
        <p class="subtitle">{{ currentPage.description }}</p>
      </div>
      <div class="status" :class="status"><span class="indicator"></span> Python {{ status }}</div>
    </header>

    <BackendNotice :status="status" :diagnostic="diagnostic" :retrying="retrying" @retry="retry" />

    <div v-show="activePage === 'overview'" class="cards">
      <section class="card metric">
        <div class="metric-label">Electron IPC</div>
        <strong>桌面能力</strong>
        <p>窗口、文件对话框、应用目录</p>
      </section>
      <section class="card metric">
        <div class="metric-label">HTTP · REST</div>
        <strong>业务接口</strong>
        <p>请求、响应与错误处理</p>
      </section>
      <section class="card metric">
        <div class="metric-label">WebSocket</div>
        <strong>实时事件</strong>
        <p>任务状态、进度与通知</p>
      </section>
    </div>

    <div class="panels" :class="{ 'one-column': activePage === 'http' || activePage === 'ipc' }">
      <!-- Keep components mounted so task progress and form input survive tab changes. -->
      <div v-show="activePage !== 'ipc'" class="panel-stack">
        <EchoDemo v-show="activePage === 'overview' || activePage === 'http'" :ready="status === 'ready'" />
        <TaskDemo
          v-show="activePage === 'overview' || activePage === 'tasks'"
          :ready="status === 'ready'"
          :events="events"
        />
      </div>
      <div v-show="activePage !== 'http'" class="panel-stack">
        <DesktopDemo v-show="activePage === 'overview' || activePage === 'ipc'" />
        <EventLog v-show="activePage === 'overview' || activePage === 'tasks'" :events="events" />
      </div>
    </div>

    <footer>关闭应用窗口只停止它自己托管的 Python；独立开发后端不受影响。</footer>
  </main>
</template>
