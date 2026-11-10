/** Python owns decoding and inference; UI receives one image/result pair per decoded frame. */
import { toPlainCalibration } from './detection-payload.mjs'
import type { DetectionResult, WaferCalibration } from './water-detection'
import type { StageMode } from './station-profile'

export interface FramePerformance {
  frames: number
  decode_ms: number
  analysis_ms: number
  preview_ms: number
}

export interface AnnotatedFrame {
  ended: boolean
  /** Intermediate results for file batches; all decoded frames were scored. */
  samples?: DetectionResult[]
  performance?: FramePerformance
  frame_index?: number
  time_s?: number
  jpeg_base64?: string
  result?: DetectionResult
  detecting?: boolean
}
export interface VideoStreamSession {
  session_id: string
  fps: number
  width: number
  height: number
  duration_s: number
  frame_count: number
  stage_mode: StageMode
  is_live: boolean
  source_kind: 'file' | 'rtsp' | 'usb'
  detecting: boolean
  frame: AnnotatedFrame
}
export function openPythonVideo(
  filePath: string, calibration: WaferCalibration, timeS: number,
  stageMode: StageMode = 'single', detecting = true,
): Promise<VideoStreamSession> {
  return window.desktop.backend.request<VideoStreamSession>('POST', '/api/video/open', {
    file_path: filePath,
    calibration: toPlainCalibration(calibration),
    start_time_s: timeS,
    stage_mode: stageMode,
    detecting,
    // No client-specified detector configuration. Python resolves the
    // last administrator-approved settings for every operator session.
  })
}
export function readPythonVideoFrame(sessionId: string, batchFrames = 1): Promise<AnnotatedFrame> {
  return window.desktop.backend.request<AnnotatedFrame>('POST', '/api/video/next', {
    session_id: sessionId, batch_frames: batchFrames,
  })
}
export function setPythonDetection(sessionId: string, enabled: boolean): Promise<{ detecting: boolean }> {
  return window.desktop.backend.request<{ detecting: boolean }>(
    'POST', enabled ? '/api/video/detection/start' : '/api/video/detection/stop',
    { session_id: sessionId },
  )
}

export function stopPythonVideo(sessionId: string): Promise<{ stopped: boolean }> {
  return window.desktop.backend.request<{ stopped: boolean }>('POST', '/api/video/stop', {
    session_id: sessionId,
  })
}

export function seekPythonVideo(sessionId: string, timeS: number): Promise<AnnotatedFrame> {
  return window.desktop.backend.request<AnnotatedFrame>('POST', '/api/video/seek', {
    session_id: sessionId, time_s: timeS,
  })
}
