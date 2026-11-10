import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describeVideoOpenError } from '../src/renderer/src/utils/video-open-error.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

test('resolution mismatch tells operator the actual and annotated sizes', () => {
  const issue = {
    detail: {
      code: 'CALIBRATION_RESOLUTION_MISMATCH',
      video_width: 1920, video_height: 1080,
      calibration_width: 640, calibration_height: 480,
    },
  }
  const response = describeVideoOpenError(
    new Error('Python API 422: ' + JSON.stringify(issue)))
  assert.equal(response.kind, 'mismatch')
  assert.match(response.message, /1920×1080/)
  assert.match(response.message, /640×480/)
  assert.match(response.message, /重新标注/)
})

test('oversize is not mistaken for an issue fixable by ROI re-annotation', () => {
  const response = describeVideoOpenError(
    new Error('Python API 422: ' + JSON.stringify({
      detail: {code: 'VIDEO_RESOLUTION_TOO_LARGE', video_width: 3840, video_height: 2160},
    })))
  assert.equal(response.kind, 'oversize')
  assert.match(response.message, /3840×2160/)
  assert.doesNotMatch(response.message, /重新标注/)
})

test('unrecognized failures do not expose raw backend stack traces or RTSP credentials', () => {
  const response = describeVideoOpenError(
    new Error('Python API 422: ' + JSON.stringify({
      detail: 'Invalid rtsp://admin:secret@camera.example/stream',
    })))
  assert.equal(response.kind, 'other')
  assert.doesNotMatch(response.message, /secret|camera.example|rtsp:/)
  assert.deepEqual(describeVideoOpenError(new Error('raw stacktrace private path')).kind, 'other')
})

test('monitor and administrator login provide direct resolution-mismatch calibration flow', () => {
  const app = read('src/renderer/src/App.vue')
  const composable = read('src/renderer/src/composables/usePythonVideoStream.ts')
  const backend = read('backend/src/sample_backend/api/video.py')
  assert.ok(app.includes("videoOpenIssue.value === 'mismatch'"))
  assert.ok(app.includes("openCalibration(false)"))
  assert.ok(app.includes('videoOpenIssue === \'mismatch\''))
  assert.ok(app.includes('videoOpenIssue === \'oversize\''))
  assert.ok(app.includes('@click="switchUser">切换管理员'))
  assert.ok(app.includes('@click="openCalibration(false)">重新标注'))
  assert.ok(app.includes('frame.width !== calibration.value.width'))
  assert.ok(composable.includes('describeVideoOpenError(reason)'))
  assert.ok(backend.includes("'CALIBRATION_RESOLUTION_MISMATCH'"))
  assert.ok(backend.includes("'VIDEO_RESOLUTION_TOO_LARGE'"))
})
