import { viewportToVideo } from './videoGeometry.mjs'
import { svgClientToSource } from './svgCoordinates.mjs'

/** Resolve a pointer even when an unloaded or detached SVG has no screen CTM.
 * The fitted viewport is the event target, so its rectangle is a safe fallback.
 * Returns null only when the click is outside the picture or sizes are invalid.
 */
export function calibrationPointerToSource(svg, clientX, clientY, rect, width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  let svgPoint = null
  try {
    if (svg) svgPoint = svgClientToSource(svg, clientX, clientY)
  } catch {
    // Some browser graphics paths cannot expose getScreenCTM during startup.
  }
  if (svgPoint) return { point: svgPoint, method: 'svg' }
  const point = viewportToVideo(clientX, clientY, rect, width, height)
  return point ? { point, method: 'viewport' } : null
}
