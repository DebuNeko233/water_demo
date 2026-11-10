import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = name => fs.readFileSync(path.join(root, name), 'utf8')
const app = read('src/renderer/src/App.vue')
const playback = read('src/renderer/src/composables/usePythonVideoStream.ts')
const client = read('src/renderer/src/services/python-video.ts')
const api = read('backend/src/sample_backend/api/video.py')
const stream = read('backend/src/sample_backend/services/video_stream.py')

test('video parameter footer has only source, native size, and native FPS', () => {
  const footer = app.match(/<footer class="bottom-bar">[\s\S]*?<\/footer>/)?.[0]
  assert.ok(footer)
  assert.match(footer, /视频参数/)
  assert.match(footer, /\{\{ sourceLabel \}\}/)
  assert.match(footer, /\{\{ videoWidth \}\} × \{\{ videoHeight \}\}/)
  assert.match(footer, /\{\{ analysisFPS\.toFixed\(2\) \}\} FPS/)
  for (const label of ['原始分辨率', '原始帧率', '实际帧率', '显示', '处理']) {
    assert.ok(!footer.includes(label), 'Unrequested footer label: ' + label)
  }
})

test('four metric panel has no duplicated S_water threshold or detection region', () => {
  const dataPanel = app.match(/<section class="panel data-panel">[\s\S]*?<\/section>/)?.[0]
  assert.ok(dataPanel)
  for (const label of ['运行时间', '异常持续时间', '异常扇区', '扇区最大值']) {
    assert.ok(dataPanel.includes(label))
  }
  for (const label of ['>S_water<', '>NG 阈值<', '检测区域', 'sector-summary']) {
    assert.ok(!dataPanel.includes(label), 'Redundant data-panel content: ' + label)
  }
  assert.match(app, /<span class="panel-title">异常谱线<\/span>/)
  assert.ok(!app.includes('S_water 历史曲线'))
})

test('video playback buttons remain under the image and are independent of inference', () => {
  const imageControls = app.match(/<div class="video-footer"[\s\S]*?<\/section>/)?.[0]
  assert.ok(imageControls)
  assert.match(imageControls, /@click="togglePlay"/)
  assert.match(imageControls, /暂停播放/)
  assert.match(imageControls, /播放视频/)
  assert.match(imageControls, /暂停画面/)
  assert.match(imageControls, /继续画面/)
  assert.match(app, /if \(isPlaying\.value\) detection\.pause\(\)/)
  assert.match(app, /else detection\.play\(\)/)
  assert.doesNotMatch(imageControls, /@click="stopDetection"/)
})

test('start and stop buttons only control algorithm; video capture stays open', () => {
  const footer = app.match(/<footer class="bottom-bar">[\s\S]*?<\/footer>/)?.[0]
  assert.ok(footer)
  assert.match(footer, /@click="startDetection">▶ 开始检测/)
  assert.match(footer, /@click="stopDetection">■ 停止检测/)
  assert.match(footer, /导出检测结果/)
  assert.match(app, /await detection\.startDetection\(\)/)
  assert.match(app, /await detection\.stopDetection\(\)/)
  assert.match(app, /isDetecting\.value/)
  assert.match(playback, /async function startDetection\(\)/)
  assert.match(playback, /async function stopDetection\(\)/)
  assert.match(playback, /setPythonDetection\(sid, true\)/)
  assert.match(playback, /setPythonDetection\(sid, false\)/)
  assert.match(playback, /isDetecting\.value = state\.detecting/)
  assert.match(client, /'\/api\/video\/detection\/start'/)
  assert.match(client, /'\/api\/video\/detection\/stop'/)
  assert.match(api, /@router\.post\('\/detection\/start'\)/)
  assert.match(api, /@router\.post\('\/detection\/stop'\)/)
  assert.match(stream, /def set_detection\(self, session_id: str, enabled: bool\)/)
  assert.match(stream, /if not self\._detecting:/)
})
