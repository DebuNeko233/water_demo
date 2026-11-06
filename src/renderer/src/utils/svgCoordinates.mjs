/**
 * Convert a browser pointer to SVG source coordinates using the actual matrix
 * the browser uses when painting the marker. No separate CSS fit assumptions.
 */
export function svgClientToSource(svg, clientX, clientY) {
  const m = svg?.getScreenCTM?.()
  const vb = svg?.viewBox?.baseVal
  if (!m || !vb || ![clientX, clientY, m.a, m.b, m.c, m.d, m.e, m.f, vb.x, vb.y, vb.width, vb.height].every(Number.isFinite)) return null
  const det = m.a * m.d - m.b * m.c
  if (Math.abs(det) < 1e-12 || vb.width <= 0 || vb.height <= 0) return null
  const dx = clientX - m.e
  const dy = clientY - m.f
  const x = (m.d * dx - m.c * dy) / det
  const y = (-m.b * dx + m.a * dy) / det
  if (x < vb.x || y < vb.y || x > vb.x + vb.width || y > vb.y + vb.height) return null
  return { x, y }
}
export function svgSourceToClient(svg, x, y) {
  const m = svg?.getScreenCTM?.()
  if (!m || ![x, y, m.a, m.b, m.c, m.d, m.e, m.f].every(Number.isFinite)) return null
  return { x: m.a*x + m.c*y + m.e, y: m.b*x + m.d*y + m.f }
}
