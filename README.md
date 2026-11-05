# Python + Electron + Vue 桌面应用模板

基于 **Electron + Vue 3 + TypeScript + Python FastAPI + uv** 的轻量级 Windows 桌面应用模板。前后端分离开发，内置可运行的 IPC、HTTP、WebSocket 示例，支持独立 Python 运行时的绿色软件打包。

**仓库名** `python-electron-vue-template` 只表示这是可复用的模板；示例应用仍叫 `SampleApp`，后端 Python 包仍叫 `sample_backend`，避免无意义的运行时破坏性重命名。

## 核心能力

- **Electron 自动安装**：首次启动或打包前检查 Electron 可执行文件，缺失时使用官方安装脚本按需下载，不用手动处理 `Electron uninstall`。
- **一键开发**：`pnpm dev` 在 Windows 下分别打开 Python 和 Electron/Vue 开发终端，支持独立调试与热更新。
- **三种通信**：Electron IPC（桌面系统操作）、HTTP（业务请求）、WebSocket（实时事件和任务进度）。
- **Python 环境管理**：自动检测 `uv self version`；没有 uv 时下载校验后的项目本地 uv，管理解释器和依赖。
- **绿色打包**：`pnpm build` 生成包含独立 Python 的 Windows x64 应用目录，最终用户无需安装 Python 或 Node.js。
- **可靠的运行管理**：开发后端独立运行，发行版由 Electron 管理后端启动、连接、日志及退出。
- **可扩展的代码结构**：Vue 按视图、组件、组合式函数和服务组织；FastAPI 按路由、业务服务和基础配置组织。

## 快速开始

开发环境：**Windows x64、Node.js 22+、pnpm**。**无需预装 uv**：首次使用 Python 功能时会自动检查或下载 uv 到项目本地 `.tools/uv/`（需要联网）。

```powershell
git clone https://github.com/DebuNeko233/python-electron-vue-template.git
cd python-electron-vue-template
pnpm install
pnpm dev
```

启动后可在界面中尝试 **HTTP 回显、WebSocket 任务进度及取消、Electron 文件选择** 等示例。需要自己分别启动两个服务时，查看 [前后端手动启动指南](docs/manual-start.md)。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `pnpm dev` | 检测/引导 uv 后一键启动开发环境 |
| `pnpm dev:combined` | 前后端在同一个终端运行，方便集中查看输出 |
| `pnpm dev:frontend` | 仅启动 Electron/Vue |
| `pnpm dev:backend` | 仅启动 Python/FastAPI |
| `pnpm python:use 3.11` | 切换 Python 版本并重建 `.venv`（先关闭正在运行的 Python） |
| `pnpm test:backend` | 运行 Python 测试 |
| `pnpm test:scripts` | 运行辅助脚本的 Node.js 单元测试 |
| `pnpm typecheck` | 检查 TypeScript/Vue |
| `pnpm electron:setup` | 检查并按需安装 Electron 运行文件 |
| `pnpm build` | 构建 Windows x64 绿色应用目录 |

## 构建与运行

```powershell
pnpm build
```

构建产物位于 `dist/win-unpacked/`。将**整个目录**复制到目标 Windows 电脑，运行其中的 `SampleApp.exe`，不要只复制 EXE。

如果本机没有 uv，构建脚本会先自动下载校验到 `.tools/uv/`，然后优先复用 uv 已安装的 Python 版本。发行包包含独立解释器和项目依赖，不依赖开发用的 `.venv`。

## 项目结构

```text
src/
├── main/                 # Electron 主进程、Python 生命周期管理
├── preload/              # 安全 IPC 桥接
├── shared/               # 前后端桥接的 TypeScript 类型
└── renderer/src/
    ├── views/            # 页面
    ├── components/       # 功能组件
    ├── composables/      # 状态与事件订阅
    ├── services/         # HTTP / IPC 调用
    └── styles/           # 样式

backend/src/sample_backend/
├── api/                  # FastAPI HTTP / WebSocket 接口
├── services/             # Python 业务逻辑和任务
├── core/                 # 配置与日志
├── main.py               # FastAPI 应用装配
└── __main__.py           # Python 启动入口
```

## 文档

| 文档 | 内容 |
| --- | --- |
| [快速上手](docs/getting-started.md) | 首次运行与示例操作 |
| [分别手动启动前后端](docs/manual-start.md) | 两个终端启动、纯 uv/Uvicorn 启动、路径与常见错误 |
| [架构与通信协议](docs/communication.md) | Vue、Electron、Python 的通信过程 |
| [目录规范](docs/project-structure.md) | 代码应放在哪个模块 |
| [扩展功能教程](docs/extend-features.md) | 完整新增一个 Python + Vue 业务功能 |
| [项目定制](docs/customization.md) | 应用名称、Python 依赖与发行资源 |
| [依赖管理](docs/dependencies.md) | 不提交 lock 文件、版本范围和兼容性验证 |
| [日志规范](docs/logging.md) | 前后端日志写法、级别、保存位置与敏感信息规范 |
| [故障排查](docs/troubleshooting.md) | 常见问题及日志位置 |
| [AI 开发约定](AGENTS.md) | AI 或新开发者接手项目的规范 |
| [更新日志](CHANGELOG.md) | 版本历史、功能调整与修复记录 |

当前重点支持 **Windows x64**。涉及 CUDA、摄像头、硬件 SDK 或其他原生依赖的业务，需要在目标设备上额外验证。
