import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import MarkdownIt from 'markdown-it'

// 按需注册语言，避免把 highlight.js 全量语言包打进产物
const LANGUAGES = {
  bash,
  css,
  java,
  javascript,
  json,
  markdown,
  python,
  sql,
  typescript,
  xml,
  yaml,
} as const

for (const [name, definition] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, definition)
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const md = new MarkdownIt({
  // 关闭原始 HTML，防止模型输出里混入脚本
  html: false,
  linkify: true,
  breaks: true,
  highlight(code: string, lang: string): string {
    const language = lang && hljs.getLanguage(lang) ? lang : ''
    const highlighted = language
      ? hljs.highlight(code, { language, ignoreIllegals: true }).value
      : escapeHtml(code)
    const label = language || 'text'
    return `<div class="code-block"><div class="code-block__head">${label}</div><pre class="hljs"><code>${highlighted}</code></pre></div>`
  },
})

export function renderMarkdown(text: string): string {
  return md.render(text ?? '')
}

// Only citation text backed by this answer's actual retrieval results is interactive.
// Code tokens and Markdown links keep their normal renderer.
const defaultLinkOpen = md.renderer.rules.link_open
const defaultLinkClose = md.renderer.rules.link_close
md.renderer.rules.link_open = (tokens, index, options, env, self) => {
  if (env) env.linkDepth = Number(env.linkDepth || 0) + 1
  return defaultLinkOpen ? defaultLinkOpen(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
}
md.renderer.rules.link_close = (tokens, index, options, env, self) => {
  if (env) env.linkDepth = Math.max(0, Number(env.linkDepth || 0) - 1)
  return defaultLinkClose ? defaultLinkClose(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
}
md.renderer.rules.text = (tokens, index, _options, env) => {
  const text = escapeHtml(tokens[index]!.content)
  if (!env?.sourceCount || env.linkDepth) return text
  return text.replace(/\[资料\s*(\d+)\]/g, (original, number: string) => {
    const n = Number(number)
    if (!Number.isSafeInteger(n) || n < 1 || n > Number(env.sourceCount)) return original
    return `<button type="button" class="citation-link" data-source-index="${n - 1}" aria-label="查看资料${n}">${n}</button>`
  })
}

export function renderAnswerMarkdown(text: string, sourceCount: number): string {
  return md.render(text ?? '', { sourceCount, linkDepth: 0 })
}
