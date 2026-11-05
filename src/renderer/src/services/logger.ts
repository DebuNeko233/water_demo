/**
 * Renderer logger: only explicit non-sensitive event descriptions reach
 * the Electron file log. Do not pass raw form values or Error stacks here.
 */
import type { LogLevel } from '../../../shared/bridge'

export function createLogger(source: string) {
  function write(level: LogLevel, message: string): void {
    // Logs are non-critical; an IPC failure must never break the UI.
    void window.desktop.logging.write(level, source, message).catch(() => {
      console.warn('Could not write renderer log:', source)
    })
  }

  return {
    info: (message: string) => write('info', message),
    warn: (message: string) => write('warn', message),
    error: (message: string) => write('error', message),
  }
}
