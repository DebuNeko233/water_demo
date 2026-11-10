export type VideoOpenIssueKind = 'mismatch' | 'oversize' | 'other'
export interface VideoOpenErrorInfo {
  kind: VideoOpenIssueKind
  message: string
}
export declare function describeVideoOpenError(reason: unknown): VideoOpenErrorInfo
