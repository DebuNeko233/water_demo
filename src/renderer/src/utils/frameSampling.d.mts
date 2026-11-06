export interface FrameSampler {
  shouldSample(timeSeconds: number): boolean
  reset(): void
}
export function createFrameSampler(fps?: number): FrameSampler
