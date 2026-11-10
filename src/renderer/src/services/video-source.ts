/** Backend-owned video selection. Only admins may edit camera endpoints. */
export type VideoSourceKind = 'file' | 'rtsp' | 'usb'

export interface VideoSourceSettings {
  kind: VideoSourceKind
  rtsp_url: string
  usb_index: number
}

export interface VideoSourceStatus {
  kind: VideoSourceKind
  usb_index: number
}

export const DEFAULT_VIDEO_SOURCE: VideoSourceSettings = {
  kind: 'file', rtsp_url: '', usb_index: 0,
}

export function publicVideoSource(): Promise<VideoSourceStatus> {
  return window.desktop.backend.request('GET', '/api/video/source')
}

export function adminVideoSource(adminToken: string): Promise<VideoSourceSettings> {
  return window.desktop.backend.request('POST', '/api/video/source/config', {
    admin_token: adminToken,
  })
}

export function saveVideoSource(source: VideoSourceSettings, adminToken: string): Promise<{ source: VideoSourceSettings }> {
  return window.desktop.backend.request('POST', '/api/video/source/save', {
    source, admin_token: adminToken,
  })
}

export interface CameraSnapshot {
  width: number
  height: number
  jpeg_base64: string
}

export function cameraSnapshot(adminToken: string): Promise<CameraSnapshot> {
  return window.desktop.backend.request('POST', '/api/video/snapshot', {
    admin_token: adminToken,
  })
}
