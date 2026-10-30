import test from 'node:test'
import assert from 'node:assert/strict'
import { renderAnswerMarkdown, renderMarkdown } from '../src/utils/markdown.ts'

test('citations map to the exact retrieved fragment, including repeated source files', () => {
  const html = renderAnswerMarkdown('步骤见[资料1]，更多说明见[资料2]。', 2)
  assert.match(html, /data-source-index="0"/)
  assert.match(html, /data-source-index="1"/)
  assert.match(html, /aria-label="查看资料2"/)
})
test('unbacked citations remain plain text', () => {
  const html = renderAnswerMarkdown('[资料0] [资料3] [资料999999999999999999999]', 2)
  assert.doesNotMatch(html, /<button/)
  assert.match(html, /\[资料3\]/)
})
test('code and Markdown link labels never become nested interactive controls', () => {
  const html = renderAnswerMarkdown('`[资料1]`\n\n```text\n[资料1]\n```\n\n[查看[资料1]](https://example.com)', 1)
  assert.doesNotMatch(html, /<button/)
  assert.match(html, /<code>\[资料1\]<\/code>/)
})
test('model HTML stays escaped and normal Markdown has no citation controls', () => {
  assert.doesNotMatch(renderAnswerMarkdown('<img src=x onerror=alert(1)>[资料1]', 1), /<img/)
  assert.doesNotMatch(renderMarkdown('[资料1]'), /<button/)
  assert.doesNotMatch(renderAnswerMarkdown('[unsafe](javascript:alert(1))', 1), /href="javascript/)
})
