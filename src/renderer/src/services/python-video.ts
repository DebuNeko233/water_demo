/** Python owns decoding and inference; UI receives one image/result pair per decoded frame. */
import { toPlainCalibration } from './detection-payload.mjs'
import type { DetectionResult, WaferCalibration } from './water-detection'

export interface AnnotatedFrame {
  ended: boolean
  frame_index?: number
  time_s?: number
  jpeg_base64?: string
  result?: DetectionResult
}
export interface VideoStreamSession {
  session_id: string
  fps: number
  width: number
  height: number
  duration_s: number
  frame_count: number
  frame: AnnotatedFrame
}
export function openPythonVideo(
  filePath: string, calibration: WaferCalibration, timeS: number,
): Promise<VideoStreamSession> {
  return window.desktop.backend.request<VideoStreamSession>('POST', '/api/video/open', {
    file_path: filePath,
    calibration: toPlainCalibration(calibration),
    start_time_s: timeS,
    // No client-specified detector configuration. Python resolves the
    // last administrator-approved settings for every operator session.
  })
}
export function readPythonVideoFrame(sessionId: string): Promise<AnnotatedFrame> {
  return window.desktop.backend.request<AnnotatedFrame>('POST', '/api/video/next', { session_id: sessionId })
}
export function seekPythonVideo(sessionId: string, timeS: number): Promise<AnnotatedFrame> {
  return window.desktop.backend.request<AnnotatedFrame>('POST', '/api/video/seek', {
    session_id: sessionId, time_s: timeS,
  })
}
