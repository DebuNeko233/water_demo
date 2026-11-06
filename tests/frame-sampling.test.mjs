import test from 'node:test'
import assert from 'node:assert/strict'
import { createFrameSampler } from '../src/renderer/src/utils/frameSampling.mjs'

test('30 FPS video is sampled in 8 video-time buckets, not 7.5 FPS', () => {
  const sampler = createFrameSampler(8)
  const selected = Array.from({length: 30}, (_, i) => i / 30).filter(t => sampler.shouldSample(t))
  assert.equal(selected.length, 8)
  assert.deepEqual(selected.map(t => Math.round(t * 30)), [0, 4, 8, 12, 15, 19, 23, 27])
})

test('25 FPS video still emits 8 samples per video second', () => {
  const sampler = createFrameSampler(8)
  const selected = Array.from({length: 50}, (_, i) => i / 25).filter(t => sampler.shouldSample(t))
  assert.equal(selected.length, 16)
  assert.deepEqual(selected.slice(0, 8).map(t => Math.round(t * 25)), [0, 4, 7, 10, 13, 16, 19, 22])
})

test('duplicate and out-of-order media times are rejected; reset enables new seek', () => {
  const sampler = createFrameSampler(8)
  assert.equal(sampler.shouldSample(0.03), true)
  assert.equal(sampler.shouldSample(0.05), false)
  assert.equal(sampler.shouldSample(0.1333), true)
  assert.equal(sampler.shouldSample(0.11), false)
  assert.equal(sampler.shouldSample(0.1333), false)
  sampler.reset()
  assert.equal(sampler.shouldSample(0.03), true)
})
