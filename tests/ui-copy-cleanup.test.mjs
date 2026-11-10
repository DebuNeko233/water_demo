import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const app = readFileSync(path.join(root, 'src/renderer/src/App.vue'), 'utf8')

test('settings uses a recognizable toothed gear SVG instead of radial lines', () => {
  assert.match(app, /class="algorithm-gear"[^>]*aria-label="系统设置"/)
  const gear = app.match(/<button[^>]*class="algorithm-gear"[\s\S]*?<\/button>/)?.[0]
  assert.ok(gear, 'Settings button must exist')
  assert.match(gear, /<circle cx="12" cy="11\.5" r="3"\s*\/>/)
  assert.match(gear, /<path d="M9\.671 4\.136/)
  assert.doesNotMatch(gear, /M12 2v3M12 19v3/)
})

test('normal monitor UI omits redundant prose while preserving useful controls', () => {
  const removed = [
    'VISION INSPECTION', '● 已完成标注', '● 视频预览',
    'Python\/OpenCV 逐帧检测', '原算法 ·', '1.0×',
    '灰色虚线：晶圆边缘', '参考帧 {{ formatTime',
    '选择视频后标注晶圆位置',
  ]
  for (const phrase of removed) assert.ok(!app.includes(phrase), 'Redundant UI text: ' + phrase)
  for (const essential of [
    '标注晶圆位置', '重新标注', '打开视频', 'S_water', 'NG 阈值',
    '导出检测结果', '确认', '系统设置', 'videoError', 'calibrationPhase',
    '开始检测', '停止检测', '异常谱线', '视频参数',
  ]) assert.ok(app.includes(essential), 'Essential UI text missing: ' + essential)
  assert.match(app, /v-if="resultStatus === 'ERROR' \|\| resultStatus === '连接中' \|\| resultStatus === 'WARMUP' \|\| resultStatus === 'PAUSED'"/)
  assert.ok(!app.includes('S_water 历史曲线'))
  assert.ok(!app.includes('从头播放'))
  assert.ok(!app.includes('暂停显示'))
  assert.ok(!app.includes('暂停播放'))
  assert.ok(!app.includes('检测区域'))
  assert.ok(!app.includes('<div class="data-label">S_water</div>'))
  assert.ok(!app.includes('<div class="data-label">NG 阈值</div>'))
  assert.match(app, /<span>视频参数<\/span><strong :title="sourceLabel">\{\{ sourceLabel \}\}<\/strong>/)
})
