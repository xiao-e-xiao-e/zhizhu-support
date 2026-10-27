import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '@/api'
import * as workflows from '@/api/workflows'
import type { ChatMessage, KnowledgeScope } from '@/types'
import type { AssistantRun, TicketProposal } from '@/types/workflows'
import { useConversationsStore } from './conversations'
import { useWorkspaceStore } from './workspace'

export interface SendOptions { topK: number; temperature: number; similarityThreshold: number }

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionName = ref('')
  const scope = ref<KnowledgeScope>({ product_id: null, version_id: null })
  const streaming = ref(false)
  const error = ref('')
  let controller: AbortController | null = null
  let generation = 0
  let activeRunId = ''

  function applyRun(run: AssistantRun, index?: number) {
    const target = messages.value.find(m => m.run?.id === run.id) ?? (index === undefined ? undefined : messages.value[index])
    if (!target) return
    target.run = run
    target.id = run.message_id ?? target.id
    target.content = run.result.answer || run.error || ''
    target.contexts = run.result.contexts ?? []
    target.sources = run.result.sources ?? []
    target.error = run.status === 'failed' ? run.error || '本次回复未完成，请重试' : undefined
  }

  async function execute(run: AssistantRun, index?: number) {
    if (streaming.value) return
    const current = ++generation
    activeRunId = run.id
    streaming.value = true; error.value = ''; controller = new AbortController()
    applyRun(run, index)
    const target = messages.value.find(m => m.run?.id === run.id)
    if (target) target.streaming = true
    try {
      await workflows.streamRun(run.id, {
        onRun: value => { if (current === generation) applyRun(value, index) },
        onDelta: delta => {
          if (current !== generation || delta.run_id !== run.id) return
          const item = messages.value.find(m => m.run?.id === run.id)
          if (!item) return
          if (delta.offset === item.content.length) item.content += delta.text
          else throw new Error('回复片段顺序异常，请刷新查看已保存的内容')
        },
        onReset: id => {
          if (current !== generation || id !== run.id) return
          const item = messages.value.find(m => m.run?.id === id)
          if (item) item.content = ''
        },
        onStep: step => {
          if (current !== generation) return
          const item = messages.value.find(m => m.run?.id === run.id)
          if (!item?.run) return
          const steps = item.run.steps ?? []
          const found = steps.findIndex(s => s.id === step.id)
          if (found < 0) steps.push(step); else steps[found] = step
          item.run.steps = steps
        },
      }, controller.signal)
    } catch (e) {
      if (current !== generation) return
      if ((e as Error).name !== 'AbortError') error.value = (e as Error).message
      try { const latest = await workflows.getRun(run.id); if (current === generation) applyRun(latest, index) }
      catch { /* Keep the original connection error. */ }
    } finally {
      if (current === generation) {
        const item = messages.value.find(m => m.run?.id === run.id)
        if (item) item.streaming = false
        streaming.value = false; controller = null; activeRunId = ''
        void useConversationsStore().refresh()
      }
    }
  }

  async function send(question: string, options: SendOptions) {
    const text = question.trim()
    if (!text || streaming.value) return
    if (!sessionName.value) sessionName.value = `${Array.from(text).slice(0, 32).join('').replace(/[/\\\u0000-\u001f]/g, " ").trim()} · ${crypto.randomUUID().slice(0, 8)}`
    const current = ++generation
    messages.value.push({ role: 'user', content: text })
    const index = messages.value.length
    messages.value.push({ role: 'assistant', content: '', streaming: true, sources: [], contexts: [] })
    streaming.value = true; error.value = ''
    try {
      const run = await workflows.createRun(text, scope.value, crypto.randomUUID(), sessionName.value, options)
      if (current !== generation) { void workflows.cancelRun(run.id).catch(() => {}); return }
      streaming.value = false
      await execute(run, index)
    } catch (e) {
      if (current !== generation) return
      streaming.value = false
      error.value = (e as Error).message
      const target = messages.value[index]
      if (target) { target.streaming = false; target.error = error.value }
      // A response can be lost after the server has created the turn. Recover it
      // instead of issuing another request that could duplicate a task.
      try {
        const saved = await api.getSession(sessionName.value)
        if (current === generation && saved.messages.length) messages.value = normalize(saved.messages)
      } catch { /* A failed creation has no saved conversation. */ }
    }
  }

  async function refreshRun(id: string) {
    const current = generation
    const run = await workflows.getRun(id)
    if (current === generation) applyRun(run)
  }

  async function cancelRun(id: string) {
    const current = generation
    const run = await workflows.cancelRun(id)
    if (current === generation) {
      applyRun(run)
      if (id === activeRunId) controller?.abort()
    }
  }

  async function stop() {
    if (activeRunId) {
      try { await cancelRun(activeRunId) } catch (e) { error.value = (e as Error).message }
    } else {
      controller?.abort()
      generation++; streaming.value = false
      const last = messages.value.at(-1)
      if (last?.streaming) { last.streaming = false; last.content = '已停止本次回复。' }
    }
  }

  async function confirm(id: string, proposal: TicketProposal) {
    const current = generation
    const ticket = await workflows.confirmTicket(id, proposal)
    if (current === generation) await refreshRun(id)
    return ticket
  }

  async function retry(id: string) {
    if (streaming.value) return
    const current = ++generation
    streaming.value = true
    try {
      const run = await workflows.retryRun(id, crypto.randomUUID())
      if (current !== generation) return
      const saved = await api.getSession(run.session || sessionName.value)
      if (current !== generation) return
      messages.value = normalize(saved.messages)
      streaming.value = false
      await execute(run)
    } catch (e) { if (current === generation) { streaming.value = false; error.value = (e as Error).message } }
  }

  function clear() {
    useWorkspaceStore().close()
    controller?.abort()
    if (activeRunId) void workflows.cancelRun(activeRunId).catch(() => {})
    generation++; activeRunId = ''; controller = null
    streaming.value = false; messages.value = []; sessionName.value = ''
    scope.value = { product_id: null, version_id: null }; error.value = ''
  }

  function normalize(loaded: ChatMessage[]) {
    return loaded.map(msg => ({ ...msg, streaming: false, error: msg.run?.status === 'failed' ? msg.run.error || '回复未完成' : undefined }))
  }

  function loadSession(name: string, loaded: ChatMessage[], loadedScope?: KnowledgeScope) {
    clear()
    sessionName.value = name
    scope.value = loadedScope ?? { product_id: null, version_id: null }
    messages.value = normalize(loaded)
  }

  async function save(name: string) {
    if (!sessionName.value || streaming.value) return
    if (/[\\/\u0000-\u001f]/.test(name)) throw new Error('对话名称不能包含斜杠或换行')
    const current = generation
    const saved = await api.renameSession(sessionName.value, name)
    if (current !== generation) return
    messages.value = normalize(saved.messages); sessionName.value = name
    void useConversationsStore().refresh()
  }

  return { messages, sessionName, scope, streaming, error, send, execute, stop, clear, loadSession, save, refreshRun, cancelRun, confirm, retry }
})
