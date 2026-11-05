# 前后端目录与扩展示例

本模板采用 **按职责分层、避免空目录与多余框架** 的结构。实际示例已经接通三种通信方式。

## 目录

```text
src/
├─ main/                        # Electron 主进程：窗口、进程、IPC
├─ preload/                     # 暴露受限 API
├─ shared/bridge.ts             # 跨 Electron / Vue 的类型
└─ renderer/src/
   ├─ App.vue                   # 只装配导航与页面
   ├─ views/HomeView.vue        # 组装首页
   ├─ components/               # 页面中的独立功能块
   │  ├─ EchoDemo.vue           # HTTP 调用示例
   │  ├─ TaskDemo.vue           # 任务和 WebSocket 状态
   │  ├─ DesktopDemo.vue        # IPC 调用示例
   │  ├─ EventLog.vue           # WebSocket 事件显示
   │  ├─ BackendNotice.vue      # 后端异常诊断与重连
   │  └─ AppSidebar.vue
   ├─ composables/              # 可复用的 Vue 状态与订阅
   │  ├─ useBackendConnection.ts
   │  └─ useBackendEvents.ts
   ├─ services/                 # 与 Python / Electron 交互
   │  ├─ backend-api.ts
   │  └─ desktop.ts
   └─ styles/main.css

backend/
├─ .python-version
├─ pyproject.toml
├─ uv.lock
├─ src/sample_backend/
│  ├─ __main__.py               # Python 进程入口
│  ├─ main.py                   # 创建应用、连接模块、生命周期
│  ├─ api/                      # HTTP、WebSocket、控制接口
│  │  ├─ routes.py
│  │  ├─ websocket.py
│  │  └─ control.py
│  ├─ services/                 # Python 业务逻辑和任务
│  │  ├─ demo_jobs.py
│  │  └─ event_hub.py
│  └─ core/                     # 基础配置与日志
│     ├─ config.py
│     └─ logging.py
└─ tests/                       # pytest 回归测试
```

## 职责约定

| 要做的事 | 放在哪里 |
| --- | --- |
| 完整的新页面 | `views/` |
| 复用的 UI、业务面板 | `components/` |
| Vue 响应式状态和订阅清理 | `composables/` |
| Python 的 HTTP 调用 | `services/backend-api.ts` |
| 原生窗口/文件等系统功能 | `src/main/` + `src/preload/` + `services/desktop.ts` |
| 新的 Python HTTP 接口 | `backend/src/sample_backend/api/routes.py` |
| 后台任务、相机、算法等业务 | `backend/src/sample_backend/services/` |
| 环境变量、存储目录和日志 | `backend/src/sample_backend/core/` |
| Python 回归测试 | `backend/tests/` |

目前只有一个页面，所以不默认安装 vue-router；状态并不复杂，也不需要 Pinia。
未来有真实路由或跨页面状态需求时，再引入即可。

## 示例：新增一个 HTTP 接口

在 `backend/src/sample_backend/api/routes.py` 加：

```python
class SumInput(BaseModel):
    left: int
    right: int


@router.post("/sum")
async def sum_numbers(payload: SumInput) -> dict:
    return {"result": payload.left + payload.right}
```

在 `src/renderer/src/services/backend-api.ts` 加：

```ts
export function sumNumbers(left: number, right: number): Promise<{ result: number }> {
  return window.desktop.backend.request('POST', '/api/sum', { left, right })
}
```

然后在 Vue 组件里调用 `sumNumbers`。无需手动处理端口或鉴权，也不要让组件直接访问 Node.js。

## 示例：从 Python 推送事件

在 Python 路由或业务方法中获取应用事件中心：

```python
await request.app.state.events.publish(
    "device.state",
    {"connected": True, "name": "Demo device"},
)
```

在 Vue 中使用 `useBackendEvents()` 读取事件，或者通过 `window.desktop.backend.onEvent`
订阅，卸载时调用其返回的取消订阅函数。

任务最终状态仍然应该通过 HTTP 查询。WebSocket 可以断线，不保证每条历史事件都能重放。

## 示例：增加 Electron IPC

添加系统能力时按以下顺序编辑：

1. 在 `src/main/index.ts` 注册受限 IPC，校验发送页面。
2. 在 `src/preload/index.ts` 暴露最小的方法。
3. 在 `src/shared/bridge.ts` 定义 TypeScript 接口。
4. 在 `src/renderer/src/services/desktop.ts` 封装，供 Vue 组件调用。

不要在 Renderer 打开 `nodeIntegration` 或暴露整个 `ipcRenderer`。

## 保持简单

**页面负责组装、组件负责交互、组合式函数负责订阅、服务负责 API。**
Python 路由应短小，复杂业务放在 `services/`。
不为了目录好看而增加无用的空文件、自动注册框架或过早抽象。

## 下一步学习

- [上手和启动](getting-started.md)
- [真实通信流程](communication.md)
- [完整业务扩展](extend-features.md)
- [打包和依赖定制](customization.md)
- [排错手册](troubleshooting.md)

## 依赖管理

模板不提交 pnpm 或 uv 的 lock 文件。请按 [依赖管理指南](dependencies.md) 中的版本范围与兼容性流程更新依赖。
