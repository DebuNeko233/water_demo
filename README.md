# ZeboVision 湿法清洗检测系统

水流异常检测桌面应用（项目仓库 `water_demo`）。基于独立的 [Python + Electron + Vue 模板](https://github.com/DebuNeko233/python-electron-vue-template) 初始化，本仓库用于实际业务开发，不再向模板仓库提交业务改动。

## 当前功能（V3 前端）

- 选择本地视频文件，弹出晶圆位置标注模态框。
- 通过两次点击确定晶圆中心和边缘半径；可在标注时拖动进度条定位画面。
- 模态框右下角提供**重置**与**确认**；未完成两点标注时不能确认。
- 进入监测页后，支持视频播放、暂停、跳转、重新标注、替换视频。
- 在监测画面叠加晶圆 ROI 圆环（0.65R–0.95R）与 24 个扇区。
- 右侧采用原 `main1_chn.py` 的指标布局，包括状态、S_water、阈值、异常持续时间、异常扇区及历史曲线。

**水流检测已接入 Python。** 监测播放时，每秒从屏幕当前视频抽取至多 8 个解码帧，交由原始 `main1_chn.py` 的 `WaterDetector` 计算 `S_water`、OK/NG、异常持续时间、24 扇区分数；右侧曲线展示最近 5 秒数据。该版是实时**抽帧**分析，而不是完整视频的逐帧离线回放；低性能电脑可能进一步跳过帧，因此结果不能直接等同于原始 25/30 FPS 逐帧算法报告。跳转进度条、切换视频、重新标注会重新初始化时序窗口，显示 WARMUP 后再出 OK/NG。离线逐帧检测与自动三工位 ROI 切换尚未接入。
  
检测数据来自 Python，不使用模拟值；可以导出当前连续检测段的 CSV。若 Python 服务未连接，界面会提示错误，数据不再假装为正常。

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
- `backend/src/sample_backend/services/water_detection.py`：从用户原始 `main1_chn.py` 提取的 WaterDetector 算法。
- `backend/src/sample_backend/services/water_session.py`：单视频检测会话、帧顺序与进度条跳转重置。
- `backend/src/sample_backend/api/detection.py`：`/api/detection/start`、`/api/detection/frame`。
- `src/renderer/src/composables/useWaterDetection.ts`：逐帧采样、请求调度与同步 UI。
- `backend/`：FastAPI 检测服务（保留模板自带的示例 API）。

模板的开发与打包原理仍可参考 `docs/` 中的技术文档。
