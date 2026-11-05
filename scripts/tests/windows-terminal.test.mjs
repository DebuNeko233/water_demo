import assert from 'node:assert/strict'
import test from 'node:test'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as pause } from 'node:timers/promises'
import { windowsTerminalScript } from '../windows-terminal.mjs'

test('starts cmd.exe directly instead of interpreting the window title as a file', () => {
  const script = windowsTerminalScript({
    workingDirectory: 'C:\\Users\\Someone\\Desktop\\My Project',
    command: 'pnpm run dev:backend',
    title: 'Python backend',
  })

  assert.ok(script.includes('Start-Process -FilePath $env:ComSpec'))
  assert.ok(script.includes("-ArgumentList '/d /k pnpm run dev:backend'"))
  assert.ok(script.includes("-WorkingDirectory 'C:\\Users\\Someone\\Desktop\\My Project'"))
  assert.ok(script.includes("Write-Output 'Opened Python backend'"))
  assert.ok(!script.includes('start "Python backend"'))
})

test('quotes apostrophes in project paths and supports npm', () => {
  const script = windowsTerminalScript({
    workingDirectory: "C:\\Users\\D'Angelo\\My App",
    command: 'npm run dev:frontend',
    title: 'Electron frontend',
  })

  assert.ok(script.includes("D''Angelo"))
  assert.ok(script.includes('/d /k npm run dev:frontend'))
  assert.ok(script.includes("Write-Output 'Opened Electron frontend'"))
})

test('Windows: a new command terminal runs a command from a quoted folder', {
  skip: process.platform !== 'win32',
}, async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'terminal launch '))
  const folder = path.join(root, "A Folder O'Brien")
  fs.mkdirSync(folder)
  const marker = path.join(folder, 'started.txt')

  try {
    // /k keeps cmd open in normal use. The test command exits itself.
    const script = windowsTerminalScript({
      workingDirectory: folder,
      command: 'echo TERMINAL_READY > started.txt & exit',
      title: 'Python backend',
    })
    const result = spawnSync('powershell.exe', [
      '-NoProfile', '-NonInteractive', '-EncodedCommand',
      Buffer.from(script, 'utf16le').toString('base64'),
    ], { encoding: 'utf8', timeout: 10_000 })

    assert.equal(result.status, 0, result.stderr || result.stdout)
    for (let i = 0; i < 50 && !fs.existsSync(marker); i++) {
      await pause(100)
    }
    assert.equal(fs.readFileSync(marker, 'utf8').trim(), 'TERMINAL_READY')
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
