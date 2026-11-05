# 上手教程：从零启动到完成第一次修改

目标：**不需要读过之前的聊天记录，也能使用、理解和验证这个模板**。

## 0. 先了解你运行的是什么

这个仓库包含三个不同的运行部分：

- **Vue Renderer**：窗口里看到的页面，在 `src/renderer/src/`；不能直接访问 Node.js 和 Python。
- **Electron Main + Preload**：启动桌面窗口、控制系统权限、代理 API、连接 WebSocket，代码在 `src/main/`、`src/preload/`。
- **Python FastAPI**：执行真正的业务接口和任务，在 `backend/src/sample_backend/`。

读代码建议顺序：`src/renderer/src/App.vue` → `views/HomeView.vue` →
`components/EchoDemo.vue` → `services/backend-api.ts` → `src/preload/index.ts` →
`src/main/index.ts` → `src/main/backend-manager.ts` →
`backend/src/sample_backend/main.py` → `api/routes.py`。

完整的调用路径见 [通信协议](communication.md)。

## 1. 开发机首次运行

当前重点平台：Windows x64。安装 **Node.js 22+、pnpm** 即可，**uv 无需手工安装**：首次需要 Python 时自动执行 `uv self version` 检测系统 uv；系统没有 uv 才下载官方二进制到项目 `.tools/uv/`。首次下载需联网，且会校验官方 SHA-256。
在 PowerShell 的项目根目录执行：

~~~powershell
pnpm install
pnpm dev
~~~

- Windows 下 `pnpm dev` 打开两个独立终端，分别运行 Python、Electron/Vue；`pnpm dev:combined` 则使用一个终端统一运行两个进程。
- Python 环境缺失时，uv 自动创建 `backend/.venv` 并安装依赖；没有 uv 时先执行项目本地引导。
- 正常运行时页面显示 `Python ready`，侧边栏可以切换“应用概览、HTTP 示例、实时任务、IPC 示例”。
- 如果 Electron 先起来而 Python 尚未就绪，等待后点击界面里的“重新连接”。

想**手动分别启动前后端**时，请打开两个独立的 PowerShell 窗口，均从项目根目录执行：

**终端 1 · Python FastAPI 后端：**

~~~powershell
pnpm dev:backend
~~~

**终端 2 · Electron + Vue 前端：**

~~~powershell
pnpm dev:frontend
~~~

后端开发模式使用 `127.0.0.1:8765`；单独关闭 Electron **不会结束**后端进程，各终端可以用 `Ctrl+C` 结束。

如果希望**完全独立使用 uv 命令**启动 Python，也可以从 `backend/` 目录执行 `uv run python -m sample_backend --dev`（不要直接运行 `main.py`）。
工作目录区别、Uvicorn 入口、未预装 uv 时的用法和 `Electron uninstall` 处理方法详见 [分别手动启动前后端](manual-start.md)。

## 2. 不读源码也能执行的四个实验

| 页面 | 操作 | 你应该观察到 |
| --- | --- | --- |
| HTTP 示例 | 输入文字并点击“发送” | 收到 `Python / FastAPI` 返回的消息 |
| 实时任务 | 启动任务、观察事件，再尝试取消 | 任务有 ID、进度和最终状态 |
| IPC 示例 | 点击“选择文件”和“打开日志目录” | Windows 文件对话框和日志文件夹 |
| 侧边栏 | 任务运行中切换到 HTTP 后再切回来 | 原任务 ID 与状态没有被切换操作清空 |

页面只是示例，不包含账号系统、数据库、摄像头驱动或 GPU 推理。

## 3. 第一次修改源码：沿已有示例学习

最短的练习是修改后端回显接口 `backend/src/sample_backend/api/routes.py` 中
`echo()` 返回的 `from` 字段，然后在 HTTP 示例页面点击“发送”。

要新增一个自己的功能，请按 [业务扩展实战](extend-features.md)
依次修改后端 Service、API、前端 Service、Vue 组件和测试，而不是修改打包器。

修改后端 Python：开发模式支持 Uvicorn 自动重新加载。
修改 Vue 组件：Vite 负责页面热更新。
修改 Electron Main 或 Preload：开发服务器可能重启 Electron，需要重新验收相关 IPC。

## 4. 检查、测试、构建

项目根目录：

~~~powershell
pnpm test:backend
pnpm typecheck
pnpm test:scripts
~~~

需要打包绿色目录时，在 **Windows x64** 执行：

~~~powershell
pnpm build
~~~

成功产物在 `dist/win-unpacked/`。
必须复制整个文件夹，不能只复制 `SampleApp.exe`。

打包过程复制 uv 缓存中已经安装的 Python 解释器，缺少对应版本时才下载；
构建使用独立运行时，不依赖最终用户安装 Python、Node.js 或 uv。下载 uv 只发生在开发/构建机，**不会进入绿色软件**。

可在 [GitHub Actions](../.github/workflows/quality.yml) 查看自动化验证：
Python 测试、TypeScript、构建、打包的 Python 通信测试、打包的 Electron
通信和菜单测试、强制结束 Electron 后 Python 清理测试。

## 5. 切换 Python 版本

先关闭单独运行的 Python 开发终端，再执行：

~~~powershell
pnpm python:use 3.11
pnpm python:info
pnpm dev
~~~

`python:use` 会**删除整个 `backend/.venv` 并重新创建环境**，
但不删除源码、用户数据、模型或 uv 缓存。
切回默认版本：

~~~powershell
pnpm python:use 3.12
~~~

依赖与锁文件的兼容性依然受实际 Python 版本和 Wheel 支持情况约束。

## 6. 什么时候算学会了这个样例？

- 能解释 Vue → Preload → Electron Main → FastAPI 的 HTTP 路径。
- 能解释 WebSocket 事件如何从 Python 返回 Vue。
- 能在 `api/` + `services/` 添加一个 API，并在 Vue 组件成功调用。
- 知道为什么开发版不杀后端、而绿色版退出时必须清理后端。
- 会运行 Python 测试和 TypeScript 检查，也会查看日志排错。
- 不依赖前述聊天记录，能独立添加、测试、打包一个小功能。

继续阅读：[uv 自动引导](uv-bootstrap.md) · [依赖管理](dependencies.md) · [目录约定](project-structure.md) · [通信协议](communication.md) ·
[业务扩展实战](extend-features.md) · [常见问题](troubleshooting.md)。
