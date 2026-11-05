# 日志指南：Electron / Vue / Python

这个模板的三种日志职责明确，**不需要引入新的日志框架**：

| 运行部分 | 推荐 API | 日志最终去向 |
| --- | --- | --- |
| Vue Renderer | `createLogger('模块名')` | 通过受限 IPC 转发至 Electron 的 `electron.log` |
| Electron Main | `console.info / warn / error` | Main 终端输出 + `electron.log` |
| Python FastAPI / Service | `loguru.logger` | 开发 Python 终端 + `backend.log` |

所有日志由代码写入文件；**WebSocket 事件不是日志存储**，不要以 `publish()` 替代日志。

## 一、快速使用

### 1. Vue 组件（Renderer）

从 `src/renderer/src/services/logger.ts` 导入：

~~~ts
import { createLogger } from '../services/logger'

const log = createLogger('CameraView')

async function connectCamera(): Promise<void> {
  log.info('Camera connection requested')
  try {
    // await cameraApi.connect()
    log.info('Camera connected')
  } catch (error) {
    log.error('Camera connection failed')
    // 页面也应该显示可理解的错误信息；日志不能代替 UI 提示。
    throw error
  }
}
~~~

现成示例：`src/renderer/src/components/EchoDemo.vue`、`DesktopDemo.vue`。
可直接使用 `log.info('...')`、`log.warn('...')`、`log.error('...')`。

调用链：

~~~text
Vue createLogger('CameraView')
    ↓
window.desktop.logging.write(level, source, message)
    ↓
src/preload/index.ts
    ↓ Electron IPC: logging:write（验证消息来自主窗口）
src/main/index.ts
    ↓ 校验日志级别、模块名、单行长度
console[level]('[renderer:CameraView]', message)
    ↓
src/main/logging.ts → electron.log
~~~

Renderer **不能直接使用 Node.js 文件系统**，也不能直接写发行包目录。
日志写入是非关键操作：如果 IPC 失败，logger 本身只在 Renderer 控制台提示一次类错误，
不会阻塞或中断用户点击的业务操作。

目前 Renderer 的接口仅接受 **INFO、WARN、ERROR** 三种级别，
模块名应由开发者硬编码，例如 `CameraView`、`TaskDemo`，不应来自用户输入。
单条消息限定为不超过 1000 字符的单行文本；换行和控制字符会被 Main 拒绝。

### 2. Electron 主进程（Main）

`src/main/logging.ts` 在应用启动时调用 `installLogging()`，
接管主进程的这三个标准方法：

~~~ts
console.info('[BackendManager] Python backend ready')
console.warn('[BackendManager] WebSocket disconnected')
console.error('[BackendManager] Startup failed:', error)
~~~

用一个简短、固定的 `[模块名]` 方便搜索。
错误日志可以写入实际 Error 对象以保留堆栈，**前提是堆栈、错误消息没有包含密钥或敏感内容**。
禁止直接记录 HTTP Header、随机会话/关闭令牌和任何秘密环境变量。

Main 的文件采用 UTC ISO 时间戳（`new Date().toISOString()`）：

~~~text
2026-10-27T05:00:00.000Z [INFO] [renderer:CameraView] Camera connected
2026-10-27T05:00:01.000Z [WARN] [BackendManager] WebSocket disconnected
~~~

文件为 `electron.log`；超过约 5 MiB 时，会轮转为 `electron.log.1`
（只保留一个备份文件）。同时输出到 Electron Main 终端。

### 3. Python 后端（FastAPI / Service）

直接使用项目已有的 **Loguru**：

~~~python
from loguru import logger


def process_frame(frame_id: int) -> None:
    logger.info("camera.frame_started frame_id={}", frame_id)
    try:
        # process(...)
        logger.info("camera.frame_finished frame_id={}", frame_id)
    except Exception:
        logger.exception("camera.frame_failed frame_id={}", frame_id)
        raise
~~~

- 使用 `logger.debug(...)`：临时诊断和高频细节，只在开发时按需启用，不应大量写正式文件。
- 使用 `logger.info(...)`：重要但正常的状态变化（任务开始、完成、设备连接）。
- 使用 `logger.warning(...)`：可以自动恢复的异常（重连、超时重试）。
- 使用 `logger.error(...)`：业务操作失败。
- 在 `except` 内使用 `logger.exception(...)`：写入当前异常与堆栈。
- 禁止在 `except` 外滥用 `logger.exception(...)` 或空捕获不处理。
- 使用 Loguru 的 `{}` 占位符，不要为日志调用拼接大型字符串。

真实代码示例：
`backend/src/sample_backend/api/routes.py` 记录回显内容**长度，不记录用户输入**；
`services/demo_jobs.py` 记录任务 ID 和开始、完成、取消事件。

Python 日志在 FastAPI 的 `lifespan` 中由
`backend/src/sample_backend/core/logging.py` 配置：
- 文件：`backend.log`，级别从 `INFO` 起。
- 按约 10 MB 轮转，保留 7 天。
- 文件使用 UTF-8 编码、异步队列写入（`enqueue=True`）。
- 开发时还输出到 stderr，默认支持 DEBUG 级别。
- 发行版 Python 不打开独立控制台，查看文件日志。

## 二、分级与什么时候应该记录

| 级别 | 应写哪些内容 | 不应写哪些内容 |
| --- | --- | --- |
| DEBUG | 开发过程的中间状态、分支判断 | 每帧原始图像、巨量矩阵、生产环境高频刷屏 |
| INFO | 服务就绪、任务启动/完成、配置生效（非秘密） | 每次心跳、每次鼠标移动、整段请求体 |
| WARN | 断线重连、可恢复的设备超时、资源即将不足 | 当成业务成功通知 |
| ERROR | 无法完成的操作、异常退出、关键设备故障 | 明文 token、密码、患者数据或完整原始堆栈中可能含敏感内容的请求 |

尽量统一用 **`模块.事件 + 关联 ID`**：
- `camera.connected device_id=cam1`
- `demo_job.started task_id=...`
- `demo_job.completed task_id=...`

对一个操作，在**开始、结束、失败**三个节点记录即可；
任务进度用 WebSocket 更新 UI，不要每隔 0.1 秒写一条 INFO。

## 三、隐私和安全约定（人和 AI 都必须遵守）

**即使日志是本地文件，也应按用户数据处理**：

1. **严禁**记录 `APP_SESSION_TOKEN`、`APP_CONTROL_TOKEN`、密码、Cookie、
   Authorization Header、完整环境变量、证书或私钥。
2. 不记录用户输入文本、完整文件路径、患者/客户信息、原始音视频帧、
   Base64 图像或巨大的 JSON；优先记录长度、数量、耗时、状态和业务 ID。
3. 用户选择文件的示例只记录 `File selected`，**不记录所选路径**。
4. 捕获错误时，UI 可以显示合适的错误信息；写日志时先审查 `Error.message`
   / Python 异常是否含有敏感路径或用户数据。Renderer 示例只记录固定的错误事件。
5. 不把日志文件提交到 Git 仓库或默认上传给第三方；共享报错前先脱敏。
6. Renderer 的 IPC 有输入校验，**并不自动给任意消息做隐私脱敏**；
   日志调用者仍必须遵守上面的规则。

## 四、日志目录在哪里？

| 模式 | Electron / Vue 日志 | Python 日志 |
| --- | --- | --- |
| Windows 开发模式 | `app.getPath('userData')/data/logs/electron.log` | `%USERPROFILE%\.python-electron-vue-sample\logs\backend.log` |
| Windows 发行模式 | `app.getPath('userData')/data/logs/electron.log` | `app.getPath('userData')/data/logs/backend.log` |

**开发模式下的前后端日志不在同一个文件夹**，因为 Python 是独立进程。
正式发行模式下，它们共享 Electron 用户数据根目录下的 `data/logs`。

界面里的“IPC 示例”现在分别提供：
- **打开前端日志**：打开 Electron/Main/Renderer 共同的文件日志目录。
- **打开后端日志**：打开 Python 日志目录（发行版与前端同目录）。

其中 `userData` 的绝对路径由 Electron 根据系统用户和应用配置决定；
不要自行猜测固定的 `C:\Users\...` 路径。

### PowerShell 查看和实时跟踪

打开相应目录后，在 PowerShell 中：

~~~powershell
Get-Content .\backend.log -Tail 60
Get-Content .\backend.log -Tail 30 -Wait
Select-String -Path .\electron.log -Pattern "ERROR|WARN"
~~~

这些命令需要先将 PowerShell 工作目录切换到日志文件夹。
遇到问题先按发生时间对照 `electron.log` 和 `backend.log`，
找到同一个事件或关联的 `task_id`。

## 五、修改日志时需要运行的检查

~~~powershell
pnpm test:backend
pnpm typecheck
pnpm build
node scripts/smoke/electron.mjs
~~~

CI 的打包版 Electron 冒烟测试还会验证
**Renderer → Preload → Main → electron.log** 确实写入了日志，
而不是只在网页控制台显示。

添加新的业务日志应遵守三个原则：**可定位、低噪声、保护隐私**。
