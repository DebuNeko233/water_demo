/** Only passes frames from the currently visible HTMLVideoElement to Python.
 * Python WaterDetector (from main1_chn.py) owns all scoring and NG hysteresis.
 */
import { toPlainCalibration } from './detection-payload.mjs'
import { copyAlgorithmSettings, type AlgorithmSettings } from '../utils/algorithm-settings.mjs'

export const ANALYSIS_FPS = 8

export interface WaferCalibration {
  cx: number
  cy: number
  radius: number
  width: number
  height: number
}

export interface DetectionSession {
  session_id: string
  sample_fps: number
  s_water_threshold: number
  sector_threshold: number
  history_seconds: number
  sector_count: number
  inner_radius_ratio: number
  outer_radius_ratio: number
}

export interface DetectionHistoryPoint {
  time_s: number
  s_water: number
}

export interface DetectionResult {
  session_id: string
  status: 'WARMUP' | 'OK' | 'NG'
  s_water: number
  history_ready: boolean
  s_water_threshold: number
  sector_threshold: number
  sector_count: number
  inner_radius_ratio: number
  outer_radius_ratio: number
  max_sector_idx: number
  max_sector_score: number
  sector_scores: number[]
  abnormal_run_s: number
  time_s: number
  history: DetectionHistoryPoint[]
}

export async function beginDetection(calibration: WaferCalibration, settings: AlgorithmSettings): Promise<DetectionSession> {
  return window.desktop.backend.request<DetectionSession>('POST', '/api/detection/start', {
    calibration: toPlainCalibration(calibration),
    sample_fps: ANALYSIS_FPS,
    detector: copyAlgorithmSettings(settings),
  })
}

export async function analyzeVideoFrame(sessionId: string, time: number, pngBase64: string): Promise<DetectionResult> {
  return window.desktop.backend.request<DetectionResult>('POST', '/api/detection/frame', {
    session_id: sessionId,
    time_s: time,
    png_base64: pngBase64,
  })
}