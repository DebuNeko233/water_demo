/**
 * Fixed, video-time-aligned analysis lattice. Do not use a rolling duration
 * throttle: 30 FPS with a >=125 ms gate accidentally sends every 4th frame
 * (7.5 FPS), rather than an actual eight samples in each second.
 *
 * Browser presentation may still skip source frames. If the renderer is slow,
 * missed ticks are skipped instead of sending old frames after newer ones.
 */
export function createFrameSampler(fps = 8) {
  if (!Number.isFinite(fps) || fps <= 0) throw new RangeError('Sampling FPS must be positive')
  let lastBucket = -1
  let lastTime = -Infinity
  return {
    shouldSample(timeSeconds) {
      if (!Number.isFinite(timeSeconds) || timeSeconds < 0 || timeSeconds <= lastTime) return false
      const bucket = Math.floor(timeSeconds * fps + 1e-8)
      if (bucket <= lastBucket) return false
      lastBucket = bucket
      lastTime = timeSeconds
      return true
    },
    reset() { lastBucket = -1; lastTime = -Infinity },
  }
}
