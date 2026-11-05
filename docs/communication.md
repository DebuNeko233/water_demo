# 通信契约：IPC / HTTP / WebSocket / 进程生命周期

**这是当前实现的接口契约，不是计划中的未来架构。**
修改接口时同步更新前端类型、代码、测试与本文件。

## 一张总览图

~~~text
Vue 组件
  ├─ services/backend-api.ts
  │     ↓ window.desktop.backend.request(...)
  │   preload/index.ts
  │     ↓ ipcRenderer.invoke('backend:request', ...)
  │   Electron Main: ipcMain + BackendManager.request()
  │     ↓ HTTP（仅 localhost；发行模式由 Main 添加会话令牌）
  │   FastAPI: api/routes.py → services/demo_jobs.py
  │
  ├─ composables/useBackendEvents.ts
  │     ↑ window.desktop.backend.onEvent(...)
  │   preload/index.ts ← webContents.send('backend:event', ...)
  │   Electron Main: EventStream（单连接，ws 库）
  │     ↑ WebSocket /ws/events
  │   FastAPI: api/websocket.py → services/event_hub.py
  │
  └─ services/desktop.ts
        ↓ window.desktop.system.selectFile()
      preload/index.ts → IPC system:select-file
        ↓
      Electron Main → Windows 系统文件对话框
~~~

结论：**前端 Vue 不需要知道 Python 的端口、PID、密钥或解释器路径**。
不要在组件里硬编码 `http://127.0.0.1:8765`：那只在开发模式成立。

## HTTP：现有请求

| 方法与路径 | 请求 | 返回 | 实现 |
| --- | --- | --- | --- |
| `GET /api/health` | 无 | `{status, version}` | `api/routes.py` |
| `POST /api/echo` | `{message: string}` | `{message, from}` | `api/routes.py` |
| `POST /api/tasks/demo` | 无 | `{task_id, status}` | `api/routes.py` |
| `GET /api/tasks/{job_id}` | 无 | `{task_id, status, progress}` | `api/routes.py` |
| `POST /api/tasks/{job_id}/cancel` | 无 | `{task_id, status, progress}` | `api/routes.py` |

未知任务返回 HTTP 404 / `TASK_NOT_FOUND`；输入为空的 echo 返回 422。

前端使用 `window.desktop.backend.request<T>('GET' | 'POST', path, body?)`，
封装示例位于 `src/renderer/src/services/backend-api.ts`。
**当前转发器仅允许 GET / POST 和不带查询参数的 `/api/...` 路径。**
若业务需要 PATCH、DELETE、上传文件或 URL 查询参数，先明确扩展
`src/main/backend-manager.ts` 的请求校验与处理，并补充测试。
不要偷偷绕过主进程直连 Python。

## WebSocket：单向事件与任务进度

连接地址是 `/ws/events`，Electron Main 的 `src/main/event-stream.ts`
持有一个连接；Vue 通过 Preload 事件订阅，不自己建立额外连接。

消息结构：

~~~json
{
  "event": "task.progress",
  "sequence": 7,
  "data": {"task_id": "example-job-id", "progress": 40}
}
~~~

当前事件包括：

| 事件 | 用途 |
| --- | --- |
| `system.connected` | 接入后收到的第一条事件 |
| `system.heartbeat` | 后端周期性心跳 |
| `task.progress` | 任务进度 |
| `task.completed` | 任务完成 |
| `task.cancelled` | 任务取消 |

`sequence` 是**Python 进程内**的递增序号，重启后重置。
这个示例的事件保存在内存中，没有数据库重放、严格送达保证或跨重启恢复。
断线后 Electron Main 自动重连；Vue 应再发 HTTP 请求获取**当前权威状态**，
参照 `TaskDemo.vue` 的 `refresh()`。

新增事件时，使用 `request.app.state.events.publish(name, payload)`
或通过 Service 注入的 `publish` 回调发送，而不是直接修改 Vue DOM。

## IPC：受限系统操作

`src/shared/bridge.ts` 是 TypeScript 契约；
`src/preload/index.ts` 执行有限的 IPC 转发；
`src/main/index.ts` 里的 `registerIpc()` 验证消息确实来自应用主窗口。

目前公开的方法：

| Vue API | 作用 |
| --- | --- |
| `backend.request()` | 请求 Python HTTP 接口 |
| `backend.onEvent()` | 订阅 Python 推送，返回取消订阅函数 |
| `backend.onStatus()` | 订阅 Python 状态 |
| `backend.status()` | 获取 Python 当前状态 |
| `backend.diagnostics()` | 获取后端诊断信息 |
| `backend.retry()` | 重新连接/重启受托管后端 |
| `system.selectFile()` | 打开文件选择对话框 |
| `logging.write(level, source, message)` | Renderer 经认证 IPC 写入 Electron 文件日志 |
| `system.openLogs('electron' / 'python')` | 分别打开前端或后端日志目录 |
| `system.closeWindow()` | 关闭应用窗口 |

不要将整个 `ipcRenderer`、文件系统对象、Node.js 或 Python 控制密钥暴露给 Vue。

## 开发模式 vs 发行模式

| 项目 | 开发 | Windows 绿色发布 |
| --- | --- | --- |
| Python 谁启动 | 单独的终端（`pnpm dev:backend`） | Electron Main `BackendManager` |
| Python 端口 | `127.0.0.1:8765` | Python 监听 localhost 的动态端口 |
| 后端就绪 | Main 检查健康接口 | Python 写临时 ready JSON，Main 验证 PID/session/port 后健康检查 |
| 会话认证 | 模板开发后端不设置会话令牌 | Main 生成随机 `APP_SESSION_TOKEN`，在 HTTP/WS 请求中使用 |
| 关闭 Electron | 不关闭独立 Python | 优雅关闭自己启动的 Python，超时强制结束 |
| Python 意外残留 | 开发者自行管理 | Python 监测父进程句柄并在父进程退出时尝试停止 |

发行版另有仅限 localhost、要求 `APP_CONTROL_TOKEN` 的
`POST /internal/shutdown`，由 Electron Main 请求；它**不是**供 Vue 使用的业务接口。

进程启动路径：`src/main/index.ts` → `backend-manager.ts` → Python `__main__.py`
→ `main.py`（FastAPI 生命周期创建事件中心与 DemoJobs）。
资源组装由 `scripts/build.mjs`、`electron-builder.yml` 完成。

生产主进程在 `APP_DATA_DIR` 指向的数据目录保存 Python 日志和其他数据。
相关日志接口、级别与敏感信息处理见 [日志指南](logging.md)，路径和排错见 [常见问题](troubleshooting.md)。

## 不属于当前模板的保证

- 没有可靠事件队列或跨重启任务存储。
- 没有自动更新、完整业务认证、数据库迁移或 GPU 安装。
- 没有对任意硬件设备的安全停机保证；安全动作需要业务/硬件实现。
- 没有自动为任意 Python 原生依赖收集额外 DLL 的机制。
- 打包版的主进程生命周期回归测试不等于所有 Windows 机型的离线兼容性认证。
