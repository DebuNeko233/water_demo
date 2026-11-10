import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = name => fs.readFileSync(path.join(root, name), 'utf8')
const app = read('src/renderer/src/App.vue')
const modal = read('src/renderer/src/components/AlgorithmSettingsModal.vue')
const source = read('src/renderer/src/services/video-source.ts')
const playback = read('src/renderer/src/composables/usePythonVideoStream.ts')
const backend = read('backend/src/sample_backend/services/video_stream.py')

test('administrator settings use parameter video source and device configuration tabs', () => {
  for (const tab of ['检测参数', '视频源', '设备配置']) {
    assert.ok(modal.includes(tab), 'Missing settings tab: ' + tab)
  }
  assert.match(modal, /role="tablist"/)
  assert.match(modal, /sourceDraft\.kind === 'rtsp'/)
  assert.match(modal, /sourceDraft\.kind === 'usb'/)
  assert.match(modal, /v-model\.trim="sourceDraft\.rtsp_url"/)
  assert.match(modal, /v-model\.number="sourceDraft\.usb_index"/)
  assert.match(app, /@save-source="applyVideoSourceSettings"/)
  assert.match(app, /@import-profile="importDeviceProfile"/)
  assert.match(app, /@export-profile="exportDeviceProfile"/)
  assert.ok(source.includes("'/api/video/source/save'"))
})

test('live camera monitoring hides seek and timeline but retains pause and image/results', () => {
  assert.match(app, /v-if="!isLiveVideo"[\s\S]*aria-label="视频播放进度"/)
  assert.match(app, /v-else class="playback live-playback"/)
  assert.match(app, /v-if="!isLiveVideo" class="btn btn-muted" @click="restart"/)
  assert.match(app, /@click="togglePlay"/)
  assert.match(app, /isLiveVideo\.value \|\| !duration\.value/)
  assert.match(playback, /if \(!sid \|\| isLive\.value\) return/)
  assert.match(playback, /isLive\.value = session\.is_live/)
  assert.match(backend, /if self\._source_kind != 'file':\r?\n            raise InvalidFrame/)
  assert.match(backend, /def _live_loop/)
  assert.match(backend, /self\._next_locked\(\)/)
})

test('camera still capture and reference frames use administrator-only APIs', () => {
  assert.ok(app.includes('await cameraSnapshot(adminToken.value)'))
  assert.ok(app.includes('captureLiveStationReference(selectedStation.value, group, adminToken.value)'))
  assert.ok(app.includes('v-if="isLiveVideo && liveSnapshotUrl"'))
  assert.ok(app.includes('v-else class="calib-timeline"'))
  assert.ok(source.includes("'/api/video/snapshot'"))
  assert.ok(read('backend/src/sample_backend/api/stations.py').includes("'/reference/live'"))
  assert.ok(read('backend/src/sample_backend/api/video.py').includes('user_access.require_admin(req.admin_token)'))
})
