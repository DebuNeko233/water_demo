# 如何把样例定制成自己的桌面软件

建议先保留底层 `BackendManager`、IPC、Python 包名不变，只修改业务页面和应用外观。
当前**没有项目重命名向导**，所以改名时必须考虑多个来源。

## 修改应用名称与发行文件名

| 目标 | 文件 |
| --- | --- |
| npm 包标识与前端版本 | `package.json` 的 `name` / `version` |
| Electron 产品名、App ID | `electron-builder.yml` 的 `productName` / `appId` |
| 页面和导航显示文本 | `src/renderer/index.html`、`components/AppSidebar.vue` |
| 示例项目的文字介绍 | `README.md`、相关页面/文档 |

`productName` 改动会改变 EXE 名称，而目前部分 Windows smoke 脚本
（`scripts/smoke/electron.mjs` 和 `scripts/smoke/parent-exit.mjs`）
按 `SampleApp.exe` 查找发行文件；更名后必须同步修改这些脚本和 README。
`appId` / 应用名的变化也可能改变 Windows 的用户数据目录。
不要把持久业务数据放到 `dist/win-unpacked` 中。

**谨慎修改 Python 包名** `sample_backend`：目前 `backend/pyproject.toml`、
`__main__.py` 的 uvicorn 入口、`src/main/backend-manager.ts` 的启动参数、
smoke 测试都依赖这个模块名。业务项目通常无须修改内部模块名，
更改软件显示名称就够了。

## 加 Python 依赖

编辑 `backend/pyproject.toml` 的 `dependencies`，然后在根目录运行：

~~~powershell
uv lock --project backend --upgrade
uv sync --project backend
pnpm test:backend
pnpm build
~~~

只需要提交 `backend/pyproject.toml`；本地自动生成的 `backend/uv.lock` 被 Git 忽略。
不要复制开发 `.venv`。`pnpm build` 根据兼容版本范围装配正式依赖并构建独立 CPython 运行时。
详细策略见 [依赖管理](dependencies.md)。

如果包包含原生 DLL、GPU、OpenCV/PyTorch 或硬件 SDK，
还需检查资源装配、第三方许可证以及无开发环境 Windows 电脑的实际运行情况。

## 修改 Python 版本

建议通过 `pnpm python:use 3.11` 切换；它会删除整个旧 `backend/.venv`
并重建，不影响 uv 的用户级解释器缓存。
当前版本声明 `backend/pyproject.toml` 中的 `requires-python`
只是兼容范围，不表示所有第三方依赖都支持其中每个 Python 版本。

## 加业务资源、配置、模型文件

- 源码中的业务资源可放在业务目录，使用相对模块位置获取资源。
- 发行资源若不属于 Python Package，请明确在 `electron-builder.yml`
  或 `scripts/build.mjs` 中组装，再提供统一路径获取方法。
- 数据库、日志、运行时配置、用户选择的模型输出不应写入只读安装资源目录。
  正式环境数据根目录由 `APP_DATA_DIR` 指向 Electron 用户数据目录。
- 不要硬编码 `C:\Users\某用户` 或依赖当前工作目录。

## 何时引入新框架？

- 少量页面：继续使用 `navigation.ts` 的当前选项卡导航；
  确有 URL、嵌套路由、历史导航时才考虑 vue-router。
- 少量 Vue 状态：使用 `composables/`；
  多页面复杂状态共享时再考虑 Pinia。
- 需要持久化：先明确数据模型、迁移、备份与路径，再引入数据库。
- 相机与硬件：业务模块负责生命周期、安全停机；不要让 Electron
  的超时强杀成为实际设备的唯一保护机制。

## 发布验收顺序

1. `pnpm test:backend` 和 `pnpm typecheck`。
2. Windows `pnpm build`。
3. Python HTTP / WebSocket / 任务 / Electron IPC 全部实际工作。
4. 正常退出和强制结束 Electron 后 Python 没有残留。
5. 复制**整个** `dist/win-unpacked` 到另一目录运行。
6. 正式发布前优先在没有安装 Python/Node 的离线 Windows 电脑做手工验收。

CI 能验证模板当前依赖的烟雾路径，但不保证任意新 SDK、硬件或模型都能工作。
