import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '@/api'
import type { ChatMessage } from '@/types'

export interface SendOptions {
  topK: number
  temperature: number
  similarityThreshold: number
  llm?: { api_key?: string; api_base_url?: string; chat_model?: string }
  /** 是否把本轮对话落到后端会话文件 */
  autoSave?: boolean
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionName = ref('')
  const streaming = ref(false)
  const error = ref('')

  let controller: AbortController | null = null

  async function send(question: string, options: SendOptions) {
    if (streaming.value) return

    const text = question.trim()
    if (!text) return

    messages.value.push({ role: 'user', content: text })

    // 先占位一条助手消息，后续靠 SSE 增量填充
    const index = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      contexts: [],
      sources: [],
      streaming: true,
    })

    streaming.value = true
    error.value = ''
    controller = new AbortController()

    const patch = (fn: (msg: ChatMessage) => void) => {
      const target = messages.value[index]
      if (target) fn(target)
    }

    try {
      await api.askStream(
        {
          question: text,
          session: options.autoSave ? sessionName.value || null : null,
          top_k: options.topK,
          temperature: options.temperature,
          similarity_threshold: options.similarityThreshold,
          llm: options.llm ?? null,
        },
        {
          onContexts: (contexts) => patch((msg) => (msg.contexts = contexts)),
          onDelta: (chunk) => patch((msg) => (msg.content += chunk)),
          onDone: (data) =>
            patch((msg) => {
              msg.sources = data.sources
              msg.contexts = data.contexts
            }),
          onError: (message) => patch((msg) => (msg.error = message)),
        },
        controller.signal,
      )
    } catch (e) {
      const err = e as Error
      if (err.name === 'AbortError') {
        patch((msg) => {
          msg.content = msg.content ? `${msg.content}\n\n_（已中断）_` : '_（已中断）_'
        })
      } else {
        patch((msg) => (msg.error = err.message))
        error.value = err.message
      }
    } finally {
      patch((msg) => (msg.streaming = false))
      streaming.value = false
      controller = null
    }
  }

  function stop() {
    controller?.abort()
  }

  function clear() {
    if (streaming.value) stop()
    messages.value = []
    sessionName.value = ''
    error.value = ''
  }

  function loadSession(name: string, loaded: ChatMessage[]) {
    if (streaming.value) stop()
    sessionName.value = name
    messages.value = loaded.map((msg) => ({ ...msg, streaming: false, error: undefined }))
    error.value = ''
  }

  function dropLast() {
    if (streaming.value) stop()
    if (messages.value.length > 0) messages.value.pop()
  }

  async function save(name: string) {
    const payload = messages.value
      .filter((msg) => msg.content && !msg.error)
      .map((msg) => ({
        role: msg.role,
        content: msg.content,
        sources: msg.sources ?? [],
        contexts: msg.contexts ?? [],
      }))
    await api.saveSession(name, payload)
    sessionName.value = name
  }

  return {
    messages,
    sessionName,
    streaming,
    error,
    send,
    stop,
    clear,
    loadSession,
    dropLast,
    save,
  }
})
