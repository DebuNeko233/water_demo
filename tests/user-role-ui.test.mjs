import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const read = p => fs.readFileSync(path.join(root, p), 'utf8')
const app = read('src/renderer/src/App.vue')
const monitor = read('src/renderer/src/services/python-video.ts')
const backendVideo = read('backend/src/sample_backend/api/video.py')
const legacy = read('backend/src/sample_backend/api/detection.py')
const auth = read('backend/src/sample_backend/services/user_access.py')

test('operator is the initial role and gear is visible only to admins', () => {
  assert.match(app, /currentRole = ref<UserRole>\('operator'\)/)
  assert.match(app, /class="algorithm-gear"[^\n]*currentRole === 'admin'/)
  assert.match(app, /currentRole\.value !== 'admin' \|\| !adminToken\.value/)
  assert.match(app, /v-if="algorithmSettingsOpen && currentRole === 'admin'"/)
  assert.match(app, /class="role-switch"/)
  assert.match(app, /切换管理员/)
  assert.match(app, /退出管理员/)
})

test('operator video never passes a user-selected detector configuration', () => {
  const open = monitor.slice(monitor.indexOf('export function openPythonVideo('),
    monitor.indexOf('export function readPythonVideoFrame('))
  assert.ok(open.includes("'/api/video/open'"))
  assert.ok(!/detector:\s*copyAlgorithmSettings/.test(open))
  assert.match(backendVideo, /user_access\.resolve_detector\(req\.detector, req\.admin_token\)/)
  assert.match(legacy, /user_access\.resolve_detector\(body\.detector, body\.admin_token\)/)
  assert.match(auth, /def update_settings\(self, token: str, settings: DetectorSettings\)/)
  assert.match(auth, /self\._check\(token\)/)
})

test('administrator password and settings are not stored in frontend localStorage', () => {
  assert.ok(!app.includes('storeAlgorithmSettings('))
  assert.ok(!app.includes('readAlgorithmSettings('))
  assert.match(app, /saveApprovedSettings\(adminToken\.value/)
  assert.match(app, /loginAdministrator\(password\)/)
  assert.match(app, /setupAdministrator\(password\)/)
  assert.match(app, /resetToOperator\(\)/)
  const dialog = read('src/renderer/src/components/AdminAccessDialog.vue')
  assert.match(dialog, /type="password"/)
  assert.match(dialog, /两次输入的密码不一致/)
})
