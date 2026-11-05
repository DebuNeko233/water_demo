# 故障定位手册

先分清是前端、Electron、Python、通信还是打包问题。不要遇到问题就先删除整个环境。

## 常见故障与应该检查的文件

| 现象 | 先检查 |
| --- | --- |
| `pnpm dev` 无法打开两个 Windows 终端 | `scripts/dev.mjs`、`scripts/windows-terminal.mjs` |
| Electron 窗口无法启动 | `electron.vite.config.ts`、`src/main/index.ts` |
| 窗口显示 Python offline | 开发 Python 终端、`src/main/backend-manager.ts` |
| HTTP 调用报错 | `services/backend-api.ts`、Preload、Main IPC、`api/routes.py` |
| WebSocket 不更新 | `event-stream.ts`、`api/websocket.py`、`services/event_hub.py` |
| 开发正常，绿色版错误 | `scripts/build.mjs`、`resources/backend/manifest.json` |
| 退出后还有 Python 进程 | `backend-manager.ts` 和 Python `__main__.py` |

## Electron uninstall / electron-vite 能编译却打不开窗口

Electron 42+ 不再在 `pnpm install` 的 `postinstall` 中自动下载二进制，`electron-vite dev` 却需要先找到 `electron/path.txt`。模板已通过 `scripts/ensure-electron.mjs` 在 `pnpm dev:frontend`、`pnpm build` 中自动补齐缺失的 Electron 运行文件。

如安装期间 GitHub Releases 网络不可达，可先手工执行：

~~~powershell
pnpm electron:setup
pnpm dev:frontend
~~~

此步骤只下载项目已经声明的 Electron 版本；不改变 `package.json`、Node.js、Python 或 uv。不要直接删除整个 `node_modules` 来处理这个问题。下载失败时检查网络/代理，或按 Electron 官方文档配置下载镜像。

## 开发启动失败

手动分别启动前后端的完整步骤见 [手动启动指南](manual-start.md)。尝试在不同 PowerShell 终端（均位于项目根目录）分别执行：

~~~powershell
pnpm dev:backend
pnpm dev:frontend
~~~

若单独启动正常，一键启动有问题，执行：

~~~powershell
pnpm test:scripts
~~~

## 直接运行 main.py 时 ImportError

不要在 `backend/src/sample_backend/` 执行 `uv run .\main.py`。这是包内模块，带有 `from .api...` 相对导入；请回到 `backend/` 后运行：

~~~powershell
cd backend
uv run python -m sample_backend --dev
~~~

如果当前已经在 `backend/src/sample_backend/`，先运行 `cd ..\..`。若系统无法识别 `uv`，从**项目根目录**运行 `pnpm dev:backend`，由脚本使用已安装或自动下载的 uv。详见 [手动启动指南](manual-start.md)。

## Python offline

开发模式监听 `127.0.0.1:8765`。如果启动较慢，后端成功启动后按界面的“重新连接”。

检查端口：

~~~powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
~~~

开发模式可打开 `http://127.0.0.1:8765/docs` 查看 FastAPI OpenAPI。
**发行版使用动态端口，不能假设仍然是 8765。**

## Python 文件被占用或需要换版本

Windows 会锁定运行中的 Python 文件。先关闭 Python 终端和它启动的任务，再执行：

~~~powershell
pnpm python:use 3.11
pnpm python:info
~~~

它会重建整个 `backend/.venv`，但不清理用户数据、模型文件或全局 uv 缓存。

## 绿色版无法启动后端

首先确认复制的是**整个** `dist/win-unpacked/`，而非只有 `SampleApp.exe`。

检查 `dist/win-unpacked/resources/backend/manifest.json` 与其中的 Python 路径；
确认业务包、模型、原生扩展和 SDK DLL 已随发行包存在。

开发机上的完整打包冒烟测试：

~~~powershell
node scripts/smoke/backend.mjs
node scripts/smoke/electron.mjs
node scripts/smoke/parent-exit.mjs
~~~

依次测试包内 Python、真实 Electron 调用及异常退出。它们不会自动覆盖 CUDA、摄像头驱动、厂商 SDK。

## pnpm build 为什么会联网？

`scripts/build.mjs` 优先复用 uv 管理的 Python。相同版本应显示
`[build] Reusing local Python: ...`；
本机首次安装该版本仍需要下载一次。

这不等于所有依赖都永远不联网：缺少的 Electron、Python Wheel 或 npm/uv 缓存仍可能触发下载。
`pnpm clean` 不清理全局 uv 缓存。

## 日志放在哪里？

完整写法、级别、日志保存和隐私规范见 [日志指南](logging.md)。

- 开发后端：`%USERPROFILE%\.python-electron-vue-sample\logs\backend.log`。
- 绿色版后端：Electron `app.getPath('userData')/data/logs/backend.log`。
- 绿色版 Electron：同目录 `electron.log`。
- Electron 用户数据目录随实际系统用户和应用标识变化，请使用界面的“打开日志目录”。

不要把日志里的秘密令牌或真实业务数据直接上传到公开仓库。

## 侧边栏点击没有反应

现在导航状态在 `App.vue`，菜单数据在 `navigation.ts`，
按钮在 `AppSidebar.vue`，显示逻辑在 `views/HomeView.vue`。
确保已退出旧 Electron 窗口、拉取新代码并重新启动。
正式包 `smoke-electron.mjs` 包含实际菜单切换测试。

## 排查顺序建议

1. 留下第一条明确错误、复现步骤、开发版/绿色版和 Python 版本。
2. 先运行 `pnpm test:backend` 与 `pnpm typecheck`。
3. 再运行实际相关的进程测试或 `pnpm build`。
4. 只修必要文件，并为故障添加回归测试。
5. 不要靠关闭 Electron 安全防护、禁用 IPC 校验或让 Vue 直连 Python 来掩盖问题。

## 功能边界

本模板没有自动更新、数据库、持久任务队列、完整业务登录系统、自动 SDK/DLL 打包、
跨平台发布保证或面向设备的安全停机机制。这些都应在具体业务需求出现后单独设计。

## 没有安装 uv / 自动引导下载失败

`pnpm dev`、`pnpm test:backend`、`pnpm python:use`、`pnpm build` 会检测系统 uv，必要时自动下载官方 SHA-256 校验的项目本地 uv。开发机首次需能访问 GitHub Releases；如公司代理或防火墙无法访问，会报明确错误。可手工安装 uv 后重试，或在能够联网的开发机准备好对应 `.tools/uv/`。详见 [uv 自动引导](uv-bootstrap.md)。
