# Python FastAPI Backend

This is an installable Python package. You can run it independently from Electron.

从仓库根目录运行（**无需预装 uv**，脚本自动检测/下载）：

~~~powershell
pnpm dev:backend
pnpm test:backend
pnpm python:info
pnpm python:use 3.11
~~~

也可以在 **`backend/` 目录**直接手动启动（此方式要求 `uv` 已可在 PATH 中调用）：

~~~powershell
uv run python -m sample_backend --dev
~~~

或使用 Uvicorn：

~~~powershell
uv run uvicorn sample_backend.main:app --host 127.0.0.1 --port 8765 --reload
~~~

**不要在 `src/sample_backend/` 里运行 `uv run .\main.py`**：`main.py` 的 `from .api...` 相对导入需要包上下文，必须通过 `-m sample_backend` 或 `sample_backend.main:app` 加载。两种手动启动方式只能任选其一，以免占用相同端口。参见 [前后端分别手动启动指南](../docs/manual-start.md)。

- `src/sample_backend/__main__.py`：命令行启动、开发热重载、发行版就绪文件与父进程监测。
- `src/sample_backend/main.py`：FastAPI 应用工厂、中间件、lifespan、Service 装配。
- `src/sample_backend/api/`：HTTP、WS 与受保护的内部关闭端点。
- `src/sample_backend/services/`：纯业务逻辑和事件/任务服务。
- `src/sample_backend/core/`：环境配置与 Loguru 日志。
- `tests/`：HTTP、任务取消和应用装配测试。

开发独立服务监听 `127.0.0.1:8765`；正式绿色版使用由 Electron 托管的动态端口。
发行版独立 Python 运行时通过 `pnpm build` 构建，不复制这里的 `.venv`。

继续阅读：[完整业务扩展教程](../docs/extend-features.md)、
[通信契约](../docs/communication.md)。
