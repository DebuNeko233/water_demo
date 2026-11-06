export interface PlainCalibration {
  cx: number
  cy: number
  radius: number
  width: number
  height: number
}
export function toPlainCalibration(calibration: PlainCalibration): PlainCalibration
