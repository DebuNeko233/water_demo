/**
 * Bounded, frame-synchronous sampling of the video the user actually sees.
 * The original Python detector runs on 8 analyzed samples/second (not full FPS).
 * An in-flight request is never queued twice, so slow machines drop samples
 * instead of letting old results drift far behind the video timeline.
 */
import { onBeforeUnmount, ref, type Ref } from 'vue'
import {
  ANALYSIS_FPS, analyzeVideoFrame, beginDetection,
  type DetectionResult, type WaferCalibration,
} from '../services/water-detection'

export type InspectionConnection = 'idle' | 'connecting' | 'warming' | 'running' | 'error'

export function useWaterDetection(videoRef: Ref<HTMLVideoElement | null>) {
  const status = ref<InspectionConnection>('idle')
  const result = ref<DetectionResult | null>(null)
  const error = ref('')
  const sourceFrameRate = ref(ANALYSIS_FPS)
  const records = ref<DetectionResult[]>([])
  let sessionId: string | null = null
  let epoch = 0
  let frameInFlight = false
  let lastSent = -Infinity
  let callbackId: number | null = null
  let fallbackTimer: ReturnType<typeof setInterval> | null = null
  let currentCalibration: WaferCalibration | null = null
  // Serialize session creation so rapid seeks cannot let an older HTTP start
  // overwrite the latest session in the Python singleton.
  let startChain: Promise<void> = Promise.resolve()
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d', { alpha: false })

  function stopCapture(): void {
    const video = videoRef.value
    if (callbackId !== null && video?.cancelVideoFrameCallback) video.cancelVideoFrameCallback(callbackId)
    callbackId = null
    if (fallbackTimer !== null) clearInterval(fallbackTimer)
    fallbackTimer = null
  }

  function invalidate(): void {
    epoch += 1
    stopCapture()
    sessionId = null
    lastSent = -Infinity
    frameInFlight = false
    result.value = null
    records.value = []
    status.value = 'idle'
    error.value = ''
  }

  async function start(calibration: WaferCalibration): Promise<void> {
    invalidate()
    currentCalibration = { ...calibration }
    const version = epoch
    status.value = 'connecting'
    if (!context) {
      error.value = '无法创建视频画面采集器'
      status.value = 'error'
      return
    }
    try {
      const pendingStart = startChain.then(() => beginDetection(calibration))
      startChain = pendingStart.then(() => undefined, () => undefined)
      const session = await pendingStart
      if (version !== epoch) return
      sessionId = session.session_id
      sourceFrameRate.value = session.sample_fps
      status.value = 'warming'
      if (!videoRef.value?.paused) startCapture()
    } catch (reason) {
      if (version !== epoch) return
      status.value = 'error'
      error.value = '检测启动失败：' + String(reason)
    }
  }

  async function sample(time_s: number): Promise<void> {
    const video = videoRef.value
    const sid = sessionId
    const version = epoch
    if (!video || !sid || !context || frameInFlight || video.seeking || video.paused ||
      video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      time_s - lastSent < 1 / ANALYSIS_FPS - 0.01 || time_s <= lastSent) return
    frameInFlight = true
    lastSent = time_s
    try {
      const width = video.videoWidth
      const height = video.videoHeight
      if (!width || !height) return
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      context.drawImage(video, 0, 0, width, height)
      const jpegBase64 = canvas.toDataURL('image/jpeg', 0.62).split(',')[1]
      const next = await analyzeVideoFrame(sid, time_s, jpegBase64)
      if (version !== epoch || sessionId !== sid) return
      result.value = next
      records.value.push(next)
      status.value = next.history_ready ? 'running' : 'warming'
      error.value = ''
    } catch (reason) {
      if (version !== epoch) return
      status.value = 'error'
      error.value = '检测帧处理失败：' + String(reason)
      stopCapture()
    } finally {
      if (version === epoch) frameInFlight = false
    }
  }

  function startCapture(): void {
    stopCapture()
    const video = videoRef.value
    if (!video || video.paused || !sessionId || status.value === 'error') return
    if (typeof video.requestVideoFrameCallback === 'function') {
      const next = () => {
        if (video.paused || !sessionId || status.value === 'error') return
        callbackId = video.requestVideoFrameCallback((_now, metadata) => {
          callbackId = null
          if (!video.paused && !video.seeking) {
            void sample(metadata.mediaTime)
            next()
          }
        })
      }
      next()
    } else {
      fallbackTimer = setInterval(() => { void sample(video.currentTime) }, 100)
    }
  }

  function onPlay(): void {
    if (!sessionId && currentCalibration && status.value !== 'connecting') {
      void start(currentCalibration)
    } else if (sessionId) {
      startCapture()
    }
  }

  // A seek changes the meaning of the temporal persistence window.
  function onSeekStart(): void {
    invalidate()
  }
  function onSeekEnd(): void {
    if (currentCalibration) void start(currentCalibration)
  }

  function exportCSV(): void {
    if (!records.value.length) return
    const headings = ['time_s', 'status', 's_water', 'abnormal_run_s', 'max_sector_idx', 'max_sector_score']
    const csv = [headings.join(','), ...records.value.map(x => [
      x.time_s.toFixed(3), x.status, x.s_water.toFixed(6), x.abnormal_run_s.toFixed(3),
      x.max_sector_idx, x.max_sector_score.toFixed(6),
    ].join(','))].join('\r\n')
    const url = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'zebovision-detection.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  onBeforeUnmount(() => { invalidate() })

  return {
    status, result, error, records, sourceFrameRate,
    start, invalidate, startCapture, stopCapture, onPlay, onSeekStart, onSeekEnd, exportCSV,
  }
}