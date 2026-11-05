# 自动安装 uv：开发机无需预装

本模板的 Node.js 开发脚本会自动寻找 uv。**最终运行绿色软件的电脑不需要 uv，且软件不会从网络下载安装 uv。**

## 检测与安装顺序

1. 尝试系统命令 `uv self version`，只有成功且返回 `uv x.y.z` 才采用它。
2. 系统没有可用 uv，则检查被 Git 忽略的 `.tools/uv/0.13.5/<系统-架构>/uv.exe`（Windows），或 `uv`（macOS/Linux）。
3. 本地也不存在，则从 [Astral uv 官方发布页面](https://github.com/astral-sh/uv/releases) 下载 **uv 0.13.5** 的对应二进制压缩包和它的 `.sha256` 文件。
4. 对下载归档计算 SHA-256 并严格比较官方发布的值；只有一致才提取二进制，通过 `uv self version` 检查后原子写入本地缓存。
5. 下次重复使用，不再下载。两次并发请求通过下载锁避免重复安装。

该版本是**自动引导的已知兼容版本**，不是固定 Python 的版本；系统已安装的 uv 会优先使用。要升级本地引导版本可在 `scripts/uv-bootstrap.mjs` 中修改 `BOOTSTRAP_UV_VERSION` 并运行 CI 验证。

## 哪些命令自动引导？

~~~powershell
pnpm dev
pnpm dev:backend
pnpm test:backend
pnpm python:info
pnpm python:use 3.11
pnpm build
~~~

只执行 `pnpm install` 安装前端依赖，不需要 uv。
单独执行 `pnpm dev:frontend` 只启动 Electron/Vue，也不需要 uv。

## 下载位置和支持的系统

- Windows x64：`.tools/uv/0.13.5/win32-x64/uv.exe`
- Windows ARM64、Linux x64/ARM64、macOS Intel/Apple Silicon：自动选择官方对应归档。
- 其他系统：提示手工安装，不会猜测不兼容的可执行文件。

`.tools/` 被 `.gitignore` 忽略，不会提交到 Git；且没有写入系统 PATH，不会修改全局 uv 或 Windows 安装目录。
Python 解释器仍由 uv 管理并复用，发行构建只会把独立 Python 复制到 `resources/backend/runtime`，**不会把本地 uv 工具复制到绿色目录**。

## 网络问题

仅在**系统 uv 和本地缓存都不存在**时需要下载 uv。
首次下载时必须能连接到 GitHub Releases；离线、代理阻断、校验失败都会拒绝安装并给出明确报错。
遇到无法下载，可用开发机的标准方式手工安装 uv，然后重新执行命令。

自动引导仅运行 Node.js 和系统自带的 `tar` 解压官方归档；不执行从互联网直接获取的 PowerShell/Shell 安装脚本。

## 验证

~~~powershell
pnpm test:scripts
pnpm test:backend
pnpm build
~~~

CI 包含无网络单元测试和 Windows **模拟系统没有 uv 的官方二进制下载安装测试**。
