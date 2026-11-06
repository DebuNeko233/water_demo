export interface SvgMatrix {
  a: number
  b: number
  c: number
  d: number
  e: number
  f: number
}
export interface SvgPoint { x: number; y: number }
export interface SvgGeometry {
  getScreenCTM(): SvgMatrix | null
  viewBox: { baseVal: { x: number; y: number; width: number; height: number } }
}
export function svgClientToSource(svg: SvgGeometry | null, clientX: number, clientY: number): SvgPoint | null
export function svgSourceToClient(svg: SvgGeometry | null, x: number, y: number): SvgPoint | null
