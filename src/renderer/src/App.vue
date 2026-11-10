<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { containRect, viewportToVideo, sourceViewBox } from './utils/videoGeometry.mjs'
import { svgSourceToClient } from './utils/svgCoordinates.mjs'
import { calibrationPointerToSource } from './utils/calibrationPointer.mjs'
import { usePythonVideoStream } from './composables/usePythonVideoStream'
import {
  STAGES, getStationProfile, saveStationCalibration, saveSingleCalibration,
  captureStationReference, removeStationReference, captureLiveStationReference,
  exportStationArchive, importStationArchive,
  type StageKey, type StageMode, type StationProfile, type ReferenceGroup,
} from './services/station-profile'
import AlgorithmSettingsModal from './components/AlgorithmSettingsModal.vue'
import AdminAccessDialog from './components/AdminAccessDialog.vue'
import {
  loadUserStatus, setupAdministrator, loginAdministrator,
  logoutAdministrator, saveApprovedSettings,
  type UserRole,
} from './services/user-management'
import brandIconUrl from './assets/brand-icon.ico?url'
import {
  publicVideoSource, adminVideoSource, saveVideoSource, cameraSnapshot,
  DEFAULT_VIDEO_SOURCE,
  type VideoSourceSettings, type VideoSourceStatus,
} from './services/video-source'
import {
  DEFAULT_ALGORITHM_SETTINGS, copyAlgorithmSettings,
  type AlgorithmSettings,
} from './utils/algorithm-settings.mjs'

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
const screen = ref<Screen>('monitor')
// Administrator-approved settings are stored and enforced in Python, never
// trusted from browser localStorage or a client-supplied configuration.
const algorithmSettings = ref<AlgorithmSettings>(copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS))
const videoSource = ref<VideoSourceStatus>({ kind: 'file', usb_index: 0 })
const videoSourceSettings = ref<VideoSourceSettings>({ ...DEFAULT_VIDEO_SOURCE })
const liveSnapshotUrl = ref('')
const liveSnapshotBusy = ref(false)
const currentRole = ref<UserRole>('operator')
const adminToken = ref('')
const adminConfigured = ref(false)
const adminDialogOpen = ref(false)
const adminBusy = ref(false)
const adminError = ref('')
const settingsBusy = ref(false)
let unsubscribeBackendStatus: (() => void) | undefined
const algorithmSettingsOpen = ref(false)
let settingsResumePlayback = false
const detection = usePythonVideoStream()
const renderedFrame = detection.renderedFrame
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
const activeName = ref('')
const calibration = ref<Calibration | null>(null)
const stationMode = ref<StageMode>('single')
const selectedStation = ref<StageKey>('P1')
const selectedP3Nozzle = ref<'nozzle_a' | 'nozzle_b'>('nozzle_a')
const stationProfile = ref<StationProfile | null>(null)
const stationBusy = ref(false)
const archiveBusy = ref(false)
const stationError = ref('')
let stationProfileInitialized = false
const center = ref<Point | null>(null)
const radius = ref<number | null>(null)
const draftWidth = ref(0)
const draftHeight = ref(0)
const calibrationDuration = ref(0)
const calibrationTime = ref(0)
const calibrationFrameTime = ref(0)
const calibrationFrameReady = ref(false)
const currentTime = detection.currentTime
const duration = detection.duration
const videoWidth = detection.videoWidth
const videoHeight = detection.videoHeight
const isPlaying = detection.isPlaying
const isLiveVideo = computed(() => videoSource.value.kind !== 'file')
const videoError = detection.error
const message = ref('')
let previouslyPlaying = false
let resumeAt = 0
let seekWasPlaying = false
let calibrationSnapshotVersion = 0
const seekDraft = ref<number | null>(null)
let toastTimeout: ReturnType<typeof setTimeout> | undefined

const draftCalibration = computed<Calibration | null>(() =>
  center.value && radius.value !== null && radius.value >= 20 &&
  draftWidth.value > 0 && draftHeight.value > 0
    ? { cx: center.value.x, cy: center.value.y, radius: radius.value, width: draftWidth.value, height: draftHeight.value }
    : null,
)
const readyToConfirm = computed(() =>
  stationMode.value === 'auto'
    ? !!stationProfile.value?.ready && !stationBusy.value && !!draftCalibration.value &&
      STAGES.every(s => {
        const saved = stationProfile.value?.stages[s].calibration
        return saved?.width === draftWidth.value && saved?.height === draftHeight.value
      }) &&
      (() => {
        const saved = stationProfile.value?.stages[selectedStation.value].calibration
        const draft = draftCalibration.value
        return !!saved && !!draft &&
          Math.abs(saved.cx - draft.cx) < 0.01 &&
          Math.abs(saved.cy - draft.cy) < 0.01 &&
          Math.abs(saved.radius - draft.radius) < 0.01
      })()
    : !!draftCalibration.value,
)
const selectedStageConfig = computed(() => stationProfile.value?.stages[selectedStation.value])
const currentStageReferences = computed(() => (selectedStageConfig.value?.references ?? []).filter(refItem =>
  selectedStation.value !== 'P3' || (refItem.group ?? 'nozzle_a') === selectedP3Nozzle.value,
))
const p3NozzleACount = computed(() => stationProfile.value?.stages.P3.references.filter(item =>
  (item.group ?? 'nozzle_a') === 'nozzle_a').length ?? 0)
const p3NozzleBCount = computed(() => stationProfile.value?.stages.P3.references.filter(item =>
  item.group === 'nozzle_b').length ?? 0)
const currentStageMin = computed(() => stationProfile.value?.minimum_references ?? 5)
const shownTime = computed(() => seekDraft.value ?? currentTime.value)
const progress = computed(() => duration.value > 0 ? shownTime.value / duration.value * 100 : 0)
const calibrationProgress = computed(() => calibrationDuration.value > 0 ? calibrationTime.value / calibrationDuration.value * 100 : 0)
const calibrationPhase = computed(() => !center.value ? '点击晶圆中心' : radius.value === null ? '点击晶圆边缘' : '标注完成')
const calibrationMeasure = computed(() => {
  if (!center.value) return '中心 -- · 半径 --'
  const base = `中心 (${Math.round(center.value.x)}, ${Math.round(center.value.y)})`
  return radius.value === null ? `${base} · 半径 --` : `${base} · 半径 ${Math.round(radius.value)} px`
})
const sourceLabel = computed(() => videoSource.value.kind === 'rtsp'
  ? 'RTSP 实时摄像头'
  : videoSource.value.kind === 'usb' ? 'USB 摄像头 #' + videoSource.value.usb_index : '本地视频')
const draftOverlaySize = computed(() => sourceViewBox(draftWidth.value, draftHeight.value))
const detectionThreshold = computed(() => detectorResult.value?.s_water_threshold ?? algorithmSettings.value.s_water_threshold)
const sectorThreshold = computed(() => detectorResult.value?.sector_threshold ?? algorithmSettings.value.sector_threshold)
const sectorCount = computed(() => detectorResult.value?.sector_count ?? algorithmSettings.value.sector_count)
const innerRadiusRatio = computed(() => detectorResult.value?.inner_radius_ratio ?? algorithmSettings.value.inner_radius_ratio)
const outerRadiusRatio = computed(() => detectorResult.value?.outer_radius_ratio ?? algorithmSettings.value.outer_radius_ratio)
const resultStatus = computed(() => {
  if (detectorStatus.value === 'error') return 'ERROR'
  if (detectorStatus.value === 'connecting') return '连接中'
  if (detectorStatus.value === 'idle') return '--'
  return detectorResult.value?.status ?? 'WARMUP'
})
const resultDescription = computed(() => {
  if (resultStatus.value === 'PAUSED') {
    return detectorResult.value?.reason === 'POSITION_UNSTABLE'
      ? '正在确认晶圆工位' : '未识别到可靠的晶圆工位'
  }
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
    detectorResult.value.max_sector_score < sectorThreshold.value
    ? '--' : `${idx + 1} · ${Math.round(idx * 360 / sectorCount.value)}°`
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
  void startConfiguredSource()
}

async function refreshVideoSource(): Promise<void> {
  try {
    videoSource.value = await publicVideoSource()
  } catch {
    // The backend may still be starting.
  }
}

async function refreshAdminVideoSource(): Promise<void> {
  if (!adminToken.value) return
  try {
    videoSourceSettings.value = await adminVideoSource(adminToken.value)
  } catch {
    notify('视频源配置读取失败')
  }
}

async function startConfiguredSource(): Promise<void> {
  if (!stationProfile.value) await refreshStationProfile()
  const auto = stationProfile.value?.ready
    ? stationProfile.value.stages.P1.calibration : null
  const single = stationProfile.value?.single_calibration ?? null
  const preferred = stationMode.value === 'auto' ? auto : (calibration.value ?? single)
  const chosen = preferred ?? auto ?? single
  if (!chosen) {
    if (currentRole.value === 'admin' && adminToken.value) {
      openCalibration(false)
    } else {
      notify('请切换管理员完成晶圆标注')
    }
    return
  }
  const mode: StageMode = preferred ? stationMode.value : (auto ? 'auto' : 'single')
  stationMode.value = mode
  calibration.value = chosen
  activeName.value = sourceLabel.value
  videoWidth.value = chosen.width
  videoHeight.value = chosen.height
  screen.value = 'monitor'
  seekDraft.value = null
  await detection.open('', chosen, 0, isLiveVideo.value, mode)
}

async function refreshCalibrationSnapshot(timeS = calibrationTime.value): Promise<void> {
  if (!adminToken.value || !modalOpen.value) return
  const request = ++calibrationSnapshotVersion
  liveSnapshotBusy.value = true
  stationError.value = ''
  try {
    const frame = await cameraSnapshot(adminToken.value, isLiveVideo.value ? 0 : timeS)
    if (!modalOpen.value || request !== calibrationSnapshotVersion) return
    liveSnapshotUrl.value = 'data:image/jpeg;base64,' + frame.jpeg_base64
    draftWidth.value = frame.width
    draftHeight.value = frame.height
    calibrationDuration.value = frame.duration_s
    calibrationTime.value = frame.time_s
    calibrationFrameReady.value = true
    if (stationMode.value === 'auto') selectStation(selectedStation.value)
  } catch {
    if (request === calibrationSnapshotVersion) stationError.value = '视频画面读取失败'
  } finally {
    if (request === calibrationSnapshotVersion) liveSnapshotBusy.value = false
  }
}

function resetDraft(): void {
  center.value = null
  radius.value = null
  clickMarkers.value = []
  coordinateCheck.value = null
}
function selectStation(stage: StageKey): void {
  selectedStation.value = stage
  const saved = stationProfile.value?.stages[stage].calibration
  resetDraft()
  if (saved && (!draftWidth.value ||
      (saved.width === draftWidth.value && saved.height === draftHeight.value))) {
    center.value = { x: saved.cx, y: saved.cy }
    radius.value = saved.radius
  }
  stationError.value = ''
}
async function refreshStationProfile(): Promise<void> {
  try {
    const profile = await getStationProfile()
    stationProfile.value = profile
    if (!calibration.value && profile.single_calibration) {
      calibration.value = profile.single_calibration
    }
    if (!stationProfileInitialized) {
      stationProfileInitialized = true
      const hasReferences = STAGES.some(s => profile.stages[s].references.length > 0)
      if (!modalOpen.value || hasReferences) stationMode.value = hasReferences ? 'auto' : 'single'
    }
    if (modalOpen.value && stationMode.value === 'auto' &&
        !center.value && radius.value === null) {
      selectStation(selectedStation.value)
    }
  } catch (error) {
    stationError.value = '无法读取工位配置：' + String(error)
  }
}
function chooseStationMode(mode: StageMode): void {
  if (currentRole.value !== 'admin' || !adminToken.value) return
  stationMode.value = mode
  if (mode === 'auto') {
    selectStation(selectedStation.value)
    void refreshStationProfile()
  } else {
    resetDraft()
    if (calibration.value) {
      center.value = { x: calibration.value.cx, y: calibration.value.cy }
      radius.value = calibration.value.radius
    }
  }
}
async function exportDeviceProfile(): Promise<void> {
  if (currentRole.value !== 'admin' || !adminToken.value || archiveBusy.value) return
  archiveBusy.value = true
  stationError.value = ''
  try {
    const path = await window.desktop.system.saveProfileArchive()
    if (!path) return
    const saved = await exportStationArchive(path, adminToken.value)
    notify('设备配置已导出（' + saved.reference_count + ' 张参考帧）')
  } catch (error) {
    stationError.value = '导出失败：' + String(error)
    if (algorithmSettingsOpen.value) notify('设备配置导出失败，请检查 ZIP 保存位置')
    if (String(error).includes('ADMIN_REQUIRED')) resetToOperator()
  } finally {
    archiveBusy.value = false
  }
}

async function importDeviceProfile(): Promise<void> {
  if (currentRole.value !== 'admin' || !adminToken.value || archiveBusy.value) return
  archiveBusy.value = true
  stationError.value = ''
  try {
    const path = await window.desktop.system.chooseProfileArchive()
    if (!path || !window.confirm('导入将替换本机三个工位的 ROI、参考帧和检测参数，并停止当前检测。确定继续吗？')) return
    const imported = await importStationArchive(path, adminToken.value)
    detection.invalidate()
    previouslyPlaying = false
    stationProfile.value = imported.profile
    algorithmSettings.value = copyAlgorithmSettings(imported.settings)
    stationProfileInitialized = true
    stationMode.value = imported.profile.ready ? 'auto' : 'single'
    calibration.value = imported.profile.single_calibration
      ?? imported.profile.stages.P1.calibration ?? null
    selectStation('P1')
    notify('设备配置已导入（' + imported.reference_count + ' 张参考帧），请确认后重新检测')
  } catch (error) {
    stationError.value = '导入失败，原配置已保留：' + String(error)
    if (algorithmSettingsOpen.value) notify('设备配置导入失败，原配置已保留')
    if (String(error).includes('ADMIN_REQUIRED')) resetToOperator()
  } finally {
    archiveBusy.value = false
  }
}

async function captureCurrentReference(): Promise<void> {
  if (currentRole.value !== 'admin' || !adminToken.value ||
      stationBusy.value || !draftCalibration.value) return
  const file = videoSourceSettings.value.file_path
  if (!isLiveVideo.value && !file) { stationError.value = '请先在设置中选择视频'; return }
  if (!calibrationFrameReady.value) { stationError.value = '请等待画面加载'; return }
  stationBusy.value = true
  stationError.value = ''
  try {
    // Save this position's ROI then capture a *lossless OpenCV frame* on
    // Python side; browser preview images are never used for matching.
    stationProfile.value = await saveStationCalibration(
      selectedStation.value, draftCalibration.value, adminToken.value)
    const group: ReferenceGroup = selectedStation.value === 'P3' ? selectedP3Nozzle.value : 'default'
    if (isLiveVideo.value) {
      stationProfile.value = await captureLiveStationReference(selectedStation.value, group, adminToken.value)
      await refreshCalibrationSnapshot()
    } else {
      stationProfile.value = await captureStationReference(
        selectedStation.value, file, calibrationTime.value, group, adminToken.value)
    }
    notify(selectedStation.value + ' 参考帧已采集')
  } catch (error) {
    stationError.value = String(error)
  } finally {
    stationBusy.value = false
  }
}
async function deleteCurrentReference(id: string): Promise<void> {
  if (currentRole.value !== 'admin' || !adminToken.value || stationBusy.value) return
  stationBusy.value = true
  stationError.value = ''
  try {
    stationProfile.value = await removeStationReference(selectedStation.value, id, adminToken.value)
  } catch (error) {
    stationError.value = String(error)
  } finally {
    stationBusy.value = false
  }
}
function openCalibration(existing: boolean): void {
  if (currentRole.value !== 'admin' || !adminToken.value || modalOpen.value) return
  previouslyPlaying = isPlaying.value
  resumeAt = currentTime.value
  detection.pause()
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
  stationError.value = ''
  void refreshStationProfile()
  if (stationMode.value === 'auto') selectStation(selectedStation.value)
  void nextTick(() => refreshCalibrationSnapshot(
    existing && !isLiveVideo.value ? resumeAt : 0,
  ))
}
function editCalibration(): void {
  if (currentRole.value !== 'admin' || !adminToken.value) return
  if (calibration.value) openCalibration(true)
}
function onCalibrationSeek(event: Event): void {
  calibrationTime.value = Number((event.target as HTMLInputElement).value)
  calibrationFrameReady.value = false
  if (stationMode.value === 'single') resetDraft()
}
function onCalibrationSeekEnd(): void {
  void refreshCalibrationSnapshot(calibrationTime.value)
}
function formatRect(rect: DOMRect | undefined): string {
  return rect
    ? `${rect.left.toFixed(1)},${rect.top.toFixed(1)} | ${rect.width.toFixed(1)}×${rect.height.toFixed(1)}`
    : 'N/A'
}
function onCalibrationClick(event: MouseEvent): void {
  if (!modalOpen.value || currentRole.value !== 'admin' || !adminToken.value) return
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
  calibrationSnapshotVersion++
  liveSnapshotUrl.value = ''
  if (screen.value === 'monitor' && previouslyPlaying) detection.play()
}
async function confirmCalibration(): Promise<void> {
  if (currentRole.value !== 'admin' || !adminToken.value || !readyToConfirm.value) return
  const nextCalibration = stationMode.value === 'auto'
    ? stationProfile.value?.stages.P1.calibration
    : draftCalibration.value
  if (!nextCalibration) return
  const selectedTime = calibrationTime.value
  calibrationFrameTime.value = Number.isFinite(selectedTime) ? selectedTime : 0
  if (stationMode.value === 'single') {
    try {
      stationProfile.value = await saveSingleCalibration(nextCalibration, adminToken.value)
    } catch (error) {
      stationError.value = '保存单工位标定失败：' + String(error)
      return
    }
  }
  calibration.value = nextCalibration
  videoWidth.value = nextCalibration.width
  videoHeight.value = nextCalibration.height
  modalOpen.value = false
  liveSnapshotUrl.value = ''
  screen.value = 'monitor'
  seekDraft.value = null
  activeName.value = sourceLabel.value
  // Both file and live frames enter the same unchanged Python WaterDetector.
  await nextTick()
  await detection.open('', nextCalibration,
    isLiveVideo.value ? 0 : calibrationFrameTime.value, isLiveVideo.value, stationMode.value)
}
function onMainSeek(event: Event): void {
  if (seekDraft.value === null) {
    seekWasPlaying = isPlaying.value
    detection.pause()
  }
  seekDraft.value = Number((event.target as HTMLInputElement).value)
}
function onMainSeekEnd(event: Event): void {
  const seconds = Number((event.target as HTMLInputElement).value)
  const resume = seekDraft.value !== null ? seekWasPlaying : isPlaying.value
  seekDraft.value = null
  void detection.seek(seconds, resume)
}
function togglePlay(): void {
  if (isPlaying.value) detection.pause()
  else detection.play()
}
function jump(seconds: number): void {
  if (isLiveVideo.value || !duration.value) return
  void detection.seek(Math.max(0, Math.min(duration.value, currentTime.value + seconds)))
}
function restart(): void { if (!isLiveVideo.value) void detection.seek(0, true) }
function stop(): void { detection.pause() }
async function retryPythonVideo(): Promise<void> {
  try {
    await window.desktop.backend.retry()
    if (calibration.value) {
      await detection.open('', calibration.value,
        isLiveVideo.value ? 0 : currentTime.value, isLiveVideo.value, stationMode.value)
    }
  } catch (reason) {
    notify('Python 重连失败，请查看启动日志')
    console.error('Retrying Python backend failed:', reason)
  }
}
function openPythonStartupLogs(): void {
  void window.desktop.system.openLogs('electron')
}
function windowAction(action: 'minimize' | 'toggleMaximize' | 'closeWindow'): void {
  const desktop = window.desktop
  if (!desktop?.system) return
  void desktop.system[action]()
}
async function refreshUserStatus(): Promise<void> {
  try {
    const status = await loadUserStatus()
    adminConfigured.value = status.admin_configured
    algorithmSettings.value = copyAlgorithmSettings(status.settings)
  } catch {
    // Python may still be launching; an explicit login attempt reports errors.
  }
}
function userErrorText(reason: unknown): string {
  const info = String(reason)
  if (info.includes('WRONG_PASSWORD')) return '密码错误'
  if (info.includes('LOGIN_LOCKED')) return '尝试次数过多，请稍后再试'
  if (info.includes('ADMIN_ALREADY_CONFIGURED')) return '管理员已设置，请使用密码登录'
  if (info.includes('ADMIN_REQUIRED')) return '管理员验证已失效，请重新登录'
  return '操作失败，请检查密码或后端连接'
}
function resetToOperator(): void {
  if (modalOpen.value) closeCalibration()
  currentRole.value = 'operator'
  adminToken.value = ''
  videoSourceSettings.value = { ...DEFAULT_VIDEO_SOURCE }
  adminDialogOpen.value = false
  adminError.value = ''
  if (algorithmSettingsOpen.value) cancelAlgorithmSettings()
}
function switchUser(): void {
  if (currentRole.value === 'admin') {
    const token = adminToken.value
    resetToOperator()
    void logoutAdministrator(token).catch(() => undefined)
  } else {
    adminError.value = ''
    adminDialogOpen.value = true
    void refreshUserStatus()
  }
}
async function authorizeAdministrator(password: string): Promise<void> {
  if (adminBusy.value) return
  adminBusy.value = true
  adminError.value = ''
  try {
    const login = adminConfigured.value
      ? await loginAdministrator(password)
      : await setupAdministrator(password)
    algorithmSettings.value = copyAlgorithmSettings(login.settings)
    adminConfigured.value = true
    adminToken.value = login.admin_token
    currentRole.value = 'admin'
    adminDialogOpen.value = false
    notify('已切换到管理员')
    void refreshAdminVideoSource()
    if (!calibration.value && !modalOpen.value) void refreshStationProfile()
  } catch (reason) {
    adminError.value = userErrorText(reason)
    if (String(reason).includes('ADMIN_ALREADY_CONFIGURED')) {
      adminConfigured.value = true
    }
  } finally {
    adminBusy.value = false
  }
}

function openAlgorithmSettings(): void {
  if (currentRole.value !== 'admin' || !adminToken.value ||
      screen.value !== 'monitor' || algorithmSettingsOpen.value || modalOpen.value) return
  settingsResumePlayback = isPlaying.value
  detection.pause()
  algorithmSettingsOpen.value = true
  void refreshAdminVideoSource()
}
function resumeAfterSettings(): void {
  const resume = settingsResumePlayback
  settingsResumePlayback = false
  if (resume) detection.play()
}
function cancelAlgorithmSettings(): void {
  algorithmSettingsOpen.value = false
  resumeAfterSettings()
}
async function applyVideoSourceSettings(next: VideoSourceSettings): Promise<void> {
  if (settingsBusy.value || currentRole.value !== 'admin' || !adminToken.value) return
  settingsBusy.value = true
  try {
    const saved = await saveVideoSource(next, adminToken.value)
    videoSourceSettings.value = saved.source
    videoSource.value = {
      kind: saved.source.kind,
      usb_index: saved.source.usb_index,
    }
    algorithmSettingsOpen.value = false
    settingsResumePlayback = false
    detection.invalidate()
    activeName.value = ''
    seekDraft.value = null
    notify('视频源已保存，请连接' + (saved.source.kind === 'file' ? '本地视频' : '摄像头'))
  } catch (error) {
    // Some validation errors may contain a submitted RTSP URL/password.
    // Never show the raw API body in a user-visible toast.
    notify('视频源保存失败，请检查 RTSP 地址、USB 编号或管理员登录状态')
    if (String(error).includes('ADMIN_REQUIRED')) resetToOperator()
  } finally {
    settingsBusy.value = false
  }
}

async function applyAlgorithmSettings(next: AlgorithmSettings): Promise<void> {
  if (settingsBusy.value) return
  if (currentRole.value !== 'admin' || !adminToken.value) {
    notify('只有管理员可以修改设置')
    algorithmSettingsOpen.value = false
    return
  }
  settingsBusy.value = true
  try {
    const response = await saveApprovedSettings(adminToken.value, copyAlgorithmSettings(next))
    algorithmSettings.value = copyAlgorithmSettings(response.settings)
    algorithmSettingsOpen.value = false
    const resume = settingsResumePlayback
    settingsResumePlayback = false
    notify('算法参数已应用')
    if (calibration.value) {
      await detection.open('', calibration.value,
        isLiveVideo.value ? 0 : currentTime.value, resume, stationMode.value)
    }
  } catch (reason) {
    notify(userErrorText(reason))
    if (String(reason).includes('ADMIN_REQUIRED')) resetToOperator()
  } finally {
    settingsBusy.value = false
  }
}

function onEscape(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (adminDialogOpen.value) adminDialogOpen.value = false
  else if (algorithmSettingsOpen.value) cancelAlgorithmSettings()
  else if (modalOpen.value) closeCalibration()
}
onMounted(() => {
  window.addEventListener('keydown', onEscape)
  void refreshUserStatus()
  void refreshStationProfile()
  void refreshVideoSource()
  if (window.desktop?.backend) {
    unsubscribeBackendStatus = window.desktop.backend.onStatus((status) => {
      if (status === 'ready') {
        // Backend restart always invalidates administrator authentication.
        resetToOperator()
        void refreshUserStatus()
        void refreshStationProfile()
        void refreshVideoSource()
      } else if (status === 'offline' || status === 'failed') {
        resetToOperator()
      }
    })
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEscape)
  unsubscribeBackendStatus?.()
  detection.invalidate()
  calibrationResizeObserver?.disconnect()
  monitorResizeObserver?.disconnect()
  if (toastTimeout) clearTimeout(toastTimeout)
})
</script>

<template>
  <div class="zebo-app">
    <header class="app-header">
      <div class="brand">
        <div class="brand-icon" aria-hidden="true"><img :src="brandIconUrl" alt="" /></div>
        <div class="brand-name">ZeboVision</div>
      </div>
      <div class="app-title">ZeboVision湿法清洗检测系统</div>
      <div class="header-actions">
        <span v-if="screen === 'monitor'" class="header-status"><i class="status-dot"/>{{ sourceLabel }}</span>
        <button type="button" class="role-switch" :title="currentRole === 'admin' ? '退出管理员' : '切换管理员'" :aria-label="currentRole === 'admin' ? '退出管理员' : '切换管理员'" @click="switchUser">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg>
          <span>{{ currentRole === 'admin' ? '管理员' : '操作员' }}</span>
        </button>
        <button v-if="screen === 'monitor' && currentRole === 'admin'" type="button" class="algorithm-gear" title="系统设置" aria-label="系统设置" @click="openAlgorithmSettings">
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9.671 4.136a2 2 0 0 1 4.659 0 2 2 0 0 0 2.892 1.67 2 2 0 0 1 2.33 4.033 2 2 0 0 0 0 3.34 2 2 0 0 1-2.33 4.034 2 2 0 0 0-2.892 1.67 2 2 0 0 1-4.66 0 2 2 0 0 0-2.89-1.67 2 2 0 0 1-2.33-4.033 2 2 0 0 0 0-3.34A2 2 0 0 1 6.78 5.805a2 2 0 0 0 2.891-1.67Z"/>
            <circle cx="12" cy="11.5" r="3"/>
          </svg>
        </button>
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
        <h1>{{ sourceLabel }}</h1>
        <button type="button" class="btn btn-primary welcome-select" @click="chooseVideo">{{ isLiveVideo ? '连接摄像头' : '打开视频' }}</button>
      </section>
    </main>

    <template v-else>
      <main class="workspace">
        <section class="panel video-panel">
          <div class="panel-heading"><span class="panel-title">检测画面</span><span v-if="stationMode === 'auto' && detectorResult" class="monitor-station-indicator">{{ detectorResult.stage === 'UNKNOWN' ? '工位未确认' : '工位 ' + (detectorResult.stage ?? '--') }}</span><div class="heading-actions"><button v-if="currentRole === 'admin'" class="btn btn-muted" @click="editCalibration">重新标注</button><button class="btn btn-muted" @click="chooseVideo">{{ isLiveVideo ? '重新连接' : '打开视频' }}</button></div></div>
          <div class="video-stage" ref="monitorStage">
            <div class="video-fit" :style="monitorViewportStyle">
              <img v-if="renderedFrame" class="video-element" :src="renderedFrame" alt="Python 逐帧推理后的检测画面"/>
            </div>
            <div v-if="videoError" class="video-error">
              <div class="video-error-message">{{ videoError }}</div>
              <div class="video-error-actions">
                <button class="btn btn-primary" type="button" @click="retryPythonVideo">重试连接</button>
                <button class="btn btn-muted" type="button" @click="openPythonStartupLogs">查看启动日志</button>
              </div>
            </div>
          </div>
          <div class="video-footer" :class="{ 'video-footer-live': isLiveVideo }">
            <template v-if="!isLiveVideo">
              <input class="progress-range" type="range" aria-label="视频播放进度" min="0" :max="duration || 1" step="0.01" :value="shownTime" :style="{ '--progress': progress + '%' }" :disabled="!duration" @input="onMainSeek" @change="onMainSeekEnd"/>
              <div class="playback"><div class="playback-left"><button title="后退 5 秒" aria-label="后退 5 秒" @click="jump(-5)">↶</button><button :title="isPlaying ? '暂停' : '播放'" :aria-label="isPlaying ? '暂停' : '播放'" @click="togglePlay">{{ isPlaying ? 'Ⅱ' : '▶' }}</button><button title="前进 5 秒" aria-label="前进 5 秒" @click="jump(5)">↷</button><span>{{ formatTime(shownTime) }} / {{ formatTime(duration) }}</span></div></div>
            </template>
            <div v-else class="playback live-playback"><div class="playback-left"><span class="live-label">● 实时画面</span><button :title="isPlaying ? '暂停显示' : '恢复显示'" :aria-label="isPlaying ? '暂停显示' : '恢复显示'" @click="togglePlay">{{ isPlaying ? 'Ⅱ' : '▶' }}</button><span>已运行 {{ formatTime(currentTime) }} · {{ isPlaying ? '监测中' : '显示已暂停' }}</span></div></div>
          </div>
        </section>

        <div class="right-column">
          <section class="panel result-panel"><div><div class="data-label">当前检测结果</div><div class="status-unavailable" :class="{ 'status-good': resultStatus === 'OK', 'status-bad': resultStatus === 'NG', 'status-error': resultStatus === 'ERROR' }">{{ resultStatus }}</div><div v-if="resultStatus === 'ERROR' || resultStatus === '连接中' || resultStatus === 'WARMUP' || resultStatus === 'PAUSED'" class="status-description" :title="resultDescription">{{ resultDescription }}</div></div><div class="result-divider"/><div><div class="data-label">S_water · 当前值</div><div class="result-score">{{ detectorResult && detectorResult.status !== 'PAUSED' ? detectorResult.s_water.toFixed(4) : '--' }}</div><div class="threshold-line">阈值 <b>{{ detectionThreshold.toFixed(4) }}</b></div></div></section>
          <section class="panel data-panel"><div class="panel-heading"><span class="panel-title">检测数据</span></div><div class="data-grid"><div class="metric"><div class="data-label">运行时间</div><div class="metric-value">{{ currentTime.toFixed(2) }} <small>s</small></div></div><div class="metric"><div class="data-label">S_water</div><div class="metric-value metric-blue">{{ detectorResult && detectorResult.status !== 'PAUSED' ? detectorResult.s_water.toFixed(4) : '--' }}</div></div><div class="metric"><div class="data-label">NG 阈值</div><div class="metric-value metric-orange">{{ detectionThreshold.toFixed(4) }}</div></div><div class="metric"><div class="data-label">异常持续时间</div><div class="metric-value">{{ detectorResult && detectorResult.status !== 'PAUSED' ? detectorResult.abnormal_run_s.toFixed(2) : '--' }} <small>s</small></div></div><div class="metric"><div class="data-label">异常扇区</div><div class="metric-value">{{ worstSector }}</div></div><div class="metric"><div class="data-label">扇区最大值</div><div class="metric-value">{{ detectorResult && detectorResult.status !== 'PAUSED' ? detectorResult.max_sector_score.toFixed(4) : '--' }}</div></div></div><div class="sector-summary"><span>检测区域</span><strong>{{ innerRadiusRatio.toFixed(2) }}R — {{ outerRadiusRatio.toFixed(2) }}R · {{ sectorCount }} 扇区</strong></div></section>
          <section class="panel chart-panel"><div class="panel-heading"><span class="panel-title">S_water 历史曲线</span><span class="chart-legend"><i/> S_water　 <b>┄</b> NG 阈值</span></div><div class="chart-body"><svg viewBox="0 0 520 140" preserveAspectRatio="none" role="img" aria-label="实时水流异常检测历史曲线"><path d="M50 18H510 M50 66H510 M50 115H510" class="chart-grid"/><path :d="`M50 ${chartThresholdY}H510`" class="chart-threshold"/><polyline v-if="chartPoints" :points="chartPoints" class="chart-series"/><text x="5" y="20">{{ chartMaximum.toFixed(3) }}</text><text x="5" :y="chartThresholdY + 2">{{ detectionThreshold.toFixed(3) }}</text><text x="5" y="118">0.000</text><text x="50" y="133">-5s</text><text x="480" y="133">当前</text><text v-if="!chartPoints" x="285" y="99" class="chart-empty">等待检测数据</text></svg></div></section>
        </div>
      </main>
      <footer class="bottom-bar"><div class="file-info"><span>视频</span><strong :title="activeName">{{ activeName }}</strong><i v-if="activeName"/><span v-if="activeName">{{ videoWidth }} × {{ videoHeight }} · {{ analysisFPS.toFixed(2) }} FPS</span></div><div class="footer-actions"><button v-if="!isLiveVideo" class="btn btn-muted" @click="restart">↻ 从头播放</button><button class="btn btn-danger" :disabled="!isPlaying" @click="stop">{{ isLiveVideo ? '■ 暂停显示' : '■ 暂停播放' }}</button><button class="btn btn-primary" :disabled="!detectionRecords.length" title="导出当前检测时段的逐帧采样数据" @click="detection.exportCSV">⇩ 导出检测结果</button></div></footer>
    </template>

    <AlgorithmSettingsModal v-if="algorithmSettingsOpen && currentRole === 'admin'" :settings="algorithmSettings" :source="videoSourceSettings" :busy="settingsBusy || archiveBusy" @cancel="cancelAlgorithmSettings" @save="applyAlgorithmSettings" @save-source="applyVideoSourceSettings" @import-profile="importDeviceProfile" @export-profile="exportDeviceProfile"/>
    <AdminAccessDialog v-if="adminDialogOpen" :configured="adminConfigured" :busy="adminBusy" :error="adminError" @cancel="adminDialogOpen = false" @submit="authorizeAdministrator"/>
    <div v-if="modalOpen && currentRole === 'admin'" class="modal-mask" @click.self="closeCalibration">
      <section class="calibration-modal" role="dialog" aria-modal="true" aria-labelledby="calibration-title">
        <div class="modal-header"><div><h2 id="calibration-title">标注晶圆位置</h2></div><div class="modal-header-actions"><button v-if="false" type="button" class="coordinate-toggle" :aria-pressed="coordinateCheckEnabled" @click="coordinateCheckEnabled = !coordinateCheckEnabled">{{ coordinateCheckEnabled ? '坐标校验：开' : '坐标校验：关' }}</button><button type="button" class="modal-close" title="取消标注" aria-label="取消标注" @click="closeCalibration">×</button></div></div>
        <div class="modal-body">
          <div class="station-mode-tabs" role="group" aria-label="工位标定模式">
            <button type="button" :class="{ active: stationMode === 'single' }" @click="chooseStationMode('single')">单工位</button>
            <button type="button" :class="{ active: stationMode === 'auto' }" @click="chooseStationMode('auto')">三工位自动</button>
          </div>
          <div v-if="currentRole === 'admin'" class="station-archive-actions" role="group" aria-label="设备配置导入导出">
            <button type="button" class="btn btn-muted" :disabled="archiveBusy || stationBusy" @click="exportDeviceProfile">导出设备配置 ZIP</button>
            <button type="button" class="btn btn-muted" :disabled="archiveBusy || stationBusy" @click="importDeviceProfile">导入设备配置 ZIP</button>
          </div>
          <p v-if="stationMode !== 'auto' && stationError" class="station-error" role="alert">{{ stationError }}</p>
          <div v-if="stationMode === 'auto'" class="station-setup">
            <div class="station-tabs" role="group" aria-label="选择晶圆工位">
              <button v-for="stage in STAGES" :key="stage" type="button" :class="{ active: selectedStation === stage }" @click="selectStation(stage)">
                {{ stage }} <small>{{ stationProfile?.stages[stage].references.length ?? 0 }}/{{ currentStageMin }}</small>
              </button>
            </div>
            <div v-if="selectedStation === 'P3'" class="station-nozzle-tabs" role="group" aria-label="P3 喷头参考帧组">
              <button type="button" :class="{ active: selectedP3Nozzle === 'nozzle_a' }" @click="selectedP3Nozzle = 'nozzle_a'">喷头 A · {{ p3NozzleACount }} 张</button>
              <button type="button" :class="{ active: selectedP3Nozzle === 'nozzle_b' }" @click="selectedP3Nozzle = 'nozzle_b'">喷头 B · {{ p3NozzleBCount }} 张</button>
            </div>
            <div class="station-reference-controls">
              <button type="button" class="btn btn-primary" :disabled="!draftCalibration || stationBusy || (selectedStageConfig?.references.length ?? 0) >= 12" @click="captureCurrentReference">
                {{ stationBusy ? '采集中…' : '保存 ROI 并采集当前帧' }}
              </button>
              <span>{{ selectedStation === 'P3' ? '同一 P3 ROI，每种喷头分别采集至少 ' + currentStageMin + ' 张参考帧' : '每个工位至少 ' + currentStageMin + ' 张不同画面的参考帧' }}</span>
            </div>
            <div v-if="currentStageReferences.length" class="station-reference-list">
              <span v-for="refItem in currentStageReferences" :key="refItem.id" class="station-reference-chip">
                {{ refItem.source }} · {{ refItem.source.endsWith('camera') ? '实时抓拍' : formatTime(refItem.time_s) }}
                <button type="button" :disabled="stationBusy" :aria-label="'删除' + selectedStation + '参考帧'" @click="deleteCurrentReference(refItem.id)">×</button>
              </span>
            </div>
            <p v-if="stationError" class="station-error" role="alert">{{ stationError }}</p>
          </div>
          <div ref="calibrationStage" class="calibration-stage" :class="{ 'stage-ready': !!draftWidth }"><div class="video-fit calibration-fit" :style="calibrationViewportStyle" @click="onCalibrationClick"><img v-if="liveSnapshotUrl" class="live-calibration-image" :src="liveSnapshotUrl" alt="标定视频画面"/><svg ref="calibrationSvg" class="roi-overlay" :viewBox="draftOverlaySize" preserveAspectRatio="none" aria-hidden="true"><template v-if="center"><path :d="`M ${center.x-13} ${center.y} h26 M ${center.x} ${center.y-13} v26`" class="calib-cross"/><circle :cx="center.x" :cy="center.y" r="4" fill="#59d7ff"/></template><template v-if="draftCalibration"><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius" class="calib-wafer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * outerRadiusRatio" class="ring-outer"/><circle :cx="draftCalibration.cx" :cy="draftCalibration.cy" :r="draftCalibration.radius * innerRadiusRatio" class="ring-inner"/></template></svg></div></div>
          <div v-if="isLiveVideo" class="live-calibration-controls"><button type="button" class="btn btn-muted" :disabled="liveSnapshotBusy" @click="refreshCalibrationSnapshot()">{{ liveSnapshotBusy ? '抓拍中…' : '刷新画面' }}</button></div>
          <div v-else class="calib-timeline"><span>定位画面</span><input type="range" aria-label="标注画面位置" min="0" :max="calibrationDuration || 1" step="0.01" :value="calibrationTime" :style="{ '--progress': calibrationProgress + '%' }" :disabled="!calibrationDuration" @input="onCalibrationSeek" @change="onCalibrationSeekEnd"/><span>{{ formatTime(calibrationTime) }} / {{ formatTime(calibrationDuration) }}</span></div>
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
        <div class="modal-footer"><span>{{ stationMode === 'auto' ? (stationProfile?.ready ? '三工位已就绪' : '请完成三个工位的 ROI 与参考帧') : calibrationPhase }}</span><div><button class="btn btn-muted" :disabled="!center" @click="resetDraft">重置</button><button class="btn btn-primary" :disabled="!readyToConfirm" @click="confirmCalibration">确认</button></div></div>
      </section>
      <template v-if="coordinateCheckEnabled">
        <div v-for="(marker, index) in clickMarkers" :key="index" class="raw-click-marker" :class="{ 'marker-edge': marker.kind === '边缘' }" :style="{ left: marker.x + 'px', top: marker.y + 'px' }"><span>{{ marker.kind }}点击</span></div>
      </template>
    </div>
    <div v-if="message" class="toast" role="status">{{ message }}</div>
  </div>
</template>