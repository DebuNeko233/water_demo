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
