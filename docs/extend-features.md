# 实战：新增一个 Vue ↔ Python 功能

这是可复制的练习：为模板新增“反转文字”，覆盖 Python Service、FastAPI、前端类型化请求、Vue 组件与自动化测试。

## 1. Python Service

新建 `backend/src/sample_backend/services/text_tools.py`：

~~~python
"""Simple text operations independent of FastAPI and Electron."""


def reverse_text(value: str) -> str:
    return value[::-1]
~~~

业务逻辑不需要依赖 Web 框架，便于单独测试和替换。

## 2. HTTP API

编辑 `backend/src/sample_backend/api/routes.py`。
此文件已导入 `BaseModel`、`Field`、`router`；追加以下代码：

~~~python
from ..services.text_tools import reverse_text


class ReverseInput(BaseModel):
    text: str = Field(min_length=1, max_length=200)


@router.post("/text/reverse")
async def reverse_text_api(payload: ReverseInput) -> dict:
    return {"reversed": reverse_text(payload.text)}
~~~

注意：路由现有前缀 `/api`，完整接口是 `POST /api/text/reverse`，
不需要新建 FastAPI 应用或另起端口。

## 3. TypeScript API

在 `src/renderer/src/services/backend-api.ts` 追加：

~~~ts
export interface ReverseResult {
  reversed: string
}

export function reverseText(text: string): Promise<ReverseResult> {
  return window.desktop.backend.request<ReverseResult>(
    'POST',
    '/api/text/reverse',
    { text },
  )
}
~~~

它经过 Preload 和 Electron Main，发行版自动处理端口和会话认证。
不要在 Vue 中硬编码端口。

## 4. Vue 组件

新建 `src/renderer/src/components/ReverseDemo.vue`：

~~~vue
<script setup lang="ts">
import { ref } from 'vue'
import { reverseText } from '../services/backend-api'

defineProps<{ ready: boolean }>()

const input = ref('Hello')
const result = ref('')
const error = ref('')

async function submit(): Promise<void> {
  error.value = ''
  try {
    const response = await reverseText(input.value)
    result.value = response.reversed
  } catch (caught) {
    error.value = String(caught)
  }
}
</script>

<template>
  <section class="card">
    <div class="panel-heading">
      <h2>反转文字</h2><span>POST /api/text/reverse</span>
    </div>
    <label for="reverse-input">请输入文字</label>
    <div class="input-row">
      <input id="reverse-input" v-model="input" maxlength="200" />
      <button :disabled="!ready || !input" @click="submit">反转</button>
    </div>
    <p class="result">{{ result }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
~~~

编辑 `src/renderer/src/views/HomeView.vue`：

先在 Script 的 import 区增加：

~~~ts
import ReverseDemo from '../components/ReverseDemo.vue'
~~~

在已有 `EchoDemo` 标签后添加：

~~~vue
<ReverseDemo
  v-show="activePage === 'overview' || activePage === 'http'"
  :ready="status === 'ready'"
/>
~~~

这样“应用概览”和“HTTP 示例”都会显示新功能，
不需要修改主进程、Preload、Python 启动器或打包器。

## 5. 自动化测试与运行

在 `backend/tests/test_api.py` 添加：

~~~python
def test_reverse_text():
    with TestClient(app) as client:
        response = client.post("/api/text/reverse", json={"text": "ABC"})
        assert response.status_code == 200
        assert response.json() == {"reversed": "CBA"}
~~~

依次执行：

~~~powershell
pnpm test:backend
pnpm typecheck
pnpm dev
~~~

在 HTTP 页面输入 `Hello`，结果应为 `olleH`。
最后在 Windows 上执行 `pnpm build` 并验证移动后的绿色目录。

## 扩展到其他业务

- 新任务：复制 `services/demo_jobs.py` 的取消、状态查询和事件推送模式。
- 新事件：由 `EventHub.publish` 发送，并通过前端 `useBackendEvents()` 订阅；重要最终状态应另提供 HTTP 查询。
- 新页面：在 `navigation.ts` 增加页面 ID，并在 `HomeView.vue` 展示；当前没有 vue-router。
- 新 IPC：修改 `src/main/index.ts`、`src/preload/index.ts`、`src/shared/bridge.ts` 和 `services/desktop.ts`，保留来源校验。
- 新依赖：改 `backend/pyproject.toml`，同步并提交 `backend/uv.lock`，重新构建。

**常见错误**：组件里直接请求开发端口、把所有业务写在 HTTP 路由、
仅复制 exe、未更新测试或只依赖丢包后不可重放的 WebSocket 事件。
