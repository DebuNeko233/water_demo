# 分别手动启动前端与后端（Windows PowerShell）

本页演示如何**自己分别启动、调试和停止** Electron + Vue 前端与 Python FastAPI 后端；不使用一键 `pnpm dev`。所有命令都对应本仓库现有的 `package.json` 和 `sample_backend/__main__.py`。

## 运行前准备

在**项目根目录**（能看到 `package.json` 和 `backend/` 的目录）安装前端依赖：

~~~powershell
pnpm install
~~~

开发电脑需要 Node.js 22+ 和 pnpm。**不需要预装 Python 或 uv**：从根目录执行 `pnpm dev:backend` 时，项目会检查 `uv self version`，如无系统 uv 则自动下载经过校验的项目本地版本，并由 uv 安装所需 Python 与后端依赖。首次安装需要网络连接。

## 方式 A：两个 PowerShell 窗口，分别启动（推荐）

### 终端 1：单独启动 Python 后端

在项目**根目录**运行：

~~~powershell
pnpm dev:backend
~~~

这实际调用 `scripts/python.mjs`，最终运行：

~~~powershell
uv run python -m sample_backend --dev
~~~

区别是 `pnpm dev:backend` 负责**自动寻找/下载 uv**；而直接输入 `uv ...` 要求系统 PATH 已能找到 uv。

开发后端绑定 `127.0.0.1:8765`，支持 Python 代码修改后自动重载。启动后可访问：

- [FastAPI API 文档](http://127.0.0.1:8765/docs)
- [后端健康检查](http://127.0.0.1:8765/api/health)

### 终端 2：单独启动 Electron + Vue 前端

另开一个 PowerShell 窗口，在项目**根目录**运行：

~~~powershell
pnpm dev:frontend
~~~

此命令会先检查 Electron 是否已安装二进制；必要时调用 Electron npm 包自带的安装程序，然后启动 `electron-vite dev`。你会看到 Vite 开发服务（通常是 `http://localhost:5173/`）及 Electron 桌面窗口。

**这是 Electron 桌面应用，不只是浏览器网页。** 请使用打开的 Electron 窗口体验文件选择、Preload IPC 和与 Python 的通信；单独用普通浏览器打开 Vite 地址不具备全部桌面功能。

推荐先启动后端，再启动前端。若先打开前端而显示 `Python offline`，待后端启动后在窗口中点击“重新连接”。

### 单独停止

两个窗口分别按 `Ctrl+C` 结束相应开发进程。开发模式下，**关闭 Electron 不会自动关闭你手动启动的 Python 后端**。再次运行时如果 `8765` 端口被占用，先检查是否已有后端实例在运行。

## 方式 B：直接在 backend 目录运行 Python 模块

如果你希望不经过 pnpm 启动 Python，而是在 Python 项目目录中手动运行，请先确认 **uv 可以通过命令行直接调用**。

在项目根目录：

~~~powershell
cd backend
uv run python -m sample_backend --dev
~~~

也可以直接使用 Uvicorn 入口，效果相当：

~~~powershell
cd backend
uv run uvicorn sample_backend.main:app --host 127.0.0.1 --port 8765 --reload
~~~

上面两组命令**二选一**，不要同时运行（它们都使用 8765 端口）。

如果你当前已经在 `backend/src/sample_backend/`：

~~~powershell
cd ..\..
uv run python -m sample_backend --dev
~~~

> **不要运行 `uv run .\main.py` 或 `python main.py`。** `main.py` 通过 `from .api... import ...` 使用包内相对导入，必须让 Python 以 `sample_backend` 包的方式加载，否则就会报 `ImportError: attempted relative import with no known parent package`。
>
> 另外，`uv run python -m sample_backend` **不带 `--dev`** 时，会进入给打包版使用的托管模式（动态端口），不是开发时的 8765 端口，因此自己手动调试要带 `--dev`。

如果你没有安装全局 uv、只是使用了本项目自动下载的 uv，直接输入 `uv` 不一定能找到程序；此时使用上面的 `pnpm dev:backend` 即可，它会自动选择本地缓存中的 uv，不必修改系统 PATH。

## 方式 C：跳过 npm 启动器，直接启动 Electron

仍需在项目**根目录**：

~~~powershell
pnpm electron:setup
pnpm exec electron-vite dev
~~~

`pnpm electron:setup` 用于确保 Electron 运行文件存在。如果未先准备好二进制，直接运行 `electron-vite dev` 可能出现 `Error: Electron uninstall`。因此通常更推荐 `pnpm dev:frontend`。

## 常见现象与检查

| 现象 | 处理 |
| --- | --- |
| `ImportError: attempted relative import with no known parent package` | 回到 `backend/`，用 `uv run python -m sample_backend --dev`，不要直接执行 `main.py` |
| `uv` 不是内部或外部命令 | 从根目录运行 `pnpm dev:backend`，自动检查/下载项目本地 uv |
| Electron 报 `Electron uninstall` | 从根目录运行 `pnpm electron:setup`，或直接用 `pnpm dev:frontend` |
| 前端显示 `Python offline` | 确认后端在 `127.0.0.1:8765` 运行，然后点“重新连接” |
| 端口 8765 已被占用 | 停止原有后端，不要同时运行两份开发后端 |
| 只有浏览器里的 Vite 页面 | 打开 Electron 桌面窗口，桌面 IPC 功能依赖 Preload |

相关资料：[完整上手教程](getting-started.md) · [故障排查](troubleshooting.md) · [uv 自动引导](uv-bootstrap.md) · [通信协议](communication.md)。
