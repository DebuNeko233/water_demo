export interface CalibrationPoint { x: number; y: number }
export interface CalibrationPointResult { point: CalibrationPoint; method: 'svg' | 'viewport' }
export function calibrationPointerToSource(
  svg: SVGSVGElement | null,
  clientX: number,
  clientY: number,
  rect: {left: number; top: number; width: number; height: number},
  videoWidth: number,
  videoHeight: number,
): CalibrationPointResult | null
