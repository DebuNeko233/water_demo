import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const iconPath = path.join(root, 'resources', 'icon.ico')
const icon = readFileSync(iconPath)

test('Windows application icon is exactly the provided 256px ICO asset', () => {
  assert.equal(icon.length, 55835)
  assert.equal(
    createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${icon.length}\0`), icon])).digest('hex'),
    'c3e6e822348e1d8a880aad2ec5f39105810a38c8',
  )
  assert.equal(icon.readUInt16LE(0), 0)
  assert.equal(icon.readUInt16LE(2), 1)
  assert.equal(icon.readUInt16LE(4), 1)
  // ICO encodes 256 px dimensions as 0 in its directory.
  assert.equal(icon[6], 0)
  assert.equal(icon[7], 0)
  const bytes = icon.readUInt32LE(14)
  const offset = icon.readUInt32LE(18)
  assert.ok(offset + bytes <= icon.length)
  assert.ok(icon.subarray(offset, offset + 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')))
})

test('package, BrowserWindow and frontend favicon use the same asset', () => {
  const builder = readFileSync(path.join(root, 'electron-builder.yml'), 'utf8')
  const main = readFileSync(path.join(root, 'src/main/index.ts'), 'utf8')
  const html = readFileSync(path.join(root, 'src/renderer/index.html'), 'utf8')
  const favicon = readFileSync(path.join(root, 'src/renderer/public/favicon.ico'))
  assert.deepEqual(favicon, icon)
  assert.match(builder, /win:\s*\n\s*icon:\s*resources\/icon\.ico/)
  assert.match(builder, /from:\s*resources\/icon\.ico\s*\n\s*to:\s*icon\.ico/)
  assert.match(main, /icon:\s*windowIconPath/)
  assert.match(html, /href="\.\/favicon\.ico"/)
})

test('top-left brand-icon displays the same uploaded ICO as favicon', () => {
  const app = readFileSync(path.join(root, 'src/renderer/src/App.vue'), 'utf8')
  const css = readFileSync(path.join(root, 'src/renderer/src/styles/zebovision.css'), 'utf8')
  assert.match(app, /class="brand-icon"[^>]*><img src="\.\/favicon\.ico" alt=""\s*\/>/)
  assert.match(css, /\.brand-icon img\s*\{[^}]*object-fit:contain/)
})
