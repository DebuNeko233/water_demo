import test from 'node:test'
import assert from 'node:assert/strict'
import { toPlainCalibration } from '../src/renderer/src/services/detection-payload.mjs'

test('detector start payload can cross Electron structured-clone boundary', () => {
  const values = { cx: 270, cy: 389, radius: 120, width: 720, height: 576 }
  const wrapped = new Proxy(values, {})
  assert.throws(() => structuredClone(wrapped))
  const body = { calibration: toPlainCalibration(wrapped), sample_fps: 8 }
  assert.deepEqual(structuredClone(body), { calibration: values, sample_fps: 8 })
})

test('plain calibration payload does not inherit extra fields or changes', () => {
  const values = { cx: 260, cy: 440, radius: 108, width: 720, height: 576, extra: 123 }
  const plain = toPlainCalibration(new Proxy(values, {}))
  values.cx = 500
  assert.equal(plain.cx, 260)
  assert.deepEqual(Object.keys(plain).sort(), ['cx','cy','height','radius','width'])
})
