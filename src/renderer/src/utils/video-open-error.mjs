/** Only recognized backend errors may instruct users to replace an approved ROI. */
export function describeVideoOpenError(reason) {
  const text = String(reason)
  const marker = 'Python API 422: '
  const start = text.indexOf(marker)
  if (start >= 0) {
    try {
      const response = JSON.parse(text.slice(start + marker.length))
      const detail = response?.detail
      if (detail?.code === 'CALIBRATION_RESOLUTION_MISMATCH' &&
          [detail.video_width, detail.video_height, detail.calibration_width,
            detail.calibration_height].every(Number.isInteger)) {
        return {
          kind: 'mismatch',
          message: `视频 ${detail.video_width}×${detail.video_height}，标定 ${detail.calibration_width}×${detail.calibration_height}。需重新标注晶圆位置`,
        }
      }
      if (detail?.code === 'VIDEO_RESOLUTION_TOO_LARGE' &&
          [detail.video_width, detail.video_height].every(Number.isInteger)) {
        return {
          kind: 'oversize',
          message: `视频 ${detail.video_width}×${detail.video_height} 超过支持的分辨率范围，请在视频源设置中降低分辨率`,
        }
      }
      if (typeof detail === 'string' && detail.length <= 150 &&
          !detail.toLowerCase().includes('rtsp://')) {
        return { kind: 'other', message: detail }
      }
    } catch {
      // An invalid API reply should not be shown verbatim in the UI.
    }
  }
  return { kind: 'other', message: '视频打开失败，请检查视频源或查看启动日志' }
}
