/** Original main1_chn.py detector defaults. Keep in sync with Python DetectorSettings. */
export const DEFAULT_ALGORITHM_SETTINGS = Object.freeze({
  inner_radius_ratio: 0.65,
  outer_radius_ratio: 0.95,
  diff_threshold: 8,
  history_seconds: 0.50,
  persistence_threshold: 0.50,
  s_water_threshold: 0.025,
  ng_hold_seconds: 0.50,
  recover_hold_seconds: 0.60,
  sector_count: 24,
  sector_threshold: 0.05,
  blur_ksize: 3,
})

export const ALGORITHM_GROUPS = [
  { title: '检测区域', hint: '以已标定的晶圆半径 R 为基准',
    fields: [
      { key: 'inner_radius_ratio', label: '内半径比例', unit: 'R', min: 0.05, max: 1.5, step: 0.01 },
      { key: 'outer_radius_ratio', label: '外半径比例', unit: 'R', min: 0.05, max: 1.5, step: 0.01 },
      { key: 'sector_count', label: '圆周扇区数量', unit: '个', min: 4, max: 72, step: 1 },
      { key: 'sector_threshold', label: '扇区异常阈值', unit: '', min: 0, max: 1, step: 0.005 },
    ] },
  { title: '图像与时序', hint: '基于灰度帧差及像素运动驻留',
    fields: [
      { key: 'diff_threshold', label: '灰度帧差阈值', unit: '灰度级', min: 0, max: 255, step: 0.5 },
      { key: 'blur_ksize', label: '高斯模糊核大小', unit: 'px', min: 0, max: 15, step: 2 },
      { key: 'history_seconds', label: '驻留统计窗口', unit: 's', min: 0.125, max: 3, step: 0.125 },
      { key: 'persistence_threshold', label: '像素驻留比例', unit: '', min: 0, max: 1, step: 0.05 },
    ] },
  { title: 'OK / NG 判定', hint: '连续异常与恢复使用不同时间门槛',
    fields: [
      { key: 's_water_threshold', label: 'S_water 异常阈值', unit: '', min: 0, max: 1, step: 0.005 },
      { key: 'ng_hold_seconds', label: '进入 NG 持续时间', unit: 's', min: 0, max: 30, step: 0.1 },
      { key: 'recover_hold_seconds', label: '恢复 OK 持续时间', unit: 's', min: 0, max: 30, step: 0.1 },
    ] },
]

const storageKey = 'zebovision.algorithm-settings.v1'

export function copyAlgorithmSettings(value) {
  const out = {}
  for (const key of Object.keys(DEFAULT_ALGORITHM_SETTINGS)) out[key] = value[key]
  return out
}

/** Returns null when valid, otherwise an actionable error message. */
export function validateAlgorithmSettings(value) {
  if (!value || typeof value !== 'object') return '请填写检测参数'
  for (const group of ALGORITHM_GROUPS) {
    for (const field of group.fields) {
      const v = value[field.key]
      if (typeof v !== 'number' || !Number.isFinite(v)) return field.label + '必须是有效数字'
      if (v < field.min || v > field.max) {
        return field.label + '应在 ' + field.min + '～' + field.max + ' 之间'
      }
    }
  }
  if (value.inner_radius_ratio >= value.outer_radius_ratio) return '内半径比例必须小于外半径比例'
  if (!Number.isInteger(value.sector_count)) return '扇区数量必须是整数'
  if (!Number.isInteger(value.blur_ksize) ||
      (value.blur_ksize > 1 && value.blur_ksize % 2 === 0)) {
    return '模糊核大小只能是 0、1 或 3～15 的奇数'
  }
  return null
}

export function readAlgorithmSettings(storage) {
  try {
    const raw = storage?.getItem(storageKey)
    if (!raw) return copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS)
    const parsed = JSON.parse(raw)
    if (validateAlgorithmSettings(parsed)) return copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS)
    return copyAlgorithmSettings(parsed)
  } catch {
    return copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS)
  }
}

export function storeAlgorithmSettings(storage, value) {
  const problem = validateAlgorithmSettings(value)
  if (problem) throw new Error(problem)
  storage?.setItem(storageKey, JSON.stringify(copyAlgorithmSettings(value)))
}
