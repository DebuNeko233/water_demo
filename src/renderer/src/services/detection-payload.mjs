/** Build an IPC-safe snapshot from a Vue reactive calibration object. */
export function toPlainCalibration(value) {
  return {
    cx: value.cx,
    cy: value.cy,
    radius: value.radius,
    width: value.width,
    height: value.height,
  }
}
