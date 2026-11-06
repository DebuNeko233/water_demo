import test from 'node:test'
import assert from 'node:assert/strict'
import { containRect, clientToVideo, viewportToVideo, sourceViewBox } from '../src/renderer/src/utils/videoGeometry.mjs'

test('16:9 video in wide calibration box maps center and edge to source pixels', () => {
  const box = { left: 30, top: 80, width: 960, height: 460 }
  const fit = containRect(box.width, box.height, 1920, 1080)
  assert.ok(fit)
  assert.equal(fit.width, 460 * 16 / 9)
  const center = clientToVideo(box.left + box.width / 2, box.top + box.height / 2, box, 1920, 1080)
  assert.deepEqual(center, { x: 960, y: 540 })
  const right = clientToVideo(box.left + fit.left + fit.width, box.top + 230, box, 1920, 1080)
  assert.ok(right && Math.abs(right.x - 1920) < 1e-8)
})

test('portrait video in landscape area leaves side bars unclickable', () => {
  const box = { left: 10, top: 20, width: 900, height: 400 }
  assert.equal(clientToVideo(15, 220, box, 1080, 1920), null)
  assert.deepEqual(clientToVideo(460, 220, box, 1080, 1920), { x: 540, y: 960 })
})

test('landscape video in tall area leaves top and bottom bars unclickable', () => {
  const box = { left: 0, top: 0, width: 480, height: 600 }
  assert.equal(clientToVideo(240, 10, box, 1920, 1080), null)
  assert.deepEqual(clientToVideo(240, 300, box, 1920, 1080), { x: 960, y: 540 })
})

test('invalid sizes and outside points are rejected', () => {
  assert.equal(containRect(0, 400, 1920, 1080), null)
  assert.equal(clientToVideo(12, 20, { left: 20, top: 0, width: 500, height: 400 }, 1920, 1080), null)
})

test('calibration pointer and ROI use the same fitted viewport for any aspect ratio', () => {
  for (const [vw,vh,bw,bh,left,top] of [
    [1920,1080,980,430,40,60],
    [1080,1920,900,420,150,90],
    [3840,2160,420,710,10,10],
    [1280,720,870,380,33,48],
  ]) {
    const fitted = containRect(bw,bh,vw,vh)
    assert.ok(fitted)
    const frame = { left:left+fitted.left, top:top+fitted.top, width:fitted.width,height:fitted.height }
    for (const [x,y] of [[vw/2,vh/2],[vw*.82,vh*.36],[vw*.12,vh*.7]]) {
      const px = frame.left + x * frame.width / vw
      const py = frame.top + y * frame.height / vh
      const p = viewportToVideo(px,py,frame,vw,vh)
      assert.ok(p)
      assert.ok(Math.abs(p.x-x)<0.00001 && Math.abs(p.y-y)<0.00001)
    }
    assert.equal(viewportToVideo(frame.left-5,frame.top+frame.height/2,frame,vw,vh),null)
  }
})

test('SVG viewBox has the required x y width height values for both calibration and monitor', () => {
  for (const [width,height] of [[720,576],[1920,1080],[1080,1920]]) {
    const viewBox = sourceViewBox(width,height)
    const values = viewBox.split(' ').map(Number)
    assert.deepEqual(values, [0,0,width,height])
  }
  assert.equal(sourceViewBox(0,0),'0 0 1 1')
})
