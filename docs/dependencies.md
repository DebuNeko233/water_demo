# 依赖管理：不提交 lock 文件的模板模式

此仓库定位为可以直接复用的**起始模板**。按你的要求，优先使用 **兼容版本范围**，而不是把某次安装的全部间接依赖锁死并提交到 Git。

## 实际策略

| 部分 | 声明位置 | Lock 文件策略 | 安装方式 |
| --- | --- | --- | --- |
| Vue / Electron / Node 依赖 | `package.json` | **禁用** `pnpm-lock.yaml`（`pnpm-workspace.yaml` 中设置 `lockfile: false`） | `pnpm install` |
| Python 运行时依赖和测试依赖 | `backend/pyproject.toml` | 不提交 `backend/uv.lock`；uv 项目命令在本地**可能自动生成**，并由 `.gitignore` 忽略 | `uv sync --project backend` |
| Python 解释器版本 | `backend/.python-version` | 与依赖锁文件无关 | `pnpm python:use 3.12` |
| 绿色软件 | `scripts/build.mjs` | 采用**构建时解析的依赖集合**；构建期间的 `uv.lock` 只用于保持同一次构建内的解析一致 | `pnpm build` |

`pnpm install` 不读取、也不生成 `pnpm-lock.yaml`。
`uv sync` / `uv run` / `uv export` 仍是 uv 的标准项目命令，会维护本地 `backend/uv.lock`；它不属于需要提交的源码。
如果要**连本地 uv.lock 都不生成**，就需要放弃 uv 的项目同步工作流，改用另一套 pip 接口；本模板没有这样做，以免破坏现有版本切换和打包。

## 添加依赖

前端：

~~~powershell
pnpm add <package>
pnpm add -D <dev-package>
~~~

后端：

~~~powershell
uv add --project backend <package>
uv add --project backend --dev <test-package>
~~~

仅提交 `package.json` 或 `backend/pyproject.toml` 及代码修改。
日志、缓存、`node_modules`、`.venv`、本地 uv 锁文件不进入 Git。

## 升级到兼容范围内的新版

~~~powershell
pnpm update
uv lock --project backend --upgrade
uv sync --project backend --group dev

pnpm test:backend
pnpm typecheck
pnpm build
~~~

如果某个最新版修改了最低 Node/Python 版本或导致接口不兼容，就停留在已验证的版本范围，**不要无条件执行 `pnpm up --latest` 并直接发布**。

目前建议以 Node.js 22 为开发基线；Python 声明支持 3.10 及以上，但对自己要支持的目标版本仍应逐一运行测试。更新框架主版本时先看 `vue-tsc`、TypeScript、Vite 和 Electron 的兼容性。

## 不使用 lock 文件的代价

此策略适合快速创建新项目和试用较新的兼容依赖；但需要知道：

- 同一提交在不同日期解析到的补丁/次版本，**可能不同**。
- 离线重新安装不一定成功；它依赖本机已有缓存。
- 只运行测试不能证明未来所有未发布/新版依赖都兼容。
- 有供应链、审计和严格可复现要求的正式项目，应考虑恢复仓库级 lock 文件、依赖审计及发布时产物归档。

模板的 Git Tag 只能固定**源码**，不保证不带锁文件时每次重新构建出的二进制完全一致；如果需要长期保存一个稳定发行版本，应同时归档当时通过测试的构建产物。

## 测试门槛

`quality.yml` 每次在 Windows 和 Linux 重新解析依赖，验证后端接口、类型检查；Windows 还构建独立 Python 与 Electron 绿色软件、执行 HTTP/WebSocket/菜单/进程清理的完整测试。

## uv 如何安装？

开发机无需预装 uv：由 `scripts/uv-bootstrap.mjs` 先执行 `uv self version`，缺失时自动下载官方 uv 二进制到被 Git 忽略的 `.tools/uv/`。详情见 [uv 自动引导](uv-bootstrap.md)。目标电脑只运行内置 Python，不依赖 uv。
