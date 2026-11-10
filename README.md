# ZeboVision 湿法清洗检测系统

水流异常检测桌面应用（项目仓库 `water_demo`）。基于独立的 [Python + Electron + Vue 模板](https://github.com/DebuNeko233/python-electron-vue-template) 初始化，本仓库用于实际业务开发，不再向模板仓库提交业务改动。

## 当前功能（Python 视频引擎 + Electron 显示界面）

- 管理员在「系统设置」中切换 **检测参数 / 视频源 / 设备配置** 三个 Tab；视频源支持本地文件、RTSP 网络摄像头和 USB 摄像头（USB 设备编号 0～15）。
- 本地视频保留播放进度条、5 秒跳转和从头播放；RTSP/USB 使用实时画面，**不显示进度条、前后跳转、从头播放**。实时检测由 Python 后台连续读取并计算，每次只给界面传最新一帧；暂停显示不停止后台摄像头推理。
- RTSP/USB 的晶圆 ROI 由管理员使用「刷新画面」抓拍现场画面标注；采集 P1/P2/P3 参考帧时保存原始 OpenCV PNG，不经浏览器 JPEG 截图。单工位 ROI 也会持久保存，跨重启复用。
- 管理员在「系统设置 → 视频源 → 本地视频」点击「浏览…」选择文件，设置页显示完整视频路径，保存后跨软件重启保留；监测页只负责「打开视频」。首次使用没有标定时，由管理员打开标定窗口。
- 标定窗口支持「单工位」与「三工位自动」：三工位分别选择 P1/P2/P3，标注晶圆中心/半径，并从视频不同时间点采集各至少 **3 张**参考帧（最多 12 张）。每个工位的 ROI 和参考截图保存在本机设备配置目录，跨重启复用。
- 三工位完整配置之前无法开始自动检测；参考图像由 Python/OpenCV 原帧无损保存，前端只操作视频时间与标定点。
- 管理员可在「标注晶圆位置」窗口导入或导出设备配置 ZIP（P1/P2/P3 ROI、参考截图、P3 喷头 A/B 分组、管理员批准的水流判定参数）；管理员密码、认证令牌和原始视频**不会**写入 ZIP。导入前先校验全部文件，失败时保留原有配置；导入成功会停止旧检测会话，重新确认标定后再运行。
- 单工位保持原有两次点击标注与「确认」流程；可拖动进度条定位画面。
- 监测页使用已保存的视频源，**Python/OpenCV 按源 FPS 逐帧检测**。本地视频支持播放、暂停和跳转；更换文件需到管理员视频源设置中选择新路径。标定画面由 Python 按进度条时间取帧，软件重启后仍能重新标注。
- **Python 在判定后绘制图像**（原版圆环、扇区、持续异常像素红色区域）；Electron 接收处理过的图像，与对应的数值同步显示。
- 右侧采用原 `main1_chn.py` 的指标布局，包括状态、S_water、阈值、异常持续时间、异常扇区及历史曲线。
- 默认以**操作员**身份启动，可打开管理员已保存的视频源、播放、暂停及导出结果；不能选择其他本地视频、重新标注或修改参数。设备首次部署或缺少可用标定时，须切换管理员完成设置。
- 点击右上角「操作员」可以切换管理员：首次使用须设置至少 8 位管理员密码，之后通过密码登录；管理员可重新标注晶圆位置、保存 P1/P2/P3 ROI、增删 P3 双喷头参考帧及修改齿轮里的算法参数。点击「管理员」退出身份并返回操作员。
- 管理员批准的算法设置由 **Python 后端保存并强制应用**，跨应用重启保留；操作员运行视频时始终使用管理员最后保存的参数。保存时当前视频位置保持，历史记录重新预热。

**视频源设置。** 登录管理员 → 右上角齿轮「系统设置」→「视频源」→ 选「本地视频 / RTSP 摄像头 / USB 摄像头」；本地视频通过「浏览…」选择并显示完整路径，摄像头输入 `rtsp://...` 地址或 USB 编号并保存。返回监测页点击「连接摄像头」。操作员不能修改源地址，只能连接管理员已保存的源。USB 摄像头优先尝试 Windows DirectShow、失败时使用 OpenCV 默认设备后端；RTSP 优先 FFmpeg，失败后回退默认后端。摄像头设备、解码器和网络连接需要在实际机器上验证。RTSP 链接可能含密码，保存于应用数据目录 `video/source.json`（按用户权限保护），**不包含在设备配置 ZIP 中**，不要公开此文件。浏览界面、操作员配置查询和导出文件都不暴露 RTSP 地址及密码。

**实时视频工作方式。** 摄像头输出的尺寸必须与所用晶圆 ROI 一致；不同摄像头或改变分辨率后，管理员需要重新标注。实时源的帧率优先读取摄像头报告值，无法获取时使用 30 FPS 作为统计兜底值。实时视频没有总时长或 seek，前端显示当前监测时间及 LIVE 状态，播放/暂停仅决定是否刷新显示；Python 持续处理解码帧，避免暂停时积压旧画面。连接断开时显示错误，点击「重新连接」重新打开；设备长期在线和复杂网络断流重连仍需做实机压力测试。摄像头自身丢帧、解码器性能或 FPS 报告不准确可能影响基于时间的水流指标，不能把模拟测试作为实机准确率证明。

**标定文件位置与备份。** Windows 打包版 Python 的 APP_DATA_DIR 为 Electron `app.getPath('userData')/data`，ZeboVision 正式版通常是 `%APPDATA%\\ZeboVision\\data`。三个 ROI 和单工位标定保存在 `stations/profile.json`，无损参考帧是同目录的 `*.png`；已批准的水流判定参数保存在 `users/admin.json`（同时包含管理员密码哈希，因此不要手动在设备间复制此文件）。开发版默认使用 `%USERPROFILE%\\.python-electron-vue-sample`，如设置 `APP_DATA_DIR` 则以该值为准。导入、导出都需要管理员登录，导入会覆盖当前的三工位标定与算法参数，但**不会改动本机管理员密码**。不要直接复制单独的 JSON 文件，建议使用界面里的 ZIP 备份。ZIP 的格式版本为 1，含 `manifest.json`、`stations/profile.json`、`stations/references/*.png`、`detector/settings.json`；不包含视频源、检测历史或登录凭据。

**重新标注管理员权限：** 监测页的「重新标注」按钮只对管理员显示。操作员打开管理员配置的视频源时，自动使用已保存的单工位标定或完整三工位标定；如果尚无可用标定，会提示切换管理员。管理员退出登录时标定窗口立即关闭。后端 `POST /api/stations/calibration`、`/api/stations/reference`、`/api/stations/reference/remove` 均须有效管理员令牌，直接调用接口也不能越权修改设备保存的 ROI 或参考帧。现有 `GET /api/stations/profile` 允许操作员读取配置，以便复用。所选视频分辨率与标定不一致时，Python 会提示管理员重新标定。

**用户权限与密码。** 管理员密码只在本机首次切换时设置，无固定默认密码；后端用随机盐和 PBKDF2-SHA256 保存密码哈希到应用数据目录 `users/admin.json`，不会以明文保存在前端。管理员认证令牌仅保存在当前页面内存，软件/后端重启后自动恢复操作员。连续输错密码会短暂锁定登录。忘记密码时需要由有本机文件访问权限的人在退出软件后备份并删除 `users/admin.json`，**这也会清空管理员已保存的算法参数**；重新进入管理员时重新设置。该功能为本机使用权限管理，不替代操作系统文件保护与企业级身份认证。

**三工位自动识别流程：** 在标定窗口选「三工位自动」→ 点 P1，暂停至晶圆位于 P1 的清晰画面，两次点击中心与边缘，点「保存 ROI 并采集当前帧」；拖动进度条至另外至少 2 个明显不同的画面（尽量覆盖喷头不同位置）继续采集。按相同方式完成 P2 和 P3，各不少于 3 张，最后点「确认」。以后相同设备及分辨率的录像可复用已保存的 3 个工位配置；如果画面分辨率变化，必须重新标定和采集。确认后监测页会标明当前识别的工位，CSV 新增 `stage`、`position_confidence`、`position_reason`。其中 `PAUSED` 表示位置未知或仍在连续确认，不属于 OK/NG。

**P3 双喷头：** P3 的晶圆中心/半径只标定一次，在 P3 工位下切换「喷头 A / 喷头 B」分别采集参考帧；每组至少 3 张（一个工位最多保存 12 张）。识别时每组单独计算参考帧相似度中位数，P3 取分数更高的完整组，再与 P1/P2 比较。原有 P3 参考帧自动归入喷头 A，不会被清除。若喷头 B 已开始采集却不足 3 张，暂时不能确认自动检测，以免误以为喷头 B 已就绪；未配置喷头 B 的旧设备仍可只用喷头 A。两组喷头不改变水流算法或 P3 ROI。两种喷头外观需使用实际录像验证，不能仅靠增加截图保证识别率。

**工位判定阈值：** 管理员点击右上角齿轮，在「工位识别」中设置「工位判定阈值」。默认 0.78，可调整 0.50～0.99；阈值越高越严格、越容易出现 UNKNOWN，阈值越低越容易通过但误判风险增加。P1/P2/P3 及 P3 双喷头使用相同阈值，仍须高于次优工位至少 0.035，连续 3 帧确认。此参数和水流检测的 S_water 异常阈值互不影响；保存后在当前播放位置重新开始识别/预热。阈值由 Python 持久保存，并包含在设备配置 ZIP 中；导入旧版 ZIP 缺少该字段时使用默认值 0.78。

**位置识别与原算法的边界：** 参考 [water_detector](https://github.com/DebuNeko233/water_detector) 的 `PositionRecognizer`，使用灰度 Sobel 边缘图与参考图比较；采用喷头外观分组后的组内多帧中位数、动态边缘降权和三个 ROI 并集空间加权。只有最高分不低于管理员设置的工位判定阈值（默认 0.78）且高于次优至少 0.035，连续 3 帧匹配同一位置，才允许使用该位置的 ROI。否则跳过当前帧的水流判定，输出 `PAUSED`；工位切换时重建该工位检测器，恢复 `WARMUP`。默认阈值 0.78、固定差值 0.035 与连续 3 帧仍是待实机验证的初值，不能当作已经验证的准确率。**`main1_chn.py` 的 `WaterDetector.process()` 和阈值完全不变。**

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
- `backend/src/sample_backend/services/station_position.py`：P1/P2/P3 校准数据、原始 PNG 参考帧持久化、保守位置相似度判断。
- `backend/src/sample_backend/api/stations.py`：`/api/stations/profile`、`/api/stations/calibration`、`/api/stations/reference`、`/api/stations/reference/remove`。
- `src/renderer/src/services/station-profile.ts`：三个工位的前后端类型与配置 API。
- `backend/src/sample_backend/services/frame_renderer.py`：原始脚本判定后的显示绘制（不影响判定）。
- `backend/src/sample_backend/api/video.py`：`/api/video/open`、`/api/video/next`、`/api/video/seek`。
- `backend/src/sample_backend/api/detection.py`：`/api/detection/start`、`/api/detection/frame`。
- `src/renderer/src/composables/usePythonVideoStream.ts`：Python 图像流展示、帧背压与播放控制。
- `backend/`：FastAPI 检测服务（保留模板自带的示例 API）。

模板的开发与打包原理仍可参考 `docs/` 中的技术文档。
