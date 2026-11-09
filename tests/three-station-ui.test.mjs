import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = file => fs.readFileSync(path.join(root, file), 'utf8')
const app = read('src/renderer/src/App.vue')
const service = read('src/renderer/src/services/station-profile.ts')
const stream = read('src/renderer/src/services/python-video.ts')
const consumer = read('src/renderer/src/composables/usePythonVideoStream.ts')
const backend = read('backend/src/sample_backend/services/video_stream.py')

test('calibration supports single and three-station mode, with per-position tabs', () => {
  assert.match(app, /chooseStationMode\('single'\)/)
  assert.match(app, /chooseStationMode\('auto'\)/)
  assert.match(app, /v-for="stage in STAGES"/)
  assert.match(app, /selectStation\(stage\)/)
  assert.match(app, /saveStationCalibration\(/)
  assert.match(app, /captureStationReference\(/)
  assert.match(app, /removeStationReference\(/)
  assert.ok(app.includes('(selectedStageConfig?.references.length ?? 0) >= 12'))
  assert.match(app, /stationProfile\?\.ready/)
  assert.match(app, /stationMode\.value === 'single'\) resetDraft\(\)/)
})

test('Python resolves the detected stage before canonical detector and exports reason', () => {
  assert.match(stream, /stage_mode: stageMode/)
  assert.match(consumer, /openPythonVideo\(filePath, calibration, Math\.max\(0, timeS\), stageMode\)/)
  assert.match(consumer, /'stage', 'position_confidence', 'position_reason'/)
  assert.match(backend, /self\._recognizer\.classify\(frame\)/)
  assert.match(backend, /return candidate, confidence, scores, 'POSITION_UNSTABLE'/)
  assert.match(backend, /'status': 'PAUSED', 'reason': reason/)
  assert.match(backend, /data = self\._detector\.process\(frame\)/)
  assert.doesNotMatch(read('backend/src/sample_backend/services/water_detection.py'), /ReferencePositionRecognizer/)
})

test('reference frame payload uses source path and Python seek rather than renderer JPEG', () => {
  assert.match(service, /'POST', '\/api\/stations\/reference'/)
  assert.match(service, /file_path: filePath, time_s: timeS/)
  assert.match(service, /minimum_references: number/)
  assert.match(read('backend/src/sample_backend/services/station_position.py'), /cv2\.imencode\('\.png', frame\)/)
})

test('calibration modal close button has an easy-to-hit target', () => {
  const style = read('src/renderer/src/styles/zebovision.css')
  const rule = style.match(/\.modal-close\{([^}]*)\}/)?.[1]
  assert.ok(rule, 'close button must have its own style')
  assert.match(rule, /(?:^|;)width:48px(?:;|$)/)
  assert.match(rule, /(?:^|;)height:48px(?:;|$)/)
  assert.match(rule, /(?:^|;)flex:0 0 48px(?:;|$)/)
  assert.match(style, /\.modal-close:hover\{[^}]*background:/)
  assert.match(app, /class="modal-close"[^>]*@click="closeCalibration"/)
})

test('P3 has independent nozzle A/B reference selectors for a shared ROI', () => {
  assert.ok(app.includes("selectedP3Nozzle = ref"))
  assert.ok(app.includes('喷头 A'))
  assert.ok(app.includes('喷头 B'))
  assert.ok(app.includes('captureStationReference(selectedStation.value, file, time, group)'))
  assert.ok(service.includes('group?: ReferenceGroup'))
  assert.ok(service.includes('time_s: timeS, group'))
  const backendStation = read('backend/src/sample_backend/services/station_position.py')
  assert.ok(backendStation.includes('MIN_REFS = 3'))
  assert.ok(backendStation.includes('scores[stage] = max(group_scores)'))
})
