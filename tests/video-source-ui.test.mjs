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

test('live camera has no seeking; detection uses explicit start-stop controls', () => {
  assert.match(app, /v-if="!isLiveVideo"[\s\S]*aria-label="视频播放进度"/)
  assert.match(app, /v-else class="playback live-playback"/)
  assert.match(app, /@click="startDetection">▶ 开始检测/)
  assert.match(app, /@click="stopDetection">■ 停止检测/)
  assert.doesNotMatch(app, /@click="togglePlay"/)
  assert.doesNotMatch(app, /@click="restart"/)
  assert.match(app, /isLiveVideo\.value \|\| !duration\.value/)
  assert.match(playback, /if \(!sid \|\| isLive\.value\) return/)
  assert.match(playback, /isLive\.value = session\.is_live/)
  assert.match(backend, /if self\._source_kind != 'file':\r?\n            raise InvalidFrame/)
  assert.match(backend, /def _live_loop/)
  assert.match(backend, /self\._next_locked\(\)/)
})

test('camera still capture and reference frames use administrator-only APIs', () => {
  assert.ok(app.includes('await cameraSnapshot(adminToken.value, isLiveVideo.value ? 0 : timeS)'))
  assert.ok(app.includes('captureLiveStationReference(selectedStation.value, group, adminToken.value)'))
  assert.ok(app.includes('v-if="liveSnapshotUrl"'))
  assert.ok(app.includes('v-else class="calib-timeline"'))
  assert.ok(source.includes("'/api/video/snapshot'"))
  assert.ok(read('backend/src/sample_backend/api/stations.py').includes("'/reference/live'"))
  assert.ok(read('backend/src/sample_backend/api/video.py').includes('user_access.require_admin(req.admin_token)'))
})


test('video file selection lives only in administrator source settings', () => {
  const main = read('src/main/index.ts')
  const preload = read('src/preload/index.ts')
  const bridge = read('src/shared/bridge.ts')
  const backendSource = read('backend/src/sample_backend/services/video_source.py')
  const backendPreview = read('backend/src/sample_backend/api/video.py')
  assert.ok(modal.includes('sourceDraft.file_path'))
  assert.ok(modal.includes('type="text"'))
  assert.ok(modal.includes('readonly placeholder="未选择视频"'))
  assert.ok(modal.includes('selectVideoFile()'))
  assert.ok(main.includes("system:select-video-file"))
  assert.ok(preload.includes("system:select-video-file"))
  assert.ok(bridge.includes("selectVideoFile(): Promise<string | null>"))
  assert.ok(source.includes('file_path: string'))
  assert.ok(backendSource.includes('target = Path(source.file_path or file_path)'))
  assert.ok(backendSource.includes("if settings.kind == 'file' and settings.file_path"))
  assert.ok(backendPreview.includes('frame_index = min(frames - 1, max(0, round(req.time_s * fps)))'))
  assert.ok(app.includes('refreshCalibrationSnapshot(timeS = calibrationTime.value)'))
  assert.ok(app.includes('onCalibrationSeekEnd'))
  assert.ok(!app.includes('type="file"'))
  assert.ok(!app.includes('更换视频'))
})
