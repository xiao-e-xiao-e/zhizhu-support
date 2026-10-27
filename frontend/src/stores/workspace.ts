import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ChunkHit } from '@/types'
import type { TicketProposal } from '@/types/workflows'

export const useWorkspaceStore = defineStore('workspace', () => {
  const kind = ref<'sources' | 'ticket' | 'settings' | null>(null)
  const contexts = ref<ChunkHit[]>([])
  const sources = ref<string[]>([])
  const selectedSource = ref(0)
  const runId = ref('')
  const ticketDrafts = ref<Record<string, TicketProposal>>({})
  const collapsed = ref(false)
  function close() { kind.value = null; contexts.value = []; sources.value = []; runId.value = '' }
  function openSources(hits: ChunkHit[] = [], names: string[] = [], index = 0) {
    contexts.value = hits; sources.value = names; selectedSource.value = index; kind.value = 'sources'
  }
  function openTicket(id: string) { runId.value = id; kind.value = 'ticket' }
  function openSettings() { kind.value = 'settings' }
  function reset() { close(); ticketDrafts.value = {} }
  return { kind, contexts, sources, selectedSource, runId, ticketDrafts, collapsed, close, reset, openSources, openTicket, openSettings }
})
