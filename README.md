# ZeboVision 湿法清洗检测系统

水流异常检测桌面应用（项目仓库 `water_demo`）。基于独立的 [Python + Electron + Vue 模板](https://github.com/DebuNeko233/python-electron-vue-template) 初始化，本仓库用于实际业务开发，不再向模板仓库提交业务改动。

## 当前功能（V3 前端）

- 选择本地视频文件，弹出晶圆位置标注模态框。
- 通过两次点击确定晶圆中心和边缘半径；可在标注时拖动进度条定位画面。
- 模态框右下角提供**重置**与**确认**；未完成两点标注时不能确认。
- 进入监测页后，支持视频播放、暂停、跳转、重新标注、替换视频。
- 在监测画面叠加晶圆 ROI 圆环（默认 0.65R–0.95R）与 24 个扇区，均随算法参数变化。
- 右侧采用原 `main1_chn.py` 的指标布局，包括状态、S_water、阈值、异常持续时间、异常扇区及历史曲线。
- 主界面右上角「本地视频」旁点击齿轮可配置 11 项算法参数，支持恢复默认、取消或保存并应用；数值跨应用重启保存在本机。保存后重新初始化检测会话，视频保持当前播放位置，结果重新 WARMUP。

**判断算法唯一基准：`main1_chn.py`。** `water_detection.py` 保留上传源码中 `DemoConfig`、`Calibration`、`WaterDetector` 的全部执行语句和默认值。新增 AST 指纹回归测试锁定其一致性，并使用相同 BGR 视频帧直接对比 Python API 与 `WaterDetector.process()` 的 `S_water`、扇区分数、状态和持续时间。**不得因网络/性能跳帧自动重置判定器**；只有用户明确更换视频、seek、重新标定或保存新设置才开启新会话。8 FPS 与全帧率输入不同，因此计算结果仍可能不同；原算法不允许自行调整。

**8 FPS 与原版一致性改进。** 浏览器现在在视频时间轴上按固定的 8 个时间区间/秒取帧；之前对 30 FPS 视频按 125 ms 滚动限流，会实际取到约 7.5 FPS。传送至 Python 的视频画面采用无损 PNG，而不是对 HTML 视频画面再次用 JPEG 质量 0.62 压缩；Python 仍逐帧使用原来的灰度转换、帧差、光照补偿、驻留和 OK/NG 判定。仍保留浏览器/FFmpeg 解码器像素可能存在少量差别，以及播放不及时时漏采样的限制。8 FPS 与原生全帧率的结果不应被承诺为相等。

**同源视频对照与初步参数标定。** 用以下命令对*同一个原始视频*逐帧运行原版算法，同时把相同的 OpenCV 解码帧按固定 8 FPS 时间区间抽样运行另一个未改动的算法实例。输出两种结果对照 CSV，并搜索较接近原始 S_water 时序的帧差阈值、驻留窗口和驻留比例候选值：

```powershell
uv run --project backend python backend/tools/compare_8fps.py --video good.mp4 --cx 264 --cy 443 --radius 108 --comparison-csv compare-good.csv --report-json calibration-good.json
```

上面中心/半径只是命令示例，需要填入用于该录像的实际标定值；脚本不会重新选择或修改 ROI。参考全帧率与 8 FPS 始终使用**同一解码视频帧和同一标定**，没有二次 JPEG 编码。报告中 `best_fit` 只是一段视频上的拟合候选，**不会自动覆盖设置窗口参数，也不会修改默认值**。要最终确定 NG 阈值，仍需分别使用已知正常与已知异常的原始视频验证误报/漏报率；只有 CSV 而没有原视频不能完成这个验证。

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
