/**
 * 检查仓库 Markdown 本地相对链接，避免代码迁移后文档引用失效。
 * 只依赖 Node.js；跳过代码围栏中的伪 Markdown，防止误报。
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const documents = [
  'README.md',
  'CHANGELOG.md',
  'AGENTS.md',
  'backend/README.md',
  ...fs.readdirSync(path.join(root, 'docs'))
    .filter((name) => name.endsWith('.md'))
    .map((name) => 'docs/' + name),
]

for (const relativeFile of documents) {
  test('relative documentation links exist: ' + relativeFile, () => {
    const file = path.join(root, relativeFile)
    const markdown = fs.readFileSync(file, 'utf8')

    // Ignore fenced code examples: JS such as arr[index](value) is not a Markdown link.
    const prose = []
    let fenceCharacter = null
    for (const line of markdown.split(/\r?\n/)) {
      const fence = line.match(/^\s*(`{3,}|~{3,})/)
      if (fence) {
        if (fenceCharacter === null) fenceCharacter = fence[1][0]
        else if (fenceCharacter === fence[1][0]) fenceCharacter = null
        continue
      }
      if (fenceCharacter === null) prose.push(line)
    }

    for (const match of prose.join('\n').matchAll(/(?<!!)\[[^\]]+\]\(([^)]+)\)/g)) {
      const url = match[1].trim()
      if (/^(?:https?:|mailto:|#)/i.test(url)) continue
      const relativeTarget = decodeURIComponent(url.split('#')[0].split('?')[0])
      if (!relativeTarget) continue

      const target = path.resolve(path.dirname(file), relativeTarget)
      assert.ok(
        fs.existsSync(target),
        relativeFile + ' has a broken link: ' + url,
      )
    }
  })
}
