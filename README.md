# ZeboVision 湿法清洗检测系统

水流异常检测桌面应用（项目仓库 `water_demo`）。基于独立的 [Python + Electron + Vue 模板](https://github.com/DebuNeko233/python-electron-vue-template) 初始化，本仓库用于实际业务开发，不再向模板仓库提交业务改动。

## 当前功能（V3 前端）

- 选择本地视频文件，弹出晶圆位置标注模态框。
- 通过两次点击确定晶圆中心和边缘半径；可在标注时拖动进度条定位画面。
- 模态框右下角提供**重置**与**确认**；未完成两点标注时不能确认。
- 进入监测页后，支持视频播放、暂停、跳转、重新标注、替换视频。
- 在监测画面叠加晶圆 ROI 圆环（0.65R–0.95R）与 24 个扇区。
- 右侧采用原 `main1_chn.py` 的指标布局，包括状态、S_water、阈值、异常持续时间、异常扇区及历史曲线。

**当前为前端阶段。** 本地视频播放与标注已实现，但 `main1_chn.py` 的真实水流检测算法尚未接入 Python 服务；异常值与历史曲线不伪造实时结果，导出按钮在接入算法前不可用。后端目前仍保留模板的 `sample_backend` 包与示例 API，供下一阶段集成。

## 本地运行

Windows x64，Node.js 22+，pnpm：

```powershell
git clone https://github.com/DebuNeko233/water_demo.git
cd water_demo
pnpm install
pnpm dev
```

仅启动前端：`pnpm dev:frontend`；仅启动 Python：`pnpm dev:backend`；运行类型检查：`pnpm typecheck`。

## 打包

```powershell
pnpm build
```

Windows 绿色程序输出在 `dist/win-unpacked/`，执行 `ZeboVision.exe`。发布时应复制完整目录（包含 Python 运行时），而不是只复制 EXE。

## 代码位置

- `src/renderer/src/App.vue`：V3 页面与标定交互。
- `src/renderer/src/styles/zebovision.css`：工业监控界面样式。
- `src/main/index.ts`、`src/preload/index.ts`、`src/shared/bridge.ts`：Electron 窗口及安全 IPC。
- `backend/`：预留的 FastAPI 检测服务位置。

模板的开发与打包原理仍可参考 `docs/` 中的技术文档。
