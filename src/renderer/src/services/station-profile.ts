/** Device-local three-station calibration and raw OpenCV reference frames. */
import type { WaferCalibration } from './water-detection'

export type StageKey = 'P1' | 'P2' | 'P3'
export type StageMode = 'single' | 'auto'
export type ReferenceGroup = 'default' | 'nozzle_a' | 'nozzle_b'
export const STAGES: StageKey[] = ['P1', 'P2', 'P3']

export interface StageReference {
  id: string
  group?: ReferenceGroup
  time_s: number
  source: string
}
export interface StageConfig {
  calibration: WaferCalibration | null
  references: StageReference[]
}
export interface StationProfile {
  version: number
  ready: boolean
  minimum_references: number
  stages: Record<StageKey, StageConfig>
}
export function getStationProfile(): Promise<StationProfile> {
  return window.desktop.backend.request<StationProfile>('GET', '/api/stations/profile')
}
export function saveStationCalibration(stage: StageKey, calibration: WaferCalibration, adminToken: string): Promise<StationProfile> {
  return window.desktop.backend.request<StationProfile>('POST', '/api/stations/calibration', {
    stage, calibration, admin_token: adminToken,
  })
}
export function captureStationReference(stage: StageKey, filePath: string, timeS: number, group: ReferenceGroup, adminToken: string): Promise<StationProfile> {
  return window.desktop.backend.request<StationProfile>('POST', '/api/stations/reference', {
    stage, file_path: filePath, time_s: timeS, group, admin_token: adminToken,
  })
}
export function removeStationReference(stage: StageKey, referenceId: string, adminToken: string): Promise<StationProfile> {
  return window.desktop.backend.request<StationProfile>('POST', '/api/stations/reference/remove', {
    stage, reference_id: referenceId, admin_token: adminToken,
  })
}

export function exportStationArchive(filePath: string, adminToken: string): Promise<{ saved: boolean; reference_count: number }> {
  return window.desktop.backend.request('POST', '/api/stations/archive/export', {
    file_path: filePath, admin_token: adminToken,
  })
}

export function importStationArchive(filePath: string, adminToken: string): Promise<{ profile: StationProfile; settings: import('../utils/algorithm-settings.mjs').AlgorithmSettings; reference_count: number }> {
  return window.desktop.backend.request('POST', '/api/stations/archive/import', {
    file_path: filePath, admin_token: adminToken,
  })
}
