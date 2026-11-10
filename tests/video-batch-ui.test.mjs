import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8')

const playback = read('src/renderer/src/composables/usePythonVideoStream.ts')
const client = read('src/renderer/src/services/python-video.ts')
const backend = read('backend/src/sample_backend/services/video_stream.py')
const app = read('src/renderer/src/App.vue')

test('HD file updates 15 presentation frames per second but analyzes all source frames', () => {
  assert.ok(playback.includes('videoWidth.value * videoHeight.value >= 1280 * 720'))
  assert.ok(playback.includes('const targetDisplayFPS = largeFrame ? 15 : 24'))
  assert.ok(playback.includes('Math.ceil(sourceFrameRate.value / targetDisplayFPS)'))
  assert.ok(playback.includes('readPythonVideoFrame(sid, displayBatchSize())'))
  assert.ok(playback.includes('1000 * displayBatchSize() / Math.max(1, sourceFrameRate.value)'))
  assert.ok(playback.includes('records.value.push(...packet.samples)'))
  assert.ok(client.includes('batch_frames: batchFrames'))
  assert.ok(backend.includes('self._next_locked(with_preview=False)'))
  assert.ok(backend.includes('packet[\'samples\'] = intermediate'))
  assert.ok(backend.includes('VideoNextInput(BaseModel)'))
})

test('seek and pause keep frame cursor, and camera display still has no timeline', () => {
  assert.ok(playback.includes('if (!sid || isLive.value) return'))
  assert.ok(playback.includes('if (!isPlaying.value || !sid || expectedVersion !== version) return'))
  assert.ok(backend.includes('if req.batch_frames == 1:'))
  assert.ok(app.includes('v-if="!isLiveVideo"'))
})

test('measured FPS and stage timings are visible without adding settings clutter', () => {
  assert.ok(app.includes('actualFrameRate.toFixed(1)'))
  assert.ok(playback.includes('VideoPerformance'))
  assert.ok(playback.includes('analysis_ms='))
  assert.ok(playback.includes('decode_ms='))
  assert.ok(playback.includes('preview_ms='))
  assert.ok(playback.includes('total_request_ms='))
})
