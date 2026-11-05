/** Electron is responsible for desktop permissions and process ownership. */

import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { BackendManager } from './backend-manager'
import { EventStream } from './event-stream'
import { installLogging } from './logging'
import type { BackendStatus } from '../shared/bridge'

const mainDirectory = path.dirname(fileURLToPath(import.meta.url))
let mainWindow: BrowserWindow | null = null
let closing = false
let allowQuit = false

// 仅允许一个桌面应用实例，避免重复占用配置和托管多个 Python 进程。
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })
}

function publishStatus(status: BackendStatus): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:status', status)
  }
}

const backend = new BackendManager(publishStatus)
const stream = new EventStream(backend, (event) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend:event', event)
  }
})

// 合并连续点击“重新连接”触发的重试，避免并发重建 WebSocket/Python。
let retryPromise: Promise<void> | null = null

/** Manual retry also works when the developer started Python after Electron. */
function retryBackend(): Promise<void> {
  if (retryPromise) return retryPromise
  retryPromise = (async () => {
    stream.stop()
    await backend.stop()
    await backend.start()
    stream.connect()
  })().finally(() => { retryPromise = null })
  return retryPromise
}

// 每个 IPC 入口都必须确认消息来自当前窗口的主 frame，拒绝其他内容调用。
function checkSender(event: Electron.IpcMainInvokeEvent): void {
  if (!mainWindow || mainWindow.isDestroyed() ||
      event.sender !== mainWindow.webContents ||
      event.senderFrame !== mainWindow.webContents.mainFrame) {
    throw new Error('Unauthorized IPC sender')
  }
}

// Renderer 只能调用这些预先批准的 IPC；不能直接使用 Node.js 或传任意命令。
function registerIpc(): void {
  ipcMain.handle('backend:status', (event) => {
    checkSender(event)
    return backend.status
  })
  ipcMain.handle('backend:diagnostics', (event) => {
    checkSender(event)
    return backend.diagnostic
  })
  ipcMain.handle('backend:retry', (event) => {
    checkSender(event)
    return retryBackend()
  })
  ipcMain.handle('backend:request', (event, method: unknown, apiPath: unknown, body?: unknown) => {
    checkSender(event)
    if ((method !== 'GET' && method !== 'POST') || typeof apiPath !== 'string') {
      throw new Error('Invalid API request')
    }
    return backend.request(method, apiPath, body)
  })
  ipcMain.handle('system:select-file', async (event) => {
    checkSender(event)
    const selection = await dialog.showOpenDialog(mainWindow!, { properties: ['openFile'] })
    return selection.canceled ? null : selection.filePaths[0]
  })
  // 日志内容也来自 Renderer，必须校验级别、模块名、长度和控制字符。
  ipcMain.handle('logging:write', (event, level: unknown, source: unknown, message: unknown) => {
    checkSender(event)
    // Renderer content is untrusted: accept only short, single-line, text-only events.
    if ((level !== 'info' && level !== 'warn' && level !== 'error') ||
        typeof source !== 'string' || !/^[a-zA-Z][a-zA-Z0-9_.-]{0,39}$/.test(source) ||
        typeof message !== 'string' || message.length < 1 || message.length > 1000 ||
        /[\r\n\x00-\x1f\x7f]/.test(message)) {
      throw new Error('Invalid renderer log entry')
    }
    console[level]('[renderer:' + source + ']', message)
  })
  ipcMain.handle('system:open-logs', async (event, target: unknown = 'python') => {
    checkSender(event)
    if (target !== 'python' && target !== 'electron') {
      throw new Error('Invalid log target')
    }
    // 开发 Python 是独立进程，日志与 Electron 不在同一个目录。
    const directory = app.isPackaged || target === 'electron'
      ? path.join(app.getPath('userData'), 'data', 'logs')
      : path.join(os.homedir(), '.python-electron-vue-sample', 'logs')
    fs.mkdirSync(directory, { recursive: true })
    const error = await shell.openPath(directory)
    if (error) throw new Error(error)
  })
  ipcMain.handle('system:close-window', (event) => {
    checkSender(event)
    mainWindow?.close()
  })
}

function createWindow(show = true): BrowserWindow {
  mainWindow = new BrowserWindow({
    show,
    width: 1200,
    height: 790,
    minWidth: 800,
    minHeight: 600,
    autoHideMenuBar: true,
    backgroundColor: '#f5f7fb',
    // 只经 Preload 暴露白名单 API：Renderer 保持沙箱、上下文隔离和无 Node 权限。
    webPreferences: {
      preload: path.join(mainDirectory, '../preload/index.cjs'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  })
  // 禁止网页内容擅自打开新窗口或导航至任意外部地址。
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const developmentUrl = process.env.ELECTRON_RENDERER_URL
    const indexFile = path.join(mainDirectory, '../renderer/index.html')
    const allowedFile = pathToFileURL(indexFile).href
    if (url !== allowedFile && !(developmentUrl && url.startsWith(developmentUrl))) {
      event.preventDefault()
    }
  })
  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void mainWindow.loadFile(path.join(mainDirectory, '../renderer/index.html'))
  }
  const createdWindow = mainWindow
  mainWindow.on('closed', () => { mainWindow = null })
  return createdWindow
}

async function startBackend(): Promise<void> {
  try {
    await backend.start()
    stream.connect()
  } catch (error) {
    console.error('Python startup failed. Read the backend log for details:', error)
    publishStatus('failed')
  }
}

app.on('window-all-closed', () => app.quit())
// 正式退出前必须先停 WebSocket 和本应用拥有的 Python，再允许 Electron 真正退出。
app.on('before-quit', (event) => {
  if (allowQuit || closing) return
  event.preventDefault()
  closing = true
  stream.stop()
  void backend.stop().finally(() => {
    allowQuit = true
    app.quit()
  })
})

/**
 * Exercise the actual packaged Electron executable without opening a window.
 * CI runs this after bundling, so it catches missing resources and startup bugs
 * that testing python.exe alone cannot catch.
 */
async function runPackagedSmokeTest(): Promise<void> {
  let exitCode = 1
  let pythonPid: number | null = null
  try {
    if (!app.isPackaged) throw new Error('Packaged smoke test requires a release build')
    await backend.start()
    pythonPid = backend.ownedPid
    if (backend.status !== 'ready') throw new Error('Python did not report READY')
    const health = await backend.request('GET', '/api/health') as { status: string }
    if (health.status !== 'ready') throw new Error('Python health check failed')
    const echo = await backend.request('POST', '/api/echo', { message: 'Electron smoke test' }) as {
      message: string
    }
    if (echo.message !== 'Electron smoke test') throw new Error('Python HTTP echo mismatch')
    // Also exercise the actual Vue sidebar, not just the Python transport.
    registerIpc()
    const browser = createWindow(false)
    const result: unknown = await browser.webContents.executeJavaScript(
      `(async () => {
        const buttons = [...document.querySelectorAll('aside nav button')]
        const expected = ['应用概览', 'HTTP 示例', '实时任务', 'IPC 示例']
        if (buttons.length !== expected.length) {
          throw new Error('Expected four sidebar buttons')
        }

        for (let index = 0; index < buttons.length; index++) {
          buttons[index].click()
          await new Promise((resolve) => setTimeout(resolve, 30))
          const title = document.querySelector('h1')?.textContent?.trim()
          const selected = document.querySelectorAll('aside nav button[aria-current="page"]')
          if (title !== expected[index] || selected.length !== 1 ||
              selected[0] !== buttons[index]) {
            throw new Error('Sidebar did not navigate to ' + expected[index])
          }
        }

        // The task component must remain mounted when switching between tabs.
        buttons[2].click()
        await new Promise((resolve) => setTimeout(resolve, 30))
        const task = document.querySelector('#tasks')
        const start = task?.querySelector('button')
        if (!start) throw new Error('Task page has no start button')
        start.click()

        const deadline = Date.now() + 8_000
        while (!task?.querySelector('.small')?.textContent?.includes('Task ID:')) {
          if (Date.now() > deadline) throw new Error('Task did not start')
          await new Promise((resolve) => setTimeout(resolve, 100))
        }
        const taskId = task.querySelector('.small').textContent
        buttons[1].click()
        await new Promise((resolve) => setTimeout(resolve, 30))
        buttons[2].click()
        await new Promise((resolve) => setTimeout(resolve, 30))
        if (task.querySelector('.small')?.textContent !== taskId) {
          throw new Error('Task state was discarded when navigating')
        }
        return 'Navigation and task state OK'
      })()`,
      true,
    )
    // Exercise Renderer → Preload → Main → electron.log, not just console output.
    await browser.webContents.executeJavaScript(
      "window.desktop.logging.write('info', 'SmokeTest', 'Renderer log IPC roundtrip')",
      true,
    )
    const electronLog = path.join(app.getPath('userData'), 'data', 'logs', 'electron.log')
    if (!fs.readFileSync(electronLog, 'utf8').includes('[renderer:SmokeTest] Renderer log IPC roundtrip')) {
      throw new Error('Renderer log was not persisted into electron.log')
    }
    console.info('Packaged Electron and Python communication succeeded:', result)
    exitCode = 0
  } catch (error) {
    console.error('Packaged Electron smoke test failed:', error)
  } finally {
    await backend.stop()
    const report = process.env.APP_SMOKE_REPORT
    if (report) {
      try {
        fs.writeFileSync(report, JSON.stringify({ exitCode, pythonPid }), 'utf8')
      } catch (error) {
        console.error('Could not write smoke test report:', error)
        exitCode = 1
      }
    }
    app.exit(exitCode)
  }
}

/**
 * The companion integration test kills this Electron process with taskkill /F,
 * WITHOUT terminating its children. The Python parent watchdog must detect
 * that exit and shut down independently.
 */
async function runParentExitSmokeTest(): Promise<void> {
  try {
    if (!app.isPackaged) throw new Error('Requires a packaged Electron executable')
    const report = process.env.APP_SMOKE_REPORT
    if (!report) throw new Error('Missing APP_SMOKE_REPORT')
    await backend.start()
    if (backend.status !== 'ready' || !backend.ownedPid) {
      throw new Error('Python backend failed to start')
    }
    fs.writeFileSync(report, JSON.stringify({ pythonPid: backend.ownedPid }), 'utf8')
    // Keep the main process alive until the test kills it using taskkill /F.
    setInterval(() => {}, 5_000)
  } catch (error) {
    console.error('Parent-exit test setup failed:', error)
    await backend.stop()
    app.exit(1)
  }
}

// 冒烟测试只在 CI 打包程序中运行；正常启动才创建可见窗口和后端连接。
app.whenReady().then(() => {
  if (!app.hasSingleInstanceLock()) return
  installLogging()
  if (process.argv.includes('--smoke-parent-exit')) {
    void runParentExitSmokeTest()
    return
  }
  if (process.argv.includes('--smoke-test')) {
    void runPackagedSmokeTest()
    return
  }
  registerIpc()
  createWindow()
  void startBackend()
})
