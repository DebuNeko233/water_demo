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
  private startPromise: Promise<void> | null = null
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
    if (!this.endpoint) throw new Error('Python backend is not ready')
    return this.endpoint
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

  /**
   * Return the ongoing startup rather than treating an existing child process
   * as already ready. Requests can await the same handshake promise.
   */
  start(): Promise<void> {
    if (this.startPromise) return this.startPromise
    this.startPromise = this.startProcess().finally(() => { this.startPromise = null })
    return this.startPromise
  }

  private async startProcess(): Promise<void> {
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
    this.stderrTail = ''
    let python: string
    try {
      python = this.packagedPython()
    } catch (error) {
      this.latestError = String(error)
      this.change('failed')
      throw error
    }
    // 每次启动生成新的会话/控制令牌，前者用于 API，后者仅用于停机。
    const sessionId = randomUUID()
    const startupDirectory = path.join(app.getPath('userData'), 'startup')
    fs.mkdirSync(startupDirectory, { recursive: true })
    this.readyFile = path.join(startupDirectory, sessionId + '.json')
    this.sessionToken = randomBytes(32).toString('hex')
    this.controlToken = randomBytes(32).toString('hex')

    // Python startup tracebacks must survive a release-build crash.
    // Otherwise users see only "backend is not ready" and we cannot diagnose
    // missing runtimes, file permissions or invalid persisted admin profiles.
    const logDir = path.join(app.getPath('userData'), 'data', 'logs')
    const stderrLog = path.join(logDir, 'python-startup.log')
    try {
      fs.mkdirSync(logDir, { recursive: true })
      if (fs.existsSync(stderrLog) && fs.statSync(stderrLog).size > 5 * 1024 * 1024) {
        fs.rmSync(stderrLog + '.1', { force: true })
        fs.renameSync(stderrLog, stderrLog + '.1')
      }
    } catch (error) {
      console.warn('Cannot prepare Python startup log:', error)
    }
    // -I 禁用用户级包路径；APP_PARENT_PID 使 Python 能察觉 Electron 意外退出。
    const child = spawn(python, ['-I', '-m', 'sample_backend'], {
      cwd: path.dirname(python),
      windowsHide: true,
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
    child.stderr?.on('data', (data: Buffer) => {
      const chunk = data.toString('utf8')
      this.stderrTail = (this.stderrTail + chunk).slice(-4000)
      try { fs.appendFileSync(stderrLog, chunk, 'utf8') } catch { /* optional diagnostics */ }
    })
    let failure: Error | null = null
    child.on('error', (error) => { failure = error })
    child.once('exit', (code) => {
      console.info('Python exited:', code)
      if (this.child === child) {
        this.child = null
        if (!this.stopping) {
          this.latestError = 'Python 后端意外退出（exit code: ' + String(code) + '）'
          this.change('failed')
        }
      }
    })

    try {
      // 就绪握手不仅验证端口，还校验进程 PID 与本次随机会话 ID。
      const deadline = Date.now() + 30_000
      while (Date.now() < deadline && !this.stopping) {
        if (failure) throw failure
        if (exited(child)) {
          throw new Error('Python exited before becoming ready (exit=' +
            String(child.exitCode) + ', signal=' + String(child.signalCode) + ')')
        }
        if (fs.existsSync(this.readyFile)) {
          const ready = JSON.parse(fs.readFileSync(this.readyFile, 'utf8')) as ReadyMessage
          if (ready.pid !== child.pid || ready.session_id !== sessionId ||
              !Number.isInteger(ready.port) || ready.port <= 0 || ready.port > 65535) {
            throw new Error('Invalid Python startup handshake')
          }
          this.endpoint = 'http://127.0.0.1:' + ready.port
          // Python may have bound the socket but still be completing its
          // FastAPI startup. Retry health until the deadline rather than
          // failing the whole backend on one short timeout.
          try {
            await this.health()
            this.change('ready')
            return
          } catch {
            await pause(150)
            continue
          }
        }
        await pause(150)
      }
      throw new Error('Python startup timeout')
    } catch (error) {
      console.error('Python startup failed:', error)
      const detail = this.stderrTail.trim().slice(-1500)
      this.latestError = String(error) + (detail ? '\n' + detail : '') +
        '\n请打开应用日志目录中的 python-startup.log 查看详细信息'
      await this.stop()
      this.change('failed')
      throw new Error(this.latestError)
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
    // The app opens the monitor window *before* the managed Python has
    // completed its handshake. Await startup to avoid an immediate false
    // "not ready" error when a user picks a video promptly after launch.
    if (this.startPromise) {
      try { await this.startPromise } catch { /* surfaced below with diagnostics */ }
    }
    if (this.currentStatus !== 'ready' || !this.endpoint) {
      throw new Error('Python 后端未就绪（' + this.currentStatus + '）：' +
        (this.latestError || '尚未完成启动') + '。请点击「重新连接」或查看日志')
    }
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
