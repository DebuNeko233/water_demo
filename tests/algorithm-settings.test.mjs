import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DEFAULT_ALGORITHM_SETTINGS, ALGORITHM_GROUPS, copyAlgorithmSettings,
  validateAlgorithmSettings, readAlgorithmSettings, storeAlgorithmSettings,
} from '../src/renderer/src/utils/algorithm-settings.mjs'

test('original algorithm defaults and every editable field remain aligned', () => {
  assert.equal(DEFAULT_ALGORITHM_SETTINGS.s_water_threshold, 0.025)
  assert.equal(DEFAULT_ALGORITHM_SETTINGS.recover_hold_seconds, 0.60)
  assert.equal(DEFAULT_ALGORITHM_SETTINGS.sector_count, 24)
  const keys = ALGORITHM_GROUPS.flatMap(group => group.fields.map(field => field.key))
  assert.deepEqual([...keys].sort(), Object.keys(DEFAULT_ALGORITHM_SETTINGS).sort())
  assert.equal(validateAlgorithmSettings(copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS)), null)
})

test('invalid crossed ROI ratios, blur kernels and excessive history are rejected', () => {
  const base = copyAlgorithmSettings(DEFAULT_ALGORITHM_SETTINGS)
  for (const [key, value] of [
    ['inner_radius_ratio', 1.2],
    ['blur_ksize', 4],
    ['history_seconds', 10],
    ['sector_count', 1],
    ['s_water_threshold', Number.NaN],
  ]) {
    assert.ok(validateAlgorithmSettings({...base, [key]: value}))
  }
})

test('settings round-trip without sharing mutable proxy objects', () => {
  const data = new Map()
  const storage = {
    getItem(key) { return data.get(key) ?? null },
    setItem(key,value) { data.set(key,value) },
  }
  const current = {...DEFAULT_ALGORITHM_SETTINGS, s_water_threshold: 0.045, sector_count: 12}
  const wrapped = new Proxy(current, {})
  storeAlgorithmSettings(storage, wrapped)
  const loaded = readAlgorithmSettings(storage)
  assert.equal(loaded.s_water_threshold, 0.045)
  assert.equal(loaded.sector_count, 12)
  assert.doesNotThrow(() => structuredClone(loaded))
  assert.equal(readAlgorithmSettings({getItem: () => 'corrupt'}).sector_count, 24)
})
