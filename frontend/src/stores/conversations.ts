import { ref } from 'vue'
import { defineStore } from 'pinia'
import { listSessions } from '@/api'
import type { SessionSummary } from '@/types'

export function conversationTitle(name: string) {
  return name.replace(/ · [a-f0-9]{8}$/, '')
}

export const useConversationsStore = defineStore('conversations', () => {
  const items = ref<SessionSummary[]>([])
  const loading = ref(false)
  const error = ref('')
  let generation = 0
  let pending: Promise<void> | null = null
  function refresh(): Promise<void> {
    if (pending) return pending
    const current = generation
    loading.value = true
    error.value = ''
    pending = (async () => {
      try {
        const result = await listSessions()
        if (current === generation) items.value = result.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      } catch (e) {
        if (current === generation) error.value = (e as Error).message
      } finally {
        if (current === generation) { loading.value = false; pending = null }
      }
    })()
    return pending
  }
  function reset() { generation++; pending = null; items.value = []; error.value = ''; loading.value = false }
  return { items, loading, error, refresh, reset }
})
