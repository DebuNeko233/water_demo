/** Device-local operator/admin switch. Admin tokens exist only in memory. */
import type { AlgorithmSettings } from '../utils/algorithm-settings.mjs'

export type UserRole = 'operator' | 'admin'
export interface UserStatus {
  role: 'operator'
  admin_configured: boolean
  settings: AlgorithmSettings
}
export interface AdminSession {
  role: 'admin'
  admin_token: string
  settings: AlgorithmSettings
}
export function loadUserStatus(): Promise<UserStatus> {
  return window.desktop.backend.request<UserStatus>('GET', '/api/users/status')
}
export function setupAdministrator(password: string): Promise<AdminSession> {
  return window.desktop.backend.request<AdminSession>('POST', '/api/users/setup', { password })
}
export function loginAdministrator(password: string): Promise<AdminSession> {
  return window.desktop.backend.request<AdminSession>('POST', '/api/users/login', { password })
}
export function logoutAdministrator(adminToken: string): Promise<{ role: 'operator' }> {
  return window.desktop.backend.request('POST', '/api/users/logout', {
    admin_token: adminToken,
  })
}
export function saveApprovedSettings(adminToken: string, settings: AlgorithmSettings): Promise<{ settings: AlgorithmSettings }> {
  return window.desktop.backend.request('POST', '/api/users/settings', {
    admin_token: adminToken,
    settings,
  })
}
