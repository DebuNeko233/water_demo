/**
 * Single-flight, frame+result-synchronized Python video playback.
 *
 * No HTMLVideoElement is used on the monitor screen. Python reads every
 * original decoded frame and runs the unchanged main1_chn.py WaterDetector.
 * UI requests one annotated frame at a time (backpressure) and paces display
 * to source FPS. Pausing stops requests; seeking requests a new detector state.
 */
import { onBeforeUnmount, ref, type Ref } from 'vue'
import type { AlgorithmSettings } from '../utils/algorithm-settings.mjs'
import type { DetectionResult, WaferCalibration } from '../services/water-detection'
import {
  openPythonVideo, readPythonVideoFrame, seekPythonVideo,
  type AnnotatedFrame,
} from '../services/python-video'

export type StreamStatus = 'idle' | 'connecting' | 'warming' | 'running' | 'error'

export function usePythonVideoStream(settings: Readonly<Ref<AlgorithmSettings>>) {
  const status = ref<StreamStatus>('idle')
  const result = ref<DetectionResult | null>(null)
  const error = ref('')
  const records = ref<DetectionResult[]>([])
  const renderedFrame = ref('')
  const sourceFrameRate = ref(0)
  const currentTime = ref(0)
  const duration = ref(0)
  const videoWidth = ref(0)
  const videoHeight = ref(0)
  const isPlaying = ref(false)
  let sessionId: string | null = null
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
    status.value = 'idle'
    result.value = null
    records.value = []
    renderedFrame.value = ''
    error.value = ''
  }

  function showFrame(packet: AnnotatedFrame): void {
    if (packet.ended || !packet.jpeg_base64 || !packet.result ||
        packet.time_s === undefined) return
    // The image and its metadata are one atomic response from Python.
    renderedFrame.value = 'data:image/jpeg;base64,' + packet.jpeg_base64
    result.value = packet.result
    currentTime.value = packet.time_s
    records.value.push(packet.result)
    status.value = packet.result.history_ready ? 'running' : 'warming'
    error.value = ''
  }

  function play(): void {
    if (isPlaying.value || !sessionId || status.value === 'error' || status.value === 'connecting') return
    isPlaying.value = true
    schedule(version, 1000 / Math.max(1, sourceFrameRate.value))
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
        pause()
        return
      }
      showFrame(packet)
      schedule(expectedVersion, 1000 / Math.max(1, sourceFrameRate.value) - (performance.now() - started))
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
    timeS: number, autoplay = false,
  ): Promise<void> {
    invalidate()
    const epoch = version
    status.value = 'connecting'
    // Serializing open with the preceding read and seek prevents a previous
    // response from advancing the newly opened Python VideoCapture.
    const request = commandChain.then(async () => {
      if (pendingRead) await pendingRead.catch(() => undefined)
      return openPythonVideo(filePath, calibration, Math.max(0, timeS), settings.value)
    })
    commandChain = request.then(() => undefined, () => undefined)
    try {
      const session = await request
      if (epoch !== version) return
      sessionId = session.session_id
      sourceFrameRate.value = session.fps
      duration.value = session.duration_s
      videoWidth.value = session.width
      videoHeight.value = session.height
      showFrame(session.frame)
      if (autoplay) play()
    } catch (reason) {
      if (epoch !== version) return
      status.value = 'error'
      error.value = 'Python 打开视频失败：' + String(reason)
    }
  }

  async function seek(timeS: number, resume = isPlaying.value): Promise<void> {
    const sid = sessionId
    if (!sid) return
    pause()
    version += 1
    const epoch = version
    status.value = 'connecting'
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
      showFrame(packet)
      if (resume) play()
    } catch (reason) {
      if (epoch !== version) return
      status.value = 'error'
      error.value = 'Python 跳转视频失败：' + String(reason)
    }
  }

  function exportCSV(): void {
    if (!records.value.length) return
    const columns = ['time_s', 'status', 's_water', 'abnormal_run_s', 'max_sector_idx', 'max_sector_score']
    const csv = [columns.join(','), ...records.value.map(x => [
      x.time_s.toFixed(6), x.status, x.s_water.toFixed(6),
      x.abnormal_run_s.toFixed(6), x.max_sector_idx, x.max_sector_score.toFixed(6),
    ].join(','))].join('\r\n')
    const href = URL.createObjectURL(new Blob(['\ufeff', csv], {type:'text/csv;charset=utf-8'}))
    const a = document.createElement('a')
    a.href = href
    a.download = 'zebovision-detection.csv'
    a.click()
    URL.revokeObjectURL(href)
  }

  onBeforeUnmount(invalidate)
  return {
    status, result, error, records, renderedFrame, sourceFrameRate,
    currentTime, duration, videoWidth, videoHeight, isPlaying,
    open, seek, play, pause, invalidate, exportCSV,
  }
}
