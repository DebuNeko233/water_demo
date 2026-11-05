export interface VideoRect { left: number; top: number; width: number; height: number; scale: number }
export interface VideoPoint { x: number; y: number }
export function containRect(boxWidth: number, boxHeight: number, videoWidth: number, videoHeight: number): VideoRect | null
export function clientToVideo(clientX: number, clientY: number,
  box: { left: number; top: number; width: number; height: number },
  videoWidth: number, videoHeight: number): VideoPoint | null
