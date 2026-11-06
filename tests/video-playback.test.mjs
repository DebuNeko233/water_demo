import assert from 'node:assert/strict'
import test from 'node:test'
import { seekToReferenceFrame } from '../src/renderer/src/utils/videoPlayback.mjs'

test('after calibrating at 72.45 seconds monitoring displays the same time instead of zero', () => {
  const video = { duration: 123, currentTime: 0, paused: false,
    pause() { this.paused = true } }
  const t = seekToReferenceFrame(video, 72.45)
  assert.equal(t, 72.45)
  assert.equal(video.currentTime, 72.45)
  assert.equal(video.paused, true)
})
test('recalibration can seek back or forward without auto-playing', () => {
  const video = { duration: 110, currentTime: 62, paused: false,
    pause() { this.paused = true } }
  assert.equal(seekToReferenceFrame(video, 18.5), 18.5)
  assert.equal(video.currentTime, 18.5)
  assert.equal(video.paused, true)
})
test('reference seeks clamp to actual video duration and discard invalid times', () => {
  const video = { duration: 30, currentTime: 0, pause() {} }
  assert.ok(Math.abs(seekToReferenceFrame(video, 300) - 29.99) < 1e-9)
  assert.equal(seekToReferenceFrame(video, Number.NaN), 0)
  assert.equal(seekToReferenceFrame(video, -2), 0)
})
