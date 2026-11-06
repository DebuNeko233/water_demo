/**
 * Coordinates for an object-fit: contain video.
 * The returned bounds exclude letterboxing and match an SVG with the same
 * box and preserveAspectRatio="xMidYMid meet".
 */
export function containRect(boxWidth, boxHeight, videoWidth, videoHeight) {
  if (![boxWidth, boxHeight, videoWidth, videoHeight].every(v => Number.isFinite(v) && v > 0)) {
    return null
  }
  const scale = Math.min(boxWidth / videoWidth, boxHeight / videoHeight)
  const width = videoWidth * scale
  const height = videoHeight * scale
  return { left: (boxWidth - width) / 2, top: (boxHeight - height) / 2, width, height, scale }
}

/** Map a browser pointer position into the original, unscaled video pixels. */
export function clientToVideo(clientX, clientY, box, videoWidth, videoHeight) {
  const fit = containRect(box.width, box.height, videoWidth, videoHeight)
  if (!fit) return null
  const localX = clientX - box.left - fit.left
  const localY = clientY - box.top - fit.top
  if (localX < 0 || localY < 0 || localX > fit.width || localY > fit.height) return null
  return { x: Math.max(0, Math.min(videoWidth, localX / fit.scale)),
    y: Math.max(0, Math.min(videoHeight, localY / fit.scale)) }
}

/** Coordinate of a point clicked inside the already fitted viewport.
 * Unlike clientToVideo, there is no second contain/letterbox transformation.
 */
export function viewportToVideo(clientX, clientY, rect, videoWidth, videoHeight) {
  if (![clientX, clientY, rect.left, rect.top, rect.width, rect.height, videoWidth, videoHeight]
    .every(v => Number.isFinite(v)) || rect.width <= 0 || rect.height <= 0 ||
    videoWidth <= 0 || videoHeight <= 0) return null
  const x = (clientX - rect.left) * videoWidth / rect.width
  const y = (clientY - rect.top) * videoHeight / rect.height
  if (x < 0 || x > videoWidth || y < 0 || y > videoHeight) return null
  return { x, y }
}

/**
 * SVG viewBox requires four values: min-x, min-y, width, height.
 * Using only "width height" invalidates the viewBox and causes source-pixel
 * centers to render offset from the cursor when the video is scaled.
 */
export function sourceViewBox(width, height) {
  const w = Number.isFinite(width) && width > 0 ? width : 1
  const h = Number.isFinite(height) && height > 0 ? height : 1
  return `0 0 ${w} ${h}`
}
