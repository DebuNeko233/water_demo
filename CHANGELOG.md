# 更新日志（Changelog）

本文件记录版本发布、功能变化、可靠性改进及构建行为调整。项目介绍、启动命令和开发文档请查看 [README](README.md)。

## [Unreleased]

### 仓库名称更新

- GitHub 仓库更名为 `DebuNeko233/python-electron-vue-template`；同步修改 README 克隆命令、历史标签链接和 npm 包元数据。
- 示例应用 `SampleApp`、Python 包 `sample_backend`、应用 ID 和现有用户数据路径保持不变，以免仓库更名影响运行行为；已经发布的 `1.1` 标签不变。

### 源码可读性

- 为 Electron Main/Preload、Vue 异步事件与状态、FastAPI 生命周期及鉴权、Python 子进程监测、uv/Electron 自动安装、Windows 打包和进程冒烟测试补充中文注释，着重解释权限边界、资源所有权和异常分支。
- 在 `AGENTS.md` 增加注释约定：注释应解释设计原因、兼容性和风险，不重复显而易见的语法。本轮无意调整功能与协议，`1.1` 标签保持不变。

## [1.1.0]

### 文档补充

- 新增 [前后端分别手动启动指南](docs/manual-start.md)，写明双 PowerShell 终端独立启动、在 `backend/` 通过 `uv run python -m sample_backend --dev` 或 Uvicorn 启动、Electron 直接运行以及停止和排错步骤；解释为什么直接运行 `main.py` 会触发相对导入错误。

### 脚本维护

- 合并开发进程脚本：`pnpm dev` 仍在 Windows 打开独立终端，`pnpm dev:combined` 复用 `scripts/dev.mjs --combined`。
- 将 Node 单元测试整理到 `scripts/tests/`，提供 `pnpm test:scripts` 统一执行；将打包冒烟测试整理到 `scripts/smoke/`，通过共享函数减少进程状态检查与清理代码重复。
- 将 Windows 子进程参数校验模块移动到 `scripts/lib/`，保留安全回归测试。更新 CI 与文档引用，避免脚本迁移后出现失效命令。

### Electron 开发启动修复

- 适配 Electron 42+ 的延迟下载机制：`pnpm dev:frontend` 和 `pnpm build` 启动前检查已安装的 Electron 版本、`path.txt` 和二进制路径，缺失时调用当前 Electron npm 包自带的官方 `install.js`，避免 `electron-vite` 抛出 `Error: Electron uninstall`。
- 提供 `pnpm electron:setup` 自检/手动修复入口和缺失文件的回归测试；下载结果会复用，不引入新的包或系统安装。

### 开发环境改进

- 开发电脑无需预装 uv：先运行 `uv self version` 检测系统命令；没有 uv 时自动从官方 GitHub Releases 下载受 SHA-256 校验的 uv 到项目内 `.tools/uv/`，重复运行复用本地文件。
- 将同一引导入口接入 `pnpm dev`、后端测试、Python 版本切换及 `pnpm build`，增加下载互斥锁、离线失败提示与 Windows 真实下载验证。绿色发行包不包含 uv。

### 依赖策略

- 将模板调整为**无跟踪锁文件模式**：移除 `pnpm-lock.yaml` 和 `backend/uv.lock`，禁用 pnpm 锁文件生成，允许 uv 仅在本地生成被忽略的依赖解析文件；`pnpm build` 与 CI 不再要求 `--locked` 或 `--frozen-lockfile`。
- 保留 `package.json`、`backend/pyproject.toml` 的兼容版本约束，通过自动测试、Windows 绿色打包和实际进程测试验证依赖升级；新增 [依赖管理指南](docs/dependencies.md)。

### 功能与文档

- 增加 Vue Renderer 统一日志工具，通过受限 IPC 写入 Electron 的 `electron.log`；HTTP 与文件选择示例演示日志用法。
- 开发模式下分别提供打开前端与后端日志目录的入口；Python 任务示例补充启动、完成、取消事件日志。
- 新增面向人类和 AI 的日志使用与规范文档，明确级别、轮转、存储位置、错误处理和敏感信息禁录约定。
- 打包版 Electron 冒烟测试增加 Renderer 日志落盘验证。

### 修复

- 修复 Windows 下 `pnpm build` 调用 pnpm/npm 时的 Node.js `[DEP0190]` 弃用警告：不再向 `shell: true` 的子进程传入参数数组，改为受限参数的显式 `cmd.exe` 调用，并补充 Windows 回归测试。

### 文档

- 精简 README，使其专注于项目定位、核心能力、快速启动、构建和学习入口。
- 将历史功能迭代、可靠性改进和构建缓存说明集中到本文件，便于追踪版本变化。

## [1.0.0] - 2026-10-27

首个稳定基线：Electron + Vue 3 + TypeScript + FastAPI + uv 的 Windows x64 桌面应用模板。

### 开发体验

- 支持 `pnpm dev` 分别启动 Python 后端与 Electron/Vue 前端，前后端均可独立调试。
- Windows 双终端启动改用 PowerShell `Start-Process`，修复原先将 `"Python backend"` 误识别为文件名的命令行引号问题。
- 通过 uv 管理 Python 版本及依赖；切换 Python 版本时删除并重建整个开发 `.venv`。
- 前端代码拆分为 `views/`、`components/`、`composables/`、`services/`，后端拆分为 `api/`、`services/`、`core/`。

### 通信与界面

- 提供 Electron IPC、FastAPI HTTP 和 WebSocket 的可运行示例。
- 增加 Python 后端离线/失败的诊断提示及手动重新连接入口。
- 示例任务增加状态查询、取消功能；WebSocket 重新连接后可通过 HTTP 获取任务当前状态。
- 修复旧 WebSocket 连接迟到的关闭事件干扰新连接状态的问题。
- 侧边栏由静态锚点调整为真正的页面切换按钮，支持“应用概览、HTTP 示例、实时任务、IPC 示例”；切换时保留正在运行的任务界面状态。
- 开发版的“打开日志目录”优先打开独立 Python 的日志目录，发行版打开应用数据目录中的日志。

### Python 发行与进程管理

- 发行版由 Electron 自动启动内置 Python，使用动态本机端口、随机会话令牌和就绪握手。
- 正常关闭时请求后端优雅退出；超时后清理受托管进程。Python 通过父进程监测处理 Electron 意外终止的场景。
- 构建发行包时复制**独立的 CPython 运行时**，不复制开发用 `.venv`，最终用户无需安装 Python、Node.js 或 uv。
- **修复重复下载 Python 的问题**：构建优先通过 `uv python find` 查找本机已安装的 uv-managed Python，并复制至干净的发行目录；只有缺少指定版本时才通过 `uv python install` 安装一次。
- 每次构建仍会重新生成发行目录并安装项目正式依赖，避免发布产物引用开发机的虚拟环境或修改全局解释器。
- `pnpm clean` 只清理项目生成的构建文件，不删除 uv 的全局 Python 安装及依赖缓存。

### 测试与文档

- 提供 Python API、后台任务、任务取消、应用装配等测试，以及 TypeScript/Vue 类型检查。
- Windows CI 验证绿色目录、包内 Python HTTP/WebSocket、会话认证、日志、正常退出，以及打包的 Electron 启动与通信。
- 增加仅强制结束 Electron 的回归测试，检查受托管 Python 能通过父进程监测自行退出。
- 增加实际侧边栏导航和任务状态保留的打包版 Electron 冒烟测试。
- 提供首次运行、通信契约、目录说明、业务扩展示例、项目定制、故障排查及 AI 开发约定文档。
- 增加文档内部链接检查，降低重构后出现失效说明的风险。

### 已知范围

- 当前发行目标为 Windows x64。
- 未内置自动更新、业务数据库、持久化任务队列或 GPU/硬件 SDK 通用封装。
- 原生 DLL、模型、驱动及设备安全停机需在具体业务和目标电脑上单独验证。

[1.0.0]: https://github.com/DebuNeko233/python-electron-vue-template/tree/1.0.0
