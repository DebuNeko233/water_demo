import test from 'node:test'
import assert from 'node:assert/strict'
import { svgClientToSource, svgSourceToClient } from '../src/renderer/src/utils/svgCoordinates.mjs'
function fakeSvg(m, w=1920, h=1080) {
  return {getScreenCTM:()=>m,viewBox:{baseVal:{x:0,y:0,width:w,height:h}}}
}
test('click-to-SVG inverse is accurate after scaling and translation', () => {
  const svg=fakeSvg({a:.4,b:0,c:0,d:.4,e:150,f:220})
  const p=svgClientToSource(svg,534,436)
  assert.ok(Math.abs(p.x-960)<1e-9 && Math.abs(p.y-540)<1e-9)
  const screen=svgSourceToClient(svg,p.x,p.y)
  assert.ok(Math.abs(screen.x-534)<1e-9 && Math.abs(screen.y-436)<1e-9)
})
test('nonuniform scaling and viewport crop still invert exactly', () => {
  const svg=fakeSvg({a:.7,b:0,c:0,d:.4,e:5,f:15})
  const screen=svgSourceToClient(svg,800,250)
  const p=svgClientToSource(svg,screen.x,screen.y)
  assert.ok(Math.abs(p.x-800)<1e-9 && Math.abs(p.y-250)<1e-9)
})
test('rotated or skewed SVG matrix is handled', () => {
  const svg=fakeSvg({a:1.2,b:.2,c:-.1,d:.8,e:500,f:75})
  const screen=svgSourceToClient(svg,264,443)
  const p=svgClientToSource(svg,screen.x,screen.y)
  assert.ok(Math.abs(p.x-264)<1e-9 && Math.abs(p.y-443)<1e-9)
})
test('out of viewBox or degenerate transform is rejected', () => {
  const svg=fakeSvg({a:1,b:0,c:0,d:1,e:100,f:200})
  assert.equal(svgClientToSource(svg,20,350),null)
  assert.equal(svgClientToSource(fakeSvg({a:0,b:0,c:0,d:0,e:0,f:0}),5,5),null)
})
