<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

type Point = { x: number; y: number }
type Calibration = { cx: number; cy: number; radius: number; width: number; height: number }

type Screen = 'welcome' | 'monitor'
const screen = ref<Screen>('welcome')
const fileInput = ref<HTMLInputElement | null>(null)
const calibrationVideo = ref<HTMLVideoElement | null>(null)
const monitorVideo = ref<HTMLVideoElement | null>(null)
const modalOpen = ref(false)
const pendingFile = ref<File | null>(null)
const pendingUrl = ref('')
const activeUrl = ref('')
const activeName = ref('')
const calibration = ref<Calibration | null>(null)
const center = ref<Point | null>(null)
const radius = ref<number | null>(null)
const draftWidth = ref(0)
const draftHeight = ref(0)
const calibrationDuration = ref(0)
const calibrationTime = ref(0)
const currentTime = ref(0)
const duration = ref(0)
const videoWidth = ref(0)
const videoHeight = ref(0)
const isPlaying = ref(false)
const videoError = ref('')
const message = ref('')
let previouslyPlaying = false
let resumeAt = 0
let toastTimeout: ReturnType<typeof setTimeout> | undefined

const readyToConfirm = computed(() => !!center.value && radius.value !== null && radius.value >= 20 && draftWidth.value > 0)
const draftCalibration = computed<Calibration | null>(() =>
  readyToConfirm.value && center.value && radius.value !== null
    ? { cx: center.value.x, cy: center.value.y, radius: radius.value, width: draftWidth.value, height: draftHeight.value }
    : null,
)
const progress = computed(() => duration.value > 0 ? currentTime.value / duration.value * 100 : 0)
const calibrationProgress = computed(() => calibrationDuration.value > 0 ? calibrationTime.value / calibrationDuration.value * 100 : 0)
const calibrationPhase = computed(() => !center.value ? '点击晶圆中心' : radius.value === null ? '点击晶圆边缘' : '标注完成')
const calibrationMeasure = computed(() => {
  if (!center.value) return '中心 -- · 半径 --'
  const base = `中心 (${Math.round(center.value.x)}, ${Math.round(center.value.y)})`
  return radius.value === null ? `${base} · 半径 --` : `${base} · 半径 ${Math.round(radius.value)} px`
})
const previewUrl = computed(() => pendingUrl.value || activeUrl.value)
const overlaySize = computed(() => `${videoWidth.value || 1} ${videoHeight.value || 1}`)
const draftOverlaySize = computed(() => `${draftWidth.value || 1} ${draftHeight.value || 1}`)
const sectors = computed(() => {
  const c = calibration.value
  if (!c) return []
  return Array.from({ length: 24 }, (_, i) => {
    const angle = i * Math.PI / 12
    return {
      x1: c.cx + c.radius * .65 * Math.cos(angle),
      y1: c.cy + c.radius * .65 * Math.sin(angle),
      x2: c.cx + c.radius * .95 * Math.cos(angle),
      y2: c.cy + c.radius * .95 * Math.sin(angle),
    }
  })
})

function notify(text: string): void {
  message.value = text
  if (toastTimeout) clearTimeout(toastTimeout)
  toastTimeout = setTimeout(() => { message.value = '' }, 3500)
}
function formatTime(value: number): string {
  if (!Number.isFinite(value)) return '00:00'
  const seconds = Math.max(0, Math.floor(value))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
function chooseVideo(): void {
  if (!fileInput.value) return
  fileInput.value.value = ''
  fileInput.value.click()
}
function onFileChange(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.type.startsWith('video/') && !/\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(file.name)) {
    notify('请选择视频文件')
    return
  }
  if (pendingUrl.value) URL.revokeObjectURL(pendingUrl.value)
  pendingFile.value = file
  pendingUrl.value = URL.createObjectURL(file)
  openCalibration(false)
}
function resetDraft(): void {
  center.value = null
  radius.value = null
}
function openCalibration(existing: boolean): void {
  if (modalOpen.value) return
  previouslyPlaying = isPlaying.value
  resumeAt = monitorVideo.value?.currentTime || 0
  monitorVideo.value?.pause()
  resetDraft()
  draftWidth.value = 0
  draftHeight.value = 0
  calibrationDuration.value = 0
  calibrationTime.value = 0
  if (existing && calibration.value) {
    center.value = { x: calibration.value.cx, y: calibration.value.cy }
    radius.value = calibration.value.radius
  }
  modalOpen.value = true
  nextTick(() => {
    // Metadata is loaded by the modal video. A new source starts at frame zero;
    // re-calibration uses the currently displayed frame.
    calibrationVideo.value?.load()
  })
}
function editCalibration(): void {
  if (calibration.value && activeUrl.value) openCalibration(true)
}
function onCalibrationMetadata(): void {
  const video = calibrationVideo.value
  if (!video) return
  draftWidth.value = video.videoWidth
  draftHeight.value = video.videoHeight
  calibrationDuration.value = Number.isFinite(video.duration) ? video.duration : 0
  if (pendingFile.value) {
    video.currentTime = 0
  } else if (calibrationDuration.value > 0) {
    video.currentTime = Math.min(resumeAt, calibrationDuration.value)
  }
  calibrationTime.value = video.currentTime
}
function onCalibrationTime(): void {
  calibrationTime.value = calibrationVideo.value?.currentTime || 0
}
function onCalibrationSeek(event: Event): void {
  const v = calibrationVideo.value
  if (!v || !calibrationDuration.value) return
  v.currentTime = Number((event.target as HTMLInputElement).value)
  calibrationTime.value = v.currentTime
  resetDraft()
}
function onCalibrationClick(event: MouseEvent): void {
  if (!modalOpen.value || !draftWidth.value || !draftHeight.value || radius.value !== null) return
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const ratio = Math.min(rect.width / draftWidth.value, rect.height / draftHeight.value)
  const width = draftWidth.value * ratio
  const height = draftHeight.value * ratio
  const x = (event.clientX - rect.left - (rect.width - width) / 2) / ratio
  const y = (event.clientY - rect.top - (rect.height - height) / 2) / ratio
  if (x < 0 || x > draftWidth.value || y < 0 || y > draftHeight.value) return
  if (!center.value) {
    center.value = { x, y }
  } else {
    const r = Math.hypot(x - center.value.x, y - center.value.y)
    if (r < 20) { notify('半径过小，请重新点击边缘'); return }
    radius.value = r
  }
}
function closeCalibration(): void {
  modalOpen.value = false
  if (pendingUrl.value) {
    URL.revokeObjectURL(pendingUrl.value)
    pendingUrl.value = ''
    pendingFile.value = null
  }
  if (screen.value === 'monitor' && previouslyPlaying) {
    nextTick(() => { void monitorVideo.value?.play().catch(() => { isPlaying.value = false }) })
  }
}
async function confirmCalibration(): Promise<void> {
  if (!draftCalibration.value) return
  const nextCalibration = draftCalibration.value
  const replacing = !!pendingFile.value
  calibration.value = nextCalibration
  if (replacing && pendingFile.value) {
    if (activeUrl.value) URL.revokeObjectURL(activeUrl.value)
    activeUrl.value = pendingUrl.value
    activeName.value = pendingFile.value.name
    pendingUrl.value = ''
    pendingFile.value = null
    currentTime.value = 0
    duration.value = 0
    videoWidth.value = nextCalibration.width
    videoHeight.value = nextCalibration.height
    videoError.value = ''
  }
  modalOpen.value = false
  screen.value = 'monitor'
  await nextTick()
  if (replacing && monitorVideo.value) {
    monitorVideo.value.load()
  } else if (previouslyPlaying) {
    void monitorVideo.value?.play().catch(() => { isPlaying.value = false })
  }
}
function onMainMetadata(): void {
  const video = monitorVideo.value
  if (!video) return
  videoWidth.value = video.videoWidth
  videoHeight.value = video.videoHeight
  duration.value = Number.isFinite(video.duration) ? video.duration : 0
  video.currentTime = 0
  void video.play().catch(() => { isPlaying.value = false })
}
function onMainTime(): void { currentTime.value = monitorVideo.value?.currentTime || 0 }
function onMainSeek(event: Event): void {
  const video = monitorVideo.value
  if (!video || !duration.value) return
  video.currentTime = Number((event.target as HTMLInputElement).value)
  currentTime.value = video.currentTime
}
function togglePlay(): void {
  const video = monitorVideo.value
  if (!video || videoError.value) return
  if (video.paused) void video.play().catch(() => notify('视频无法播放'))
  else video.pause()
}
function jump(seconds: number): void {
  const video = monitorVideo.value
  if (!video || !duration.value) return
  video.currentTime = Math.max(0, Math.min(duration.value, video.currentTime + seconds))
  currentTime.value = video.currentTime
}
function restart(): void {
  if (!monitorVideo.value) return
  monitorVideo.value.currentTime = 0
  currentTime.value = 0
  void monitorVideo.value.play().catch(() => notify('视频无法播放'))
}
function stop(): void { monitorVideo.value?.pause() }
function windowAction(action: 'minimize' | 'toggleMaximize' | 'closeWindow'): void {
  const desktop = window.desktop
  if (!desktop?.system) return
  void desktop.system[action]()
}
function onEscape(event: KeyboardEvent): void {
  if (event.key === 'Escape' && modalOpen.value) closeCalibration()
}
onMounted(() => { window.addEventListener('keydown', onEscape) })
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEscape)
  if (toastTimeout) clearTimeout(toastTimeout)
  if (activeUrl.value) URL.revokeObjectURL(activeUrl.value)
  if (pendingUrl.value) URL.revokeObjectURL(pendingUrl.value)
})
</script>

<template>
  <div class="zebo-app">
    <header class="app-header">
      <div class="brand">
        <div class="brand-icon" aria-hidden="true"><svg viewBox="0 0 36 36"><circle cx="18" cy="18" r="12"/><circle cx="18" cy="18" r="6"/><path d="M18 2v9M18 25v9M2 18h9M25 18h9"/></svg></div>
        <div><div class="brand-name">ZeboVision</div><div class="brand-sub">VISION INSPECTION</div></div>
      </div>
      <div class="app-title">ZeboVision湿法清洗检测系统</div>
      <div class="header-actions">
        <span v-if="screen === 'monitor'" class="header-status"><i class="status-dot"/>本地视频</span>
        <div class="window-controls">
          <button type="button" title="最小化" aria-label="最小化" @click="windowAction('minimize')">—</button>
          <button type="button" title="最大化或还原" aria-label="最大化或还原" @click="windowAction('toggleMaximize')">□</button>
          <button type="button" class="close-window" title="关闭窗口" aria-label="关闭窗口" @click="windowAction('closeWindow')">×</button>
        </div>
      </div>
    </header>

    <main v-if="screen === 'welcome'" class="welcome">
      <section class="welcome-card">
        <div class="welcome-icon" aria-hidden="true"><svg viewBox="0 0 46 46"><rect x="5" y="10" width="36" height="26" rx="4"/><path d="m20 17 11 6-11 6z"/></svg></div>
        <h1>选择检测视频</h1>
        <p>选择视频后标注晶圆位置</p>
        <button type="button" class="btn btn-primary welcome-select" @click="chooseVideo">选择视频文件</button>
        <small>支持 MP4、MOV、AVI、MKV 等常见视频文件</small>
      </section>
    </main>

    <template v-else>
      <div class="statebar"><strong>实时监测</strong><span class="tag tag-green">● 已完成标注</span></div>
      <main class="workspace">
        <section class="panel video-panel">
          <div class="panel-heading"><span class="panel-title">检测画面</span><div class="heading-actions"><span class="live-label">● 视频预览</span><button class="btn btn-muted" @click="editCalibration">重新标注</button><button class="btn btn-muted" @click="chooseVideo">更换视频</button></div></div>
          <div class="video-stage">
            <div class="video-fit">
              <video ref="monitorVideo" class="video-element" :src="activeUrl" playsinline preload="metadata" @loadedmetadata="onMainMetadata" @timeupdate="onMainTime" @play="isPlaying = true" @pause="isPlaying = false" @ended="isPlaying = false" @error="videoError = '视频解码失败，请更换其他格式的视频'" />
              <svg v-if="calibration" class="roi-overlay" :viewBox="overlaySize" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
                <circle :cx="calibration.cx" :cy="calibration.cy" :r="calibration.radius * .95" class="ring-outer"/>
                <circle :cx="calibration.cx" :cy="calibration.cy" :r="calibration.radius * .65" class="ring-inner"/>
                <line v-for="(sector, i) in sectors" :key="i" :x1="sector.x1" :y1="sector.y1" :x2="sector.x2" :y2="sector.y2" class="sector-line"/>
                <path :d="`M ${calibration.cx-9} ${calibration.cy} h18 M ${calibration.cx} ${calibration.cy-9} v18`" class="center-mark"/>
              </svg>
            </div>
            <span class="viewport-label">检测画面</span>
            <span class="video-legend">绿色：检测外缘　蓝色：内缘</span>
            <div v-if="videoError" class="video-error">{{ videoError }}</div>
          </div>
          <div class="video-footer">
            <div class="timeline-header"><span>视频进度</span><span>{{ Math.round(progress) }}% 已播放</span></div>
            <input class="progress-range" type="range" aria-label="视频播放进度" min="0" :max="duration || 1" step="0.01" :value="currentTime" :style="{ '--progress': progress + '%' }" :disabled="!duration" @input="onMainSeek"/>
            <div class="playback"><div class="playback-left"><button title="后退 5 秒" aria-label="后退 5 秒" @click="jump(-5)">↶</button><button :title="isPlaying ? '暂停' : '播放'" :aria-label="isPlaying ? '暂停' : '播放'" @click="togglePlay">{{ isPlaying ? 'Ⅱ' : '▶' }}</button><button title="前进 5 秒" aria-label="前进 5 秒" @click="jump(5)">↷</button><span>{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span></div><span class="rate">1.0×</span></div>
          </div>
        </section>

        <div class="right-column">
          <section class="panel result-panel"><div><div class="data-label">当前检测结果</div><div class="status-unavailable">--</div><div class="status-description">检测数据待接入</div></div><div class="result-divider"/><div><div class="data-label">S_water · 当前值</div><div class="result-score">--</div><div class="data-note">水流扰动比例</div><div class="threshold-line">阈值 <b>0.0250</b></div></div></section>
          <section class="panel data-panel"><div class="panel-heading"><span class="panel-title">检测数据</span></div><div class="data-grid"><div class="metric"><div class="data-label">运行时间</div><div class="metric-value">{{ currentTime.toFixed(2) }} <small>s</small></div></div><div class="metric"><div class="data-label">S_water</div><div class="metric-value metric-blue">--</div></div><div class="metric"><div class="data-label">NG 阈值</div><div class="metric-value metric-orange">0.0250</div></div><div class="metric"><div class="data-label">异常持续时间</div><div class="metric-value">-- <small>s</small></div></div><div class="metric"><div class="data-label">异常扇区</div><div class="metric-value">--</div></div><div class="metric"><div class="data-label">扇区最大值</div><div class="metric-value">--</div></div></div><div class="sector-summary"><span>检测区域</span><strong>0.65R — 0.95R · 24 扇区</strong></div></section>
          <section class="panel chart-panel"><div class="panel-heading"><span class="panel-title">S_water 历史曲线</span><span class="chart-legend"><i/> S_water　 <b>┄</b> NG 阈值</span></div><div class="chart-body"><svg viewBox="0 0 520 140" preserveAspectRatio="none" role="img" aria-label="暂无检测数据，显示异常阈值参考线"><path d="M50 18H510 M50 66H510 M50 115H510" class="chart-grid"/><path d="M50 66H510" class="chart-threshold"/><text x="5" y="20">0.050</text><text x="5" y="68">0.025</text><text x="5" y="118">0.000</text><text x="50" y="133">-5s</text><text x="480" y="133">当前</text><text x="285" y="99" class="chart-empty">等待检测数据</text></svg></div></section>
        </div>
      </main>
      <footer class="bottom-bar"><div class="file-info"><span>视频</span><strong :title="activeName">{{ activeName }}</strong><i/>{{ videoWidth }} × {{ videoHeight }}<i/>FPS --</div><div class="footer-actions"><button class="btn btn-muted" @click="restart">↻ 从头播放</button><button class="btn btn-danger" :disabled="!isPlaying" @click="stop">■ 暂停播放</button><button class="btn btn-primary" disabled title="接入检测算法后可用">⇩ 导出检测结果</button></div></footer>
    </template>

    <input ref="fileInput" class="hidden-input" type="file" accept="video/*,.mp4,.mov,.avi,.mkv,.webm,.m4v" aria-label="选择视频文件" @change="onFileChange"/>
    <div v-if="modalOpen" class="modal-mask" @click.self="closeCalibration">
      <section class="calibration-modal" role="dialog" aria-modal="true" aria-labelledby="calibration-title">
        <div class="modal-header"><div><h2 id="calibration-title">标注晶圆位置</h2><p>点击画面中的晶圆中心，再点击晶圆边缘</p></div><button type="button" class="modal-close" title="取消标注" aria-label="取消标注" @click="closeCalibration">×</button></div>
        <div class="modal-body"><div class="calibration-stage" :class="{ 'stage-ready': !!draftWidth }" @click="onCalibrationClick"><video ref="calibrationVideo" :src="previewUrl" playsinline muted preload="metadata" @loadedmetadata="onCalibrationMetadata" @timeupdate="onCalibrationTime" @error="notify('无法读取视频，请尝试其他格式')"/><svg class="roi-overlay" :viewBox="draftOverlaySize" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><template v-if="center"><path :d="`M ${center.x-13} ${center.y} h26 M ${center.x} ${center.y-13} v26`" class="calib-cross"/><circle :cx="center.x" :cy="center.y" r="4" fill="#59d7ff"/></template><template v-if="draftCalibration"><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius" class="calib-wafer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * .95" class="ring-outer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * .65" class="ring-inner"/></template></svg><div class="frame-label">绿色：检测外缘　蓝色：内缘</div></div>
          <div class="calib-timeline"><span>定位画面</span><input type="range" aria-label="标注画面位置" min="0" :max="calibrationDuration || 1" step="0.01" :value="calibrationTime" :style="{ '--progress': calibrationProgress + '%' }" :disabled="!calibrationDuration" @input="onCalibrationSeek"/><span>{{ formatTime(calibrationTime) }} / {{ formatTime(calibrationDuration) }}</span></div>
          <div class="calibration-status"><strong>{{ calibrationPhase }}</strong><span>{{ calibrationMeasure }}</span></div>
        </div>
        <div class="modal-footer"><span>{{ calibrationPhase }}</span><div><button class="btn btn-muted" :disabled="!center" @click="resetDraft">重置</button><button class="btn btn-primary" :disabled="!readyToConfirm" @click="confirmCalibration">确认</button></div></div>
      </section>
    </div>
    <div v-if="message" class="toast" role="status">{{ message }}</div>
  </div>
</template>