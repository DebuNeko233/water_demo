# Architecture / 架构边界

三个职责明确的层：

- **Vue Renderer** 只负责界面和业务交互，不直接访问 Node.js。
- **Electron Main / Preload** 负责系统权限、HTTP/WebSocket 连接与托管 Python 进程。
- **Python FastAPI** 负责所有后端业务，不依赖 Electron。

Vue 使用受限的 `window.desktop` API；Electron 使用 HTTP 请求和单个 WebSocket 连接与 Python 通信。
发行模式使用随机会话令牌、动态端口与就绪文件握手，令牌不交给 Vue。

开发模式下 FastAPI 监听本机 8765 端口，可独立启动；Electron 不会关闭一个自己没有创建的 Python 进程。
发行模式由 Electron 启动内置 CPython，正常退出时请求 Uvicorn 优雅停止，超时后清理进程树。
Python 同时监测 Windows 父进程句柄，减轻 Electron 异常退出后 Python 残留的风险。

用户数据放入 Electron `userData` 目录，发布资源只读。Python 日志位于 `data/logs/backend.log`，
Electron 日志位于 `data/logs/electron.log`。开发环境下 Python 日志位于用户主目录的
`.python-electron-vue-sample/logs`。

坚持最小抽象：不将业务塞入 Electron，不增加无需求的插件系统、认证账号或 GPU 框架。

## Diagnostics and task lifecycle

`BackendManager` retains a human-readable startup/exit error and exposes a retry IPC method. A WebSocket connection shared by Electron Main forwards events to Vue. Stale close callbacks from replaced sockets must not mark a new connection offline.

Demo tasks support start, status, and cancellation. A reconnecting renderer retrieves the authoritative task state through HTTP instead of guessing from missed WebSocket events.

Windows CI exercises both graceful shutdown and forced Electron termination. The latter verifies the Python watchdog, not a forced child-process kill. Applications controlling physical hardware still require their own safety shutdown procedures.

## 标准项目目录

Vue 界面按 `views/components/composables/services` 整理；Python 按 `api/services/core` 整理。启动入口与 Electron 进程管理仍独立。目录与扩展示例见 [project-structure.md](project-structure.md)。
