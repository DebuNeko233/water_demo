export interface SeekableVideo {
  duration: number
  currentTime: number
  pause(): void
}
export function seekToReferenceFrame(video: SeekableVideo, time: number): number
