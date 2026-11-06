# ZeboVision 湿法清洗检测系统

水流异常检测桌面应用（项目仓库 `water_demo`）。基于独立的 [Python + Electron + Vue 模板](https://github.com/DebuNeko233/python-electron-vue-template) 初始化，本仓库用于实际业务开发，不再向模板仓库提交业务改动。

## 当前功能（Python 视频引擎 + Electron 显示界面）

- 选择本地视频文件，弹出晶圆位置标注模态框。
- 通过两次点击确定晶圆中心和边缘半径；可在标注时拖动进度条定位画面。
- 模态框右下角提供**重置**与**确认**；未完成两点标注时不能确认。
- 进入监测页后，**Python/OpenCV 打开原始本地视频并按源 FPS 逐帧推理**；支持播放、暂停、跳转、重新标注、替换视频。
- **Python 在判定后绘制图像**（原版圆环、扇区、持续异常像素红色区域）；Electron 接收处理过的图像，与对应的数值同步显示。
- 右侧采用原 `main1_chn.py` 的指标布局，包括状态、S_water、阈值、异常持续时间、异常扇区及历史曲线。
- 主界面右上角「本地视频」旁点击齿轮可配置 11 项算法参数，支持恢复默认、取消或保存并应用；数值跨应用重启保存在本机。保存后重新初始化检测会话，视频保持当前播放位置，结果重新 WARMUP。

**判断算法唯一基准：`main1_chn.py`。** `water_detection.py` 保留上传源码中 `DemoConfig`、`Calibration`、`WaterDetector` 的全部执行语句和默认值。在仓库测试夹具中保留用户上传的完整原始 `main1_chn.py`，自动化测试在同一 Python 运行时直接对比三个类的 AST，锁定其可执行逻辑，并使用相同 BGR 视频帧直接对比 Python API 与 `WaterDetector.process()` 的 `S_water`、扇区分数、状态和持续时间。**不得因网络/性能跳帧自动重置判定器**；只有用户明确更换视频、seek、重新标定或保存新设置才开启新会话。8 FPS 与全帧率输入不同，因此计算结果仍可能不同；原算法不允许自行调整。

**8 FPS 与原版一致性改进。** 浏览器现在在视频时间轴上按固定的 8 个时间区间/秒取帧；之前对 30 FPS 视频按 125 ms 滚动限流，会实际取到约 7.5 FPS。传送至 Python 的视频画面采用无损 PNG，而不是对 HTML 视频画面再次用 JPEG 质量 0.62 压缩；Python 仍逐帧使用原来的灰度转换、帧差、光照补偿、驻留和 OK/NG 判定。仍保留浏览器/FFmpeg 解码器像素可能存在少量差别，以及播放不及时时漏采样的限制。8 FPS 与原生全帧率的结果不应被承诺为相等。

**同源视频对照与初步参数标定。** 用以下命令对*同一个原始视频*逐帧运行原版算法，同时把相同的 OpenCV 解码帧按固定 8 FPS 时间区间抽样运行另一个未改动的算法实例。输出两种结果对照 CSV，并搜索较接近原始 S_water 时序的帧差阈值、驻留窗口和驻留比例候选值：

```powershell
uv run --project backend python backend/tools/compare_8fps.py --video good.mp4 --cx 264 --cy 443 --radius 108 --comparison-csv compare-good.csv --report-json calibration-good.json
```

上面中心/半径只是命令示例，需要填入用于该录像的实际标定值；脚本不会重新选择或修改 ROI。参考全帧率与 8 FPS 始终使用**同一解码视频帧和同一标定**，没有二次 JPEG 编码。报告中 `best_fit` 只是一段视频上的拟合候选，**不会自动覆盖设置窗口参数，也不会修改默认值**。要最终确定 NG 阈值，仍需分别使用已知正常与已知异常的原始视频验证误报/漏报率；只有 CSV 而没有原视频不能完成这个验证。

**视频与检测的唯一数据流：**

```text
用户选择本地视频 → 标注晶圆 ROI（前端预览）
      ↓ 确认标定和磁盘文件路径
Python cv2.VideoCapture(video_path)
      ↓ 原视频每一帧 BGR（源 FPS，如 30 FPS）
原始 main1_chn.py 的 WaterDetector.process(frame)
      ↓ 同一帧：状态 + S_water + 异常持续时间 + 扇区数值
Python 绘制圆环/扇区/持续扰动区域 → JPEG 仅压缩可视化图像
      ↓ 本机逐帧、单请求背压的 HTTP /api/video/next
Electron 统一更新图像和检测数值、趋势曲线
```

**算法保持原版。** 监控视频不再由前端解码并以 PNG/JPEG 传回 Python；OpenCV 原帧直接送入 `WaterDetector.process()`。Python 传给前端的有损 JPEG 是*已经推理并标注完毕的显示结果*，不会参与判定。检测器按**视频真实原始帧率**执行，驻留帧数与 NG/OK 计时恢复为与原始 `main1_chn.py` 的原视频检测方式一致。只要源文件、标定和参数相同，输出可逐帧对照；内置一致性测试保证 WaterDetector 源码未变。

**交互方式。** 前端选文件后只在标定弹窗用 HTMLVideoElement 预览，确认标定时将受控 Preload 取得的本地文件路径传给 Python。Python /api/video/open 返回视频元信息与首帧；前端依次请求 /api/video/next，每个响应都同时包含注释后的图片和对应的判定数值，绝不单独异步刷新两者。播放速度尽量按源 FPS 调度；如果 CPU/IPC 处理不及，会降低实际播放速度而不是跳过算法输入。暂停不再请求新帧；主动 seek 或修改参数时由 Python 重新打开时序窗口。Electron 关闭时 Python 释放 VideoCapture。

**兼容说明。** 旧的 `/api/detection/frame` 仍保留做单帧 API 的回归测试/兼容用途，但监测主界面不调用它。之前的 8 FPS 对照工具仍可用于离线实验，但不影响现在线上使用的原版全帧率算法。 

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
- `backend/src/sample_backend/services/water_session.py`：旧单帧检测桥接（兼容与回归测试用）。
- `backend/src/sample_backend/services/video_stream.py`：Python 全帧率视频读取、检测和图像/指标原子输出。
- `backend/src/sample_backend/services/frame_renderer.py`：原始脚本判定后的显示绘制（不影响判定）。
- `backend/src/sample_backend/api/video.py`：`/api/video/open`、`/api/video/next`、`/api/video/seek`。
- `backend/src/sample_backend/api/detection.py`：`/api/detection/start`、`/api/detection/frame`。
- `src/renderer/src/composables/usePythonVideoStream.ts`：Python 图像流展示、帧背压与播放控制。
- `backend/`：FastAPI 检测服务（保留模板自带的示例 API）。

模板的开发与打包原理仍可参考 `docs/` 中的技术文档。
