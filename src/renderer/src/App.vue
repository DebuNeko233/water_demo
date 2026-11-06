<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { containRect, viewportToVideo, sourceViewBox } from './utils/videoGeometry.mjs'
import { seekToReferenceFrame } from './utils/videoPlayback.mjs'
import { svgSourceToClient } from './utils/svgCoordinates.mjs'
import { calibrationPointerToSource } from './utils/calibrationPointer.mjs'
import { useWaterDetection } from './composables/useWaterDetection'

type Point = { x: number; y: number }
type Calibration = { cx: number; cy: number; radius: number; width: number; height: number }
type CoordinateCheck = {
  click: Point
  source: Point
  actualError: number
  legacyError: number | null
  layerMismatch: number
  videoRect: string
  svgRect: string
  viewportRect: string
  resolution: string
  devicePixelRatio: number
  method: 'svg' | 'viewport'
  timestamp: number
}
type ClickMarker = { x: number; y: number; kind: '中心' | '边缘' }

type Screen = 'welcome' | 'monitor'
const screen = ref<Screen>('welcome')
const fileInput = ref<HTMLInputElement | null>(null)
const calibrationVideo = ref<HTMLVideoElement | null>(null)
const monitorVideo = ref<HTMLVideoElement | null>(null)
const detection = useWaterDetection(monitorVideo)
const detectorResult = detection.result
const detectorStatus = detection.status
const detectorError = detection.error
const detectionRecords = detection.records
const analysisFPS = detection.sourceFrameRate
const calibrationStage = ref<HTMLElement | null>(null)
const calibrationSvg = ref<SVGSVGElement | null>(null)
const coordinateCheckEnabled = ref(false)
const clickMarkers = ref<ClickMarker[]>([])
const coordinateCheck = ref<CoordinateCheck | null>(null)
const monitorStage = ref<HTMLElement | null>(null)
const calibrationBox = ref({ width: 0, height: 0 })
const monitorBox = ref({ width: 0, height: 0 })
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
const calibrationFrameTime = ref(0)
const calibrationFrameReady = ref(false)
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

const readyToConfirm = computed(() => !!center.value && radius.value !== null && radius.value >= 20 && draftWidth.value > 0 && draftHeight.value > 0)
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
const overlaySize = computed(() => sourceViewBox(videoWidth.value, videoHeight.value))
const draftOverlaySize = computed(() => sourceViewBox(draftWidth.value, draftHeight.value))
const detectionThreshold = computed(() => detectorResult.value?.s_water_threshold ?? 0.025)
const resultStatus = computed(() => {
  if (detectorStatus.value === 'error') return 'ERROR'
  if (detectorStatus.value === 'connecting') return '连接中'
  if (detectorStatus.value === 'idle') return '--'
  return detectorResult.value?.status ?? 'WARMUP'
})
const resultDescription = computed(() => {
  if (detectorStatus.value === 'error') return detectorError.value
  if (detectorStatus.value === 'connecting') return '正在连接 Python 检测服务'
  if (detectorStatus.value === 'idle') return '播放视频后开始检测'
  if (resultStatus.value === 'WARMUP') return '正在累积帧差与驻留窗口'
  if (resultStatus.value === 'NG') return '检测到持续水流异常'
  return '水流检测正常'
})
const worstSector = computed(() => {
  const idx = detectorResult.value?.max_sector_idx ?? -1
  return idx < 0 || !detectorResult.value ||
    detectorResult.value.max_sector_score < detectorResult.value.sector_threshold
    ? '--' : `${idx + 1} · ${Math.round(idx * 360 / 24)}°`
})
const chartMaximum = computed(() => {
  const points = detectorResult.value?.history ?? []
  return Math.max(0.05, detectionThreshold.value * 1.4,
    ...points.map(point => point.s_water * 1.15))
})
const chartThresholdY = computed(() => 115 - detectionThreshold.value / chartMaximum.value * 97)
const chartPoints = computed(() => {
  const samples = detectorResult.value?.history ?? []
  if (!samples.length) return ''
  const rightTime = samples[samples.length - 1].time_s
  return samples.map(point => {
    const x = 50 + 460 * Math.max(0, Math.min(1, 1 - (rightTime - point.time_s) / 5))
    const y = 115 - 97 * Math.min(1, point.s_water / chartMaximum.value)
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
})

function fittedViewportStyle(box: { width: number; height: number }, width: number, height: number): Record<string, string> {
  const rect = containRect(box.width, box.height, width, height)
  // The single fitted rectangle contains BOTH the video and overlay.
  if (!rect) return { display: 'none' }
  return {
    left: rect.left + 'px',
    top: rect.top + 'px',
    width: rect.width + 'px',
    height: rect.height + 'px',
  }
}
const calibrationViewportStyle = computed(() =>
  fittedViewportStyle(calibrationBox.value, draftWidth.value, draftHeight.value),
)
const monitorViewportStyle = computed(() =>
  fittedViewportStyle(monitorBox.value, videoWidth.value, videoHeight.value),
)
let calibrationResizeObserver: ResizeObserver | undefined
let monitorResizeObserver: ResizeObserver | undefined
watch(calibrationStage, (node) => {
  calibrationResizeObserver?.disconnect()
  calibrationResizeObserver = undefined
  calibrationBox.value = { width: 0, height: 0 }
  if (!node) return
  calibrationResizeObserver = new ResizeObserver(([entry]) => {
    if (entry) calibrationBox.value = { width: entry.contentRect.width, height: entry.contentRect.height }
  })
  calibrationResizeObserver.observe(node)
}, { flush: 'post' })
watch(monitorStage, (node) => {
  monitorResizeObserver?.disconnect()
  monitorResizeObserver = undefined
  monitorBox.value = { width: 0, height: 0 }
  if (!node) return
  monitorResizeObserver = new ResizeObserver(([entry]) => {
    if (entry) monitorBox.value = { width: entry.contentRect.width, height: entry.contentRect.height }
  })
  monitorResizeObserver.observe(node)
}, { flush: 'post' })

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
  clickMarkers.value = []
  coordinateCheck.value = null
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
  calibrationFrameReady.value = false
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
  calibrationFrameReady.value = false
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
function onCalibrationFrameReady(): void {
  const video = calibrationVideo.value
  calibrationFrameReady.value = !!video &&
    video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !video.seeking
}
function onCalibrationSeek(event: Event): void {
  const v = calibrationVideo.value
  if (!v || !calibrationDuration.value) return
  calibrationFrameReady.value = false
  v.currentTime = Number((event.target as HTMLInputElement).value)
  calibrationTime.value = v.currentTime
  resetDraft()
}
function formatRect(rect: DOMRect | undefined): string {
  return rect
    ? `${rect.left.toFixed(1)},${rect.top.toFixed(1)} | ${rect.width.toFixed(1)}×${rect.height.toFixed(1)}`
    : 'N/A'
}
function onCalibrationClick(event: MouseEvent): void {
  if (!modalOpen.value) return
  // Metadata is sufficient for coordinate entry. Requiring loadeddata or
  // HAVE_CURRENT_DATA here could silently disable all clicks for files whose
  // browser preload stops after metadata.
  if (!draftWidth.value || !draftHeight.value) {
    notify('视频尚未读取到画面尺寸，请稍后重试')
    return
  }

  const boxRect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const svg = calibrationSvg.value
  const mapped = calibrationPointerToSource(
    svg, event.clientX, event.clientY, boxRect,
    draftWidth.value, draftHeight.value,
  )
  if (!mapped) {
    notify('点击位置不在视频画面内，请在画面上点击')
    return
  }
  const point = mapped.point
  const videoRect = calibrationVideo.value?.getBoundingClientRect()
  const svgRect = svg?.getBoundingClientRect()
  const oldPoint = viewportToVideo(event.clientX, event.clientY, boxRect, draftWidth.value, draftHeight.value)
  const projected = svg ? svgSourceToClient(svg, point.x, point.y) : null
  const legacyProjected = svg && oldPoint ? svgSourceToClient(svg, oldPoint.x, oldPoint.y) : null

  if (coordinateCheckEnabled.value) {
    coordinateCheck.value = {
      click: { x: event.clientX, y: event.clientY },
      source: point,
      actualError: projected ? Math.hypot(projected.x - event.clientX, projected.y - event.clientY) : NaN,
      legacyError: legacyProjected
        ? Math.hypot(legacyProjected.x - event.clientX, legacyProjected.y - event.clientY) : null,
      layerMismatch: videoRect && svgRect ? Math.max(
        Math.abs(videoRect.left - svgRect.left), Math.abs(videoRect.top - svgRect.top),
        Math.abs(videoRect.width - svgRect.width), Math.abs(videoRect.height - svgRect.height),
      ) : NaN,
      videoRect: formatRect(videoRect),
      svgRect: formatRect(svgRect),
      viewportRect: formatRect(boxRect),
      resolution: `${draftWidth.value}×${draftHeight.value}`,
      devicePixelRatio: window.devicePixelRatio,
      method: mapped.method,
      timestamp: calibrationVideo.value?.currentTime ?? 0,
    }
    if (radius.value === null) {
      clickMarkers.value = [...clickMarkers.value,
        { x: event.clientX, y: event.clientY, kind: center.value ? '边缘' : '中心' }]
    }
  }

  if (radius.value !== null) return
  if (!center.value) {
    center.value = point
  } else {
    const r = Math.hypot(point.x - center.value.x, point.y - center.value.y)
    if (r < 20) {
      notify('半径过小，请重新点击边缘')
      if (coordinateCheckEnabled.value) clickMarkers.value = clickMarkers.value.slice(0, -1)
      return
    }
    radius.value = r
  }
}
async function copyCoordinateCheck(): Promise<void> {
  const result = coordinateCheck.value
  if (!result) return
  const lines = [
    'ZeboVision 标注坐标校验',
    `时间: ${result.timestamp.toFixed(3)}s; 视频: ${result.resolution}; DPR: ${result.devicePixelRatio}`,
    `鼠标(client): ${result.click.x.toFixed(2)}, ${result.click.y.toFixed(2)}`,
    `SVG原图像素: ${result.source.x.toFixed(2)}, ${result.source.y.toFixed(2)}`,
    `SVG绘制偏差: ${result.actualError.toFixed(3)}px; 旧映射偏差: ${result.legacyError?.toFixed(3) ?? 'N/A'}px`,
    `映射方式: ${result.method}; 视频/SVG盒差: ${result.layerMismatch.toFixed(3)}px`,
    `视频矩形: ${result.videoRect}`,
    `SVG矩形: ${result.svgRect}`,
    `点击层矩形: ${result.viewportRect}`,
  ]
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    notify('坐标校验数据已复制')
  } catch {
    notify('复制失败，请截图校验数据')
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
  // Calibration is tied to a decoded frame, not just to the video file.
  const selectedTime = calibrationVideo.value?.currentTime ?? calibrationTime.value
  calibrationFrameTime.value = Number.isFinite(selectedTime) ? selectedTime : 0
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
  detection.invalidate()
  modalOpen.value = false
  screen.value = 'monitor'
  await nextTick()
  if (replacing && monitorVideo.value) {
    // A new source will seek in onMainMetadata after its duration is available.
    monitorVideo.value.load()
  } else if (monitorVideo.value) {
    // The existing video must show the EXACT frame that was just annotated.
    currentTime.value = seekToReferenceFrame(monitorVideo.value, calibrationFrameTime.value)
    isPlaying.value = false
    if (!monitorVideo.value.seeking) void detection.start(nextCalibration)
  }
}
function onMainFrameReady(): void {
  // loadeddata provides an actual decoded frame even for a video that remains paused.
  if (calibration.value && monitorVideo.value && !monitorVideo.value.seeking &&
      detectorStatus.value === 'idle') void detection.start(calibration.value)
}
function onMainPlay(): void {
  isPlaying.value = true
  // Always retry with the currently confirmed calibration, never a previous
  // video's geometry retained by a stale session.
  if (calibration.value && (detectorStatus.value === 'idle' || detectorStatus.value === 'error')) {
    void detection.start(calibration.value)
  } else {
    detection.onPlay()
  }
}
function onMainPause(): void {
  isPlaying.value = false
  detection.stopCapture()
}
function onMainSeeking(): void {
  detection.onSeekStart()
}
function onMainSeeked(): void {
  if (calibration.value && detectorStatus.value === 'idle') void detection.start(calibration.value)
}
function onMainMetadata(): void {
  const video = monitorVideo.value
  if (!video) return
  videoWidth.value = video.videoWidth
  videoHeight.value = video.videoHeight
  duration.value = Number.isFinite(video.duration) ? video.duration : 0
  // Previously this unconditionally reset to t=0 and auto-played, so a wafer
  // annotated at e.g. 01:12 appeared misplaced in a different frame.
  detection.invalidate()
  currentTime.value = seekToReferenceFrame(video, calibrationFrameTime.value)
  isPlaying.value = false
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
  detection.invalidate()
  calibrationResizeObserver?.disconnect()
  monitorResizeObserver?.disconnect()
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
          <div class="video-stage" ref="monitorStage">
            <div class="video-fit" :style="monitorViewportStyle">
              <video ref="monitorVideo" class="video-element" :src="activeUrl" playsinline preload="metadata" @loadedmetadata="onMainMetadata" @loadeddata="onMainFrameReady" @timeupdate="onMainTime" @play="onMainPlay" @pause="onMainPause" @ended="onMainPause" @seeking="onMainSeeking" @seeked="onMainSeeked" @error="videoError = '视频解码失败，请更换其他格式的视频'" />
              <svg v-if="calibration" class="roi-overlay" :viewBox="overlaySize" preserveAspectRatio="none" aria-hidden="true">
                <circle :cx="calibration.cx" :cy="calibration.cy" :r="calibration.radius" class="wafer-outline"/>
                <circle :cx="calibration.cx" :cy="calibration.cy" :r="calibration.radius * .95" class="ring-outer"/>
                <circle :cx="calibration.cx" :cy="calibration.cy" :r="calibration.radius * .65" class="ring-inner"/>
                <line v-for="(sector, i) in sectors" :key="i" :x1="sector.x1" :y1="sector.y1" :x2="sector.x2" :y2="sector.y2" class="sector-line" :class="{ 'sector-hot': detectorResult && detectorResult.sector_scores[i] >= detectorResult.sector_threshold }"/>
                <path :d="`M ${calibration.cx-9} ${calibration.cy} h18 M ${calibration.cx} ${calibration.cy-9} v18`" class="center-mark"/>
              </svg>
            </div>
            <span class="viewport-label">检测画面</span>
            <span class="video-legend">参考帧 {{ formatTime(calibrationFrameTime) }} · 白色虚线：晶圆边缘 R　绿色：0.95R　蓝色：0.65R</span>
            <div v-if="videoError" class="video-error">{{ videoError }}</div>
          </div>
          <div class="video-footer">
            <div class="timeline-header"><span>视频进度</span><span>{{ Math.round(progress) }}% 已播放</span></div>
            <input class="progress-range" type="range" aria-label="视频播放进度" min="0" :max="duration || 1" step="0.01" :value="currentTime" :style="{ '--progress': progress + '%' }" :disabled="!duration" @input="onMainSeek"/>
            <div class="playback"><div class="playback-left"><button title="后退 5 秒" aria-label="后退 5 秒" @click="jump(-5)">↶</button><button :title="isPlaying ? '暂停' : '播放'" :aria-label="isPlaying ? '暂停' : '播放'" @click="togglePlay">{{ isPlaying ? 'Ⅱ' : '▶' }}</button><button title="前进 5 秒" aria-label="前进 5 秒" @click="jump(5)">↷</button><span>{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span></div><span class="rate">1.0×</span></div>
          </div>
        </section>

        <div class="right-column">
          <section class="panel result-panel"><div><div class="data-label">当前检测结果</div><div class="status-unavailable" :class="{ 'status-good': resultStatus === 'OK', 'status-bad': resultStatus === 'NG', 'status-error': resultStatus === 'ERROR' }">{{ resultStatus }}</div><div class="status-description" :title="resultDescription">{{ resultDescription }}</div></div><div class="result-divider"/><div><div class="data-label">S_water · 当前值</div><div class="result-score">{{ detectorResult ? detectorResult.s_water.toFixed(4) : '--' }}</div><div class="data-note">原算法 · {{ analysisFPS }} FPS 抽帧</div><div class="threshold-line">阈值 <b>{{ detectionThreshold.toFixed(4) }}</b></div></div></section>
          <section class="panel data-panel"><div class="panel-heading"><span class="panel-title">检测数据</span></div><div class="data-grid"><div class="metric"><div class="data-label">运行时间</div><div class="metric-value">{{ currentTime.toFixed(2) }} <small>s</small></div></div><div class="metric"><div class="data-label">S_water</div><div class="metric-value metric-blue">{{ detectorResult ? detectorResult.s_water.toFixed(4) : '--' }}</div></div><div class="metric"><div class="data-label">NG 阈值</div><div class="metric-value metric-orange">{{ detectionThreshold.toFixed(4) }}</div></div><div class="metric"><div class="data-label">异常持续时间</div><div class="metric-value">{{ detectorResult ? detectorResult.abnormal_run_s.toFixed(2) : '--' }} <small>s</small></div></div><div class="metric"><div class="data-label">异常扇区</div><div class="metric-value">{{ worstSector }}</div></div><div class="metric"><div class="data-label">扇区最大值</div><div class="metric-value">{{ detectorResult ? detectorResult.max_sector_score.toFixed(4) : '--' }}</div></div></div><div class="sector-summary"><span>检测区域</span><strong>0.65R — 0.95R · 24 扇区</strong></div></section>
          <section class="panel chart-panel"><div class="panel-heading"><span class="panel-title">S_water 历史曲线</span><span class="chart-legend"><i/> S_water　 <b>┄</b> NG 阈值</span></div><div class="chart-body"><svg viewBox="0 0 520 140" preserveAspectRatio="none" role="img" aria-label="实时水流异常检测历史曲线"><path d="M50 18H510 M50 66H510 M50 115H510" class="chart-grid"/><path :d="`M50 ${chartThresholdY}H510`" class="chart-threshold"/><polyline v-if="chartPoints" :points="chartPoints" class="chart-series"/><text x="5" y="20">{{ chartMaximum.toFixed(3) }}</text><text x="5" :y="chartThresholdY + 2">{{ detectionThreshold.toFixed(3) }}</text><text x="5" y="118">0.000</text><text x="50" y="133">-5s</text><text x="480" y="133">当前</text><text v-if="!chartPoints" x="285" y="99" class="chart-empty">等待检测数据</text></svg></div></section>
        </div>
      </main>
      <footer class="bottom-bar"><div class="file-info"><span>视频</span><strong :title="activeName">{{ activeName }}</strong><i/>{{ videoWidth }} × {{ videoHeight }}<i/>FPS --</div><div class="footer-actions"><button class="btn btn-muted" @click="restart">↻ 从头播放</button><button class="btn btn-danger" :disabled="!isPlaying" @click="stop">■ 暂停播放</button><button class="btn btn-primary" :disabled="!detectionRecords.length" title="导出当前检测时段的逐帧采样数据" @click="detection.exportCSV">⇩ 导出检测结果</button></div></footer>
    </template>

    <input ref="fileInput" class="hidden-input" type="file" accept="video/*,.mp4,.mov,.avi,.mkv,.webm,.m4v" aria-label="选择视频文件" @change="onFileChange"/>
    <div v-if="modalOpen" class="modal-mask" @click.self="closeCalibration">
      <section class="calibration-modal" role="dialog" aria-modal="true" aria-labelledby="calibration-title">
        <div class="modal-header"><div><h2 id="calibration-title">标注晶圆位置</h2><p>点击画面中的晶圆中心，再点击晶圆边缘</p></div><div class="modal-header-actions"><button v-if="false" type="button" class="coordinate-toggle" :aria-pressed="coordinateCheckEnabled" @click="coordinateCheckEnabled = !coordinateCheckEnabled">{{ coordinateCheckEnabled ? '坐标校验：开' : '坐标校验：关' }}</button><button type="button" class="modal-close" title="取消标注" aria-label="取消标注" @click="closeCalibration">×</button></div></div>
        <div class="modal-body"><div ref="calibrationStage" class="calibration-stage" :class="{ 'stage-ready': !!draftWidth }"><div class="video-fit calibration-fit" :style="calibrationViewportStyle" @click="onCalibrationClick"><video ref="calibrationVideo" :src="previewUrl" playsinline muted preload="metadata" @loadedmetadata="onCalibrationMetadata" @loadeddata="onCalibrationFrameReady" @timeupdate="onCalibrationTime" @seeking="calibrationFrameReady = false" @seeked="onCalibrationFrameReady" @error="notify('无法读取视频，请尝试其他格式')"/><svg ref="calibrationSvg" class="roi-overlay" :viewBox="draftOverlaySize" preserveAspectRatio="none" aria-hidden="true"><template v-if="center"><path :d="`M ${center.x-13} ${center.y} h26 M ${center.x} ${center.y-13} v26`" class="calib-cross"/><circle :cx="center.x" :cy="center.y" r="4" fill="#59d7ff"/></template><template v-if="draftCalibration"><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius" class="calib-wafer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * .95" class="ring-outer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * .65" class="ring-inner"/></template></svg></div><div class="frame-label">灰色虚线：晶圆边缘 R　绿色：0.95R　蓝色：0.65R</div></div>
          <div class="calib-timeline"><span>定位画面</span><input type="range" aria-label="标注画面位置" min="0" :max="calibrationDuration || 1" step="0.01" :value="calibrationTime" :style="{ '--progress': calibrationProgress + '%' }" :disabled="!calibrationDuration" @input="onCalibrationSeek"/><span>{{ formatTime(calibrationTime) }} / {{ formatTime(calibrationDuration) }}</span></div>
          <div class="calibration-status"><strong>{{ calibrationPhase }}</strong><span>{{ calibrationMeasure }}</span></div>
          <div v-if="coordinateCheckEnabled" class="coordinate-debug">
            <div class="coordinate-debug-heading"><span><b>坐标校验</b>　红点：鼠标实际落点　蓝色十字：绘制位置</span><button type="button" class="coordinate-copy" :disabled="!coordinateCheck" @click="copyCoordinateCheck">复制数据</button></div>
            <div v-if="coordinateCheck" class="coordinate-debug-values">
              <span>点击 {{ coordinateCheck.click.x.toFixed(0) }}, {{ coordinateCheck.click.y.toFixed(0) }}</span>
              <span>原图 {{ coordinateCheck.source.x.toFixed(1) }}, {{ coordinateCheck.source.y.toFixed(1) }}</span>
              <span>标记误差 <b :class="{ 'coordinate-error': coordinateCheck.actualError > 1 }">{{ coordinateCheck.actualError.toFixed(2) }} px</b></span>
              <span>视频/SVG 层差 {{ coordinateCheck.layerMismatch.toFixed(2) }} px</span>
              <span>映射 {{ coordinateCheck.method === 'svg' ? 'SVG 矩阵' : '显示区回退' }}</span><span>旧算法误差 {{ coordinateCheck.legacyError?.toFixed(2) ?? '--' }} px</span>
              <small>原始分辨率 {{ coordinateCheck.resolution }} · DPR {{ coordinateCheck.devicePixelRatio }} · 帧 {{ coordinateCheck.timestamp.toFixed(3) }} s</small>
            </div>
            <div v-else class="coordinate-debug-hint">请先点击画面中的晶圆中心</div>
          </div>
        </div>
        <div class="modal-footer"><span>{{ calibrationPhase }}</span><div><button class="btn btn-muted" :disabled="!center" @click="resetDraft">重置</button><button class="btn btn-primary" :disabled="!readyToConfirm" @click="confirmCalibration">确认</button></div></div>
      </section>
      <template v-if="coordinateCheckEnabled">
        <div v-for="(marker, index) in clickMarkers" :key="index" class="raw-click-marker" :class="{ 'marker-edge': marker.kind === '边缘' }" :style="{ left: marker.x + 'px', top: marker.y + 'px' }"><span>{{ marker.kind }}点击</span></div>
      </template>
    </div>
    <div v-if="message" class="toast" role="status">{{ message }}</div>
  </div>
</template>