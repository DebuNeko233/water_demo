/** Only passes frames from the currently visible HTMLVideoElement to Python.
 * Python WaterDetector (from main1_chn.py) owns all scoring and NG hysteresis.
 */
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
  max_sector_idx: number
  max_sector_score: number
  sector_scores: number[]
  abnormal_run_s: number
  time_s: number
  history: DetectionHistoryPoint[]
}

export async function beginDetection(calibration: WaferCalibration): Promise<DetectionSession> {
  return window.desktop.backend.request<DetectionSession>('POST', '/api/detection/start', {
    calibration: {
      cx: calibration.cx,
      cy: calibration.cy,
      radius: calibration.radius,
      width: calibration.width,
      height: calibration.height,
    },
    sample_fps: ANALYSIS_FPS,
  })
}

export async function analyzeVideoFrame(sessionId: string, time: number, jpegBase64: string): Promise<DetectionResult> {
  return window.desktop.backend.request<DetectionResult>('POST', '/api/detection/frame', {
    session_id: sessionId,
    time_s: time,
    jpeg_base64: jpegBase64,
  })
}