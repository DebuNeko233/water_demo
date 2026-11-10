/**
 * Single-flight, frame+result-synchronized Python video playback.
 *
 * No HTMLVideoElement is used on the monitor screen. Python reads every
 * original decoded frame and runs the unchanged main1_chn.py WaterDetector.
 * UI requests one annotated frame at a time (backpressure) and paces display
 * to source FPS. Pausing stops requests; seeking requests a new detector state.
 */
import { onBeforeUnmount, ref } from 'vue'
import { describeVideoOpenError } from '../utils/video-open-error.mjs'
import type { DetectionResult, WaferCalibration } from '../services/water-detection'
import type { StageMode } from '../services/station-profile'
import {
  openPythonVideo, readPythonVideoFrame, seekPythonVideo,
  type AnnotatedFrame,
} from '../services/python-video'

export type StreamStatus = 'idle' | 'connecting' | 'warming' | 'running' | 'error'

export function usePythonVideoStream() {
  const status = ref<StreamStatus>('idle')
  const result = ref<DetectionResult | null>(null)
  const error = ref('')
  const openIssue = ref<'mismatch' | 'oversize' | null>(null)
  const records = ref<DetectionResult[]>([])
  const renderedFrame = ref('')
  const sourceFrameRate = ref(0)
  const currentTime = ref(0)
  const duration = ref(0)
  const isLive = ref(false)
  const sourceKind = ref<'file' | 'rtsp' | 'usb'>('file')
  const videoWidth = ref(0)
  const videoHeight = ref(0)
  const isPlaying = ref(false)
  let sessionId: string | null = null
  let reachedEnd = false
  let version = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let pendingRead: Promise<AnnotatedFrame> | null = null
  let commandChain: Promise<void> = Promise.resolve()

  function pause(): void {
    isPlaying.value = false
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function invalidate(): void {
    pause()
    version += 1
    sessionId = null
    reachedEnd = false
    status.value = 'idle'
    result.value = null
    records.value = []
    isLive.value = false
    sourceKind.value = 'file'
    renderedFrame.value = ''
    error.value = ''
    openIssue.value = null
  }

  async function showFrame(packet: AnnotatedFrame, expectedVersion: number): Promise<void> {
    if (packet.ended || !packet.jpeg_base64 || !packet.result ||
        packet.time_s === undefined) return
    const uri = 'data:image/jpeg;base64,' + packet.jpeg_base64
    // Decode before advancing both the image and its related metrics.
    // Otherwise the <img> could still show the previous frame during the
    // browser's asynchronous JPEG decode, despite newer S_water data.
    const ready = new Image()
    ready.src = uri
    await ready.decode()
    if (expectedVersion !== version) return
    renderedFrame.value = uri
    result.value = packet.result
    currentTime.value = packet.time_s
    records.value.push(packet.result)
    if (isLive.value && records.value.length > 3000) records.value.splice(0, 1000)
    status.value = packet.result.history_ready ? 'running' : 'warming'
    error.value = ''
  }

  function displayFrameRate(): number {
    // A camera still analyzes every source frame in Python. Only the UI
    // preview is limited to 20 FPS to avoid oversized IPC/JPEG/DOM churn.
    const fps = sourceFrameRate.value
    return Math.max(1, isLive.value ? Math.min(20, fps) : fps)
  }

  function play(): void {
    if (isPlaying.value || !sessionId || status.value === 'error' || status.value === 'connecting') return
    if (reachedEnd) {
      void seek(0, true)
      return
    }
    isPlaying.value = true
    schedule(version, 1000 / displayFrameRate())
  }

  function schedule(expectedVersion: number, delayMs: number): void {
    if (!isPlaying.value || expectedVersion !== version) return
    timer = setTimeout(() => {
      timer = null
      void advance(expectedVersion)
    }, Math.max(0, delayMs))
  }

  async function advance(expectedVersion: number): Promise<void> {
    const sid = sessionId
    if (!isPlaying.value || !sid || expectedVersion !== version) return
    const started = performance.now()
    const reading = readPythonVideoFrame(sid)
    pendingRead = reading
    try {
      const packet = await reading
      if (version !== expectedVersion || sid !== sessionId) return
      if (packet.ended) {
        reachedEnd = true
        currentTime.value = duration.value
        pause()
        return
      }
      await showFrame(packet, expectedVersion)
      schedule(expectedVersion, 1000 / displayFrameRate() - (performance.now() - started))
    } catch (reason) {
      if (version !== expectedVersion) return
      pause()
      status.value = 'error'
      error.value = 'Python 视频帧读取失败：' + String(reason)
    } finally {
      if (pendingRead === reading) pendingRead = null
    }
  }

  async function open(
    filePath: string, calibration: WaferCalibration,
    timeS: number, autoplay = false, stageMode: StageMode = 'single',
  ): Promise<void> {
    invalidate()
    const epoch = version
    status.value = 'connecting'
    // Serializing open with the preceding read and seek prevents a previous
    // response from advancing the newly opened Python VideoCapture.
    const request = commandChain.then(async () => {
      if (pendingRead) await pendingRead.catch(() => undefined)
      return openPythonVideo(filePath, calibration, Math.max(0, timeS), stageMode)
    })
    commandChain = request.then(() => undefined, () => undefined)
    try {
      const session = await request
      if (epoch !== version) return
      sessionId = session.session_id
      sourceFrameRate.value = session.fps
      duration.value = session.duration_s
      isLive.value = session.is_live
      sourceKind.value = session.source_kind
      videoWidth.value = session.width
      videoHeight.value = session.height
      await showFrame(session.frame, epoch)
      if (epoch === version && autoplay) play()
    } catch (reason) {
      if (epoch !== version) return
      status.value = 'error'
      const failure = describeVideoOpenError(reason)
      openIssue.value =
        failure.kind === 'mismatch' || failure.kind === 'oversize' ? failure.kind : null
      error.value = failure.message
    }
  }

  async function seek(timeS: number, resume = isPlaying.value): Promise<void> {
    const sid = sessionId
    if (!sid || isLive.value) return
    pause()
    version += 1
    const epoch = version
    status.value = 'connecting'
    reachedEnd = false
    const request = commandChain.then(async () => {
      if (pendingRead) await pendingRead.catch(() => undefined)
      return seekPythonVideo(sid, Math.max(0, Math.min(duration.value || timeS, timeS)))
    })
    commandChain = request.then(() => undefined, () => undefined)
    try {
      const packet = await request
      if (epoch !== version) return
      result.value = null
      records.value = []
      await showFrame(packet, epoch)
      if (epoch === version && resume) play()
    } catch (reason) {
      if (epoch !== version) return
      status.value = 'error'
      error.value = 'Python 跳转视频失败：' + String(reason)
    }
  }

  function exportCSV(): void {
    if (!records.value.length) return
    // Original main1_chn.py CSV headings and precision for side-by-side comparison.
    const columns = ['frame', 'time_s', 'status', 's_water', 'abnormal_run_s',
      'max_sector_index', 'max_sector_start_deg', 'max_sector_end_deg', 'max_sector_score',
      'stage', 'position_confidence', 'position_reason']
    const csv = [columns.join(','), ...records.value.map(x => {
      const idx = x.max_sector_idx
      const start = idx >= 0 ? 360 * idx / x.sector_count : ''
      const end = idx >= 0 ? 360 * (idx + 1) / x.sector_count : ''
      return [x.frame_index ?? '', x.time_s.toFixed(6), x.status, x.s_water.toFixed(6),
        x.abnormal_run_s.toFixed(6), idx, start, end,
        x.max_sector_score.toFixed(6), x.stage ?? 'P1',
        (x.position_confidence ?? 1).toFixed(4),
        x.reason ?? ''].join(',')
    })].join('\r\n')
    const href = URL.createObjectURL(new Blob(['\ufeff', csv], {type:'text/csv;charset=utf-8'}))
    const a = document.createElement('a')
    a.href = href
    a.download = 'zebovision-detection.csv'
    a.click()
    URL.revokeObjectURL(href)
  }

  onBeforeUnmount(invalidate)
  return {
    status, result, error, openIssue, records, renderedFrame, sourceFrameRate,
    currentTime, duration, isLive, sourceKind, videoWidth, videoHeight, isPlaying,
    open, seek, play, pause, invalidate, exportCSV,
  }
}
