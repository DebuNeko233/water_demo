/**
 * 统一开发启动器：Windows 默认分开两个终端；--combined 将前后端放进同一终端。
 * 使用 PowerShell Start-Process 而非 cmd start，避免复杂路径的引号问题。
 */

import { spawn, spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { windowsTerminalScript } from './windows-terminal.mjs'
import { ensureUv } from './uv-bootstrap.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// Bootstrap before launching separate terminals, so neither races the download.
try {
  await ensureUv()
} catch (error) {
  console.error('[dev] ' + error.message)
  process.exit(1)
}

// 非 Windows 默认同终端运行，Windows 默认用两个可独立调试的窗口。
const combinedMode = process.argv.includes('--combined') || process.platform !== 'win32'

if (!combinedMode) {
const packageRunner = (process.env.npm_config_user_agent ?? '').startsWith('pnpm/')
  ? 'pnpm run'
  : 'npm run'

for (const [title, script] of [
  ['Python backend', 'dev:backend'],
  ['Electron frontend', 'dev:frontend'],
]) {
  const powershell = windowsTerminalScript({
    workingDirectory: root,
    command: packageRunner + ' ' + script,
    title,
  })
  // PowerShell -EncodedCommand 需 UTF-16LE，保证包含特殊字符的路径正确传递。
  const encoded = Buffer.from(powershell, 'utf16le').toString('base64')
  const result = spawnSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
    { cwd: root, stdio: 'inherit' },
  )

  if (result.error || result.status !== 0) {
    console.error('Failed to open the ' + title + ' terminal.', result.error ?? '')
    process.exit(result.status || 1)
  }
}

console.log('Opened separate terminal windows for Python and Electron.')

} else {
  // One console on macOS/Linux, or opt in using --combined on Windows.
  const children = []
  let closing = false

  // combined 模式中任意一端退出都清理另一端，Windows 需清理进程树。
  function stop() {
    if (closing) return
    closing = true
    for (const child of children) {
      if (!child.pid || child.exitCode !== null) continue
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
      } else {
        child.kill('SIGTERM')
      }
    }
  }

  function start(script) {
    // Only the two known, hard-coded script names are sent to cmd.exe.
    const child = process.platform === 'win32'
      ? spawn('cmd.exe', ['/d', '/c', 'npm run ' + script], { cwd: root, stdio: 'inherit' })
      : spawn('npm', ['run', script], { cwd: root, stdio: 'inherit' })
    child.on('error', error => {
      console.error('[dev] Cannot launch ' + script + ':', error)
      process.exitCode = 1
      stop()
    })
    child.on('exit', code => {
      if (!closing) {
        process.exitCode = code || 1
        stop()
      }
    })
    children.push(child)
  }

  process.once('SIGINT', stop)
  process.once('SIGTERM', stop)
  start('dev:backend')
  start('dev:frontend')
}
