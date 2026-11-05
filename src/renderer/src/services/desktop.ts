/** Preload IPC wrappers. Only expose trusted desktop operations. */

import type { LogTarget } from '../../../shared/bridge'

export function selectFile(): Promise<string | null> {
  return window.desktop.system.selectFile()
}

export function openLogDirectory(target: LogTarget = 'python'): Promise<void> {
  return window.desktop.system.openLogs(target)
}
