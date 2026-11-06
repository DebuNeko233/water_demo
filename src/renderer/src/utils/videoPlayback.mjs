/**
 * Keep the exact image used during calibration visible when switching
 * from the calibration video to the monitoring video.
 *
 * The user chooses a time while the video is paused; a new <video> element
 * starts at t=0 unless this seek is applied on loadedmetadata.
 */
export function seekToReferenceFrame(video, time) {
  const requested = Number.isFinite(time) && time >= 0 ? time : 0
  const duration = Number.isFinite(video.duration) && video.duration >= 0
    ? video.duration : null
  // Avoid seeking past the last decodable frame.
  const t = duration === null ? requested : Math.min(requested, Math.max(0, duration - 0.01))
  video.pause()
  video.currentTime = t
  return t
}
