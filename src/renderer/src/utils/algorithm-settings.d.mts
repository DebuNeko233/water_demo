export interface AlgorithmSettings {
  inner_radius_ratio: number
  outer_radius_ratio: number
  diff_threshold: number
  history_seconds: number
  persistence_threshold: number
  s_water_threshold: number
  ng_hold_seconds: number
  recover_hold_seconds: number
  sector_count: number
  sector_threshold: number
  blur_ksize: number
}
export interface AlgorithmField {
  key: keyof AlgorithmSettings
  label: string
  unit: string
  min: number
  max: number
  step: number
}
export interface AlgorithmGroup {
  title: string
  hint: string
  fields: AlgorithmField[]
}
export declare const DEFAULT_ALGORITHM_SETTINGS: Readonly<AlgorithmSettings>
export declare const ALGORITHM_GROUPS: AlgorithmGroup[]
export function copyAlgorithmSettings(value: AlgorithmSettings): AlgorithmSettings
export function validateAlgorithmSettings(value: AlgorithmSettings): string | null
export function readAlgorithmSettings(storage?: Pick<Storage, 'getItem'>): AlgorithmSettings
export function storeAlgorithmSettings(storage: Pick<Storage, 'setItem'> | undefined, value: AlgorithmSettings): void
