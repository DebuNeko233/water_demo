import test from 'node:test'
import assert from 'node:assert/strict'
import { calibrationPointerToSource } from '../src/renderer/src/utils/calibrationPointer.mjs'

const rect = {left:120, top:60, width:800, height:450}
const dims = [1920, 1080]

test('metadata-only video still accepts clicks if SVG CTM is unavailable', () => {
  const svg = {getScreenCTM:()=>null, viewBox:{baseVal:{x:0,y:0,width:1920,height:1080}}}
  const result = calibrationPointerToSource(svg,520,285,rect,...dims)
  assert.deepEqual(result,{point:{x:960,y:540}, method:'viewport'})
})

test('SVG coordinate path still preferred when its transformation is usable', () => {
  const svg = {
    getScreenCTM:()=>({a:800/1920,b:0,c:0,d:450/1080,e:120,f:60}),
    viewBox:{baseVal:{x:0,y:0,width:1920,height:1080}},
  }
  const result = calibrationPointerToSource(svg,520,285,rect,...dims)
  assert.ok(result)
  assert.equal(result.method,'svg')
  assert.ok(Math.abs(result.point.x-960)<1e-8)
  assert.ok(Math.abs(result.point.y-540)<1e-8)
})

test('no CTM method, thrown CTM and outside click are handled without silently crashing', () => {
  assert.deepEqual(calibrationPointerToSource({},320,160,rect,...dims),
    {point:{x:480,y:240},method:'viewport'})
  const throwingSvg = {getScreenCTM(){throw new Error('not yet measurable')}}
  assert.deepEqual(calibrationPointerToSource(throwingSvg,520,285,rect,...dims),
    {point:{x:960,y:540},method:'viewport'})
  assert.equal(calibrationPointerToSource(null,10,10,rect,...dims),null)
  assert.equal(calibrationPointerToSource(null,520,285,rect,0,1080),null)
})
