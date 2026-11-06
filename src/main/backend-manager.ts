import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { setTimeout as pause } from 'node:timers/promises'
import { app } from 'electron'
import type { BackendStatus } from '../shared/bridge'

// 就绪文件由 Python 原子写入；pid/session_id 防止误连到其他本机服务。
interface ReadyMessage { port: number; pid: number; session_id: string }
interface Manifest { python: string }

function exited(child: ChildProcess): boolean {
  return child.exitCode !== null || child.signalCode !== null
}

// 使用一次性 exit 监听并在超时后移除，防止关闭过程中遗留监听器。
function waitForExit(child: ChildProcess, ms: number): Promise<boolean> {
  if (exited(child)) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timer = setTimeout(() => finish(false), ms)
    const listener = () => finish(true)
    const finish = (ok: boolean) => {
      clearTimeout(timer)
      child.off('exit', listener)
      resolve(ok)
    }
    child.once('exit', listener)
  })
}

/** Owns Python only in packaged mode. Development backends remain independent. */
export class BackendManager {
  private child: ChildProcess | null = null
  private endpoint = ''
  private sessionToken = ''
  private controlToken = ''
  private readyFile = ''
  private stopping = false
  private currentStatus: BackendStatus = 'starting'
  private latestError = ''
  private stderrTail = ''

  constructor(private readonly notify: (status: BackendStatus) => void) {}

  get status(): BackendStatus { return this.currentStatus }
  get diagnostic(): string { return this.latestError }
  get token(): string { return this.sessionToken }
  get ownedPid(): number | null { return this.child?.pid ?? null }

  connected(): void { this.change('ready') }
  disconnected(): void {
    if (!app.isPackaged && !this.stopping) this.change('offline')
  }
  get baseUrl(): string {
    if (!this.endpoint) {
      throw new Error('Python backend is not ready: ' + (this.latestError || this.currentStatus))
    }
    return this.endpoint
  }

  private async waitUntilReady(): Promise<void> {
    // The monitor is visible before a packaged Python interpreter finishes
    // initializing. Waiting here prevents false "backend not ready" errors
    // when the user selects a video immediately after launching Electron.
    const deadline = Date.now() + 33_000
    while (this.currentStatus === 'starting' && Date.now() < deadline) {
      await pause(150)
    }
    if (this.currentStatus === 'ready' && this.endpoint) return
    throw new Error(
      'Python backend is not ready (' + this.currentStatus + '): ' +
      (this.latestError || '后端未能启动，请检查软件目录是否完整以及 electron.log'),
    )
  }

  private change(status: BackendStatus): void {
    if (status === 'ready') this.latestError = ''
    this.currentStatus = status
    this.notify(status)
  }

  // 不信任清单中的路径：必须解析到随应用分发的 backend 目录内部。
  private packagedPython(): string {
    const root = path.join(process.resourcesPath, 'backend')
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8')) as Manifest
    const executable = path.resolve(root, manifest.python)
    const relative = path.relative(root, executable)
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      throw new Error('Invalid Python location in manifest')
    }
    if (!fs.existsSync(executable)) throw new Error('Bundled Python missing: ' + executable)
    return executable
  }

  async start(): Promise<void> {
    // 开发时 Python 由单独终端拥有；Electron 只能连接，绝不能代替用户管理它。
    if (!app.isPackaged) {
      this.endpoint = 'http://127.0.0.1:8765'
      try {
        await this.health()
        this.change('ready')
      } catch {
        this.latestError = 'Python 开发服务尚未连接。请运行 pnpm dev:backend。'
        this.change('offline')
      }
      return
    }
    if (this.child || this.stopping) return
    this.change('starting')
    let python: string
    try {
      python = this.packagedPython()
    } catch (error) {
      this.latestError = String(error)
      this.change('failed')
      throw error
    }
    // 每次启动生成新的会话/控制令牌，前者用于 API，后者仅用于停机。
    this.stderrTail = ''
    const sessionId = randomUUID()
    const startupDirectory = path.join(app.getPath('userData'), 'startup')
    fs.mkdirSync(startupDirectory, { recursive: true })
    this.readyFile = path.join(startupDirectory, sessionId + '.json')
    this.sessionToken = randomBytes(32).toString('hex')
    this.controlToken = randomBytes(32).toString('hex')

    // -I 禁用用户级包路径；APP_PARENT_PID 使 Python 能察觉 Electron 意外退出。
    const child = spawn(python, ['-I', '-m', 'sample_backend'], {
      cwd: path.dirname(python),
      windowsHide: true,
      // Capture Python's startup traceback for failures such as missing
      // DLLs, site-packages or unsupported video codecs. No extra console
      // window is opened for users; only local Electron logs record it.
      stdio: ['ignore', 'ignore', 'pipe'],
      env: {
        ...process.env,
        APP_PARENT_PID: String(process.pid),
        APP_SESSION_ID: sessionId,
        APP_SESSION_TOKEN: this.sessionToken,
        APP_CONTROL_TOKEN: this.controlToken,
        APP_READY_FILE: this.readyFile,
        APP_DATA_DIR: path.join(app.getPath('userData'), 'data'),
        PYTHONNOUSERSITE: '1',
      },
    })
    this.child = child
    child.stderr?.on('data', (chunk: Buffer | string) => {
      this.stderrTail = (this.stderrTail + String(chunk)).slice(-12_000)
    })
    let failure: Error | null = null
    child.on('error', (error) => { failure = error })
    child.once('exit', (code, signal) => {
      const exit = typeof code === 'number'
        ? String(code) + ' / 0x' + (code >>> 0).toString(16)
        : String(signal)
      const reason = 'Python exited (' + exit + ')' +
        (this.stderrTail.trim() ? ': ' + this.stderrTail.trim() : '')
      console.error(reason)
      if (this.child === child) {
        this.child = null
        if (!this.stopping) {
          this.latestError = reason
          this.change('failed')
        }
      }
    })

    try {
      // 就绪握手不仅验证端口，还校验进程 PID 与本次随机会话 ID。
      const deadline = Date.now() + 30_000
      while (Date.now() < deadline && !this.stopping) {
        if (failure) throw failure
        if (exited(child)) throw new Error('Python exited before becoming ready')
        if (fs.existsSync(this.readyFile)) {
          const ready = JSON.parse(fs.readFileSync(this.readyFile, 'utf8')) as ReadyMessage
          if (ready.pid !== child.pid || ready.session_id !== sessionId ||
              !Number.isInteger(ready.port) || ready.port <= 0 || ready.port > 65535) {
            throw new Error('Invalid Python startup handshake')
          }
          this.endpoint = 'http://127.0.0.1:' + ready.port
          // 有就绪文件不等于 HTTP 已可用；健康检查成功后才报告 ready。
          await this.health()
          this.change('ready')
          return
        }
        await pause(150)
      }
      throw new Error('Python startup timeout')
    } catch (error) {
      const details = [
        error instanceof Error ? error.message : String(error),
        this.stderrTail.trim(),
      ].filter(Boolean).join('\n')
      // stop() transitions to offline. Restore the meaningful failure status
      // afterwards, otherwise IPC clients only see a generic unavailable
      // backend instead of the actual Python import/loader failure.
      await this.stop()
      this.latestError = details
      console.error('Python startup failed:', details)
      this.change('failed')
      throw new Error(details)
    } finally {
      this.removeReadyFile()
    }
  }

  private removeReadyFile(): void {
    if (this.readyFile) {
      try { fs.rmSync(this.readyFile, { force: true }) } catch { /* optional cleanup */ }
      this.readyFile = ''
    }
  }

  async health(): Promise<void> {
    const response = await fetch(this.baseUrl + '/api/health', {
      headers: this.sessionToken ? { 'x-session-token': this.sessionToken } : {},
      signal: AbortSignal.timeout(2_000),
    })
    if (!response.ok) throw new Error('Python health check failed: ' + response.status)
  }

  async request(method: 'GET' | 'POST', apiPath: string, body?: unknown): Promise<unknown> {
    // Renderer 提供的路径必须在白名单范围内，避免借主进程发任意本机请求。
    if (!/^\/api\/[a-zA-Z0-9/_-]+$/.test(apiPath) || apiPath.includes('..')) {
      throw new Error('Invalid API path')
    }
    const json = body === undefined ? undefined : JSON.stringify(body)
    // Detector frame transport contains a lossless PNG encoded as base64. Keep the
    // larger payload cap limited to this one trusted local API route.
    const maxSize = apiPath === '/api/detection/frame' ? 25_000_000 : 65_536
    if (json && json.length > maxSize) throw new Error('Request too large')
    await this.waitUntilReady()
    const response = await fetch(this.baseUrl + apiPath, {
      method,
      headers: {
        ...(this.sessionToken ? { 'x-session-token': this.sessionToken } : {}),
        ...(json === undefined ? {} : { 'content-type': 'application/json' }),
      },
      body: json,
      signal: AbortSignal.timeout(15_000),
    })
    const result: unknown = await response.json().catch(() => null)
    if (!response.ok) throw new Error('Python API ' + response.status + ': ' + JSON.stringify(result))
    return result
  }

  async stop(): Promise<void> {
    if (this.stopping) return
    this.stopping = true
    this.change('stopping')
    const child = this.child
    try {
      if (child && !exited(child)) {
        // 优先请求授权的内部接口优雅关闭；超时后仅终止本进程创建的子进程。
        if (this.endpoint && this.controlToken) {
          try {
            await fetch(this.endpoint + '/internal/shutdown', {
              method: 'POST',
              headers: { 'x-control-token': this.controlToken },
              signal: AbortSignal.timeout(1_500),
            })
          } catch (error) {
            console.warn('Graceful Python shutdown failed:', error)
          }
        }
        if (!(await waitForExit(child, 5_000))) {
          if (process.platform === 'win32' && child.pid) {
            const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
              windowsHide: true, stdio: 'ignore',
            })
            await waitForExit(killer, 2_000)
          } else {
            child.kill('SIGKILL')
          }
          await waitForExit(child, 2_000)
        }
      }
    } finally {
      this.child = null
      this.endpoint = ''
      this.sessionToken = ''
      this.controlToken = ''
      this.removeReadyFile()
      this.change('offline')
      this.stopping = false
    }
  }
}
