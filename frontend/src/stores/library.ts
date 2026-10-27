import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '@/api'
import type { DocumentItem, KnowledgeScope, Stats, UploadResponse } from '@/types'

export const useLibraryStore = defineStore('library', () => {
  const documents = ref<DocumentItem[]>([])
  const stats = ref<Stats>({
    total_chunks: 0,
    sources: 0,
    space: '',
    embedding_model: '',
  })
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref('')
  let generation = 0

  function reset() {
    generation++
    documents.value = []
    stats.value = { total_chunks: 0, sources: 0, space: '', embedding_model: '' }
    loading.value = false
    error.value = ''
  }

  async function refresh() {
    const current = ++generation
    loading.value = true
    try {
      const [docs, stat] = await Promise.all([api.listDocuments(), api.getStats()])
      if (current !== generation) return
      documents.value = docs
      stats.value = stat
      error.value = ''
    } catch (e) {
      if (current === generation) error.value = (e as Error).message
    } finally {
      if (current === generation) loading.value = false
    }
  }

  async function upload(
    files: File[],
    chunkSize: number,
    chunkOverlap: number,
    scope?: KnowledgeScope,
  ): Promise<UploadResponse> {
    uploading.value = true
    try {
      const result = await api.uploadDocuments(files, chunkSize, chunkOverlap, scope)
      await refresh()
      return result
    } finally {
      uploading.value = false
    }
  }

  async function remove(id: string, revision: number) {
    await api.deleteDocument(id, revision)
    await refresh()
  }

  async function loadChunks(filename: string) {
    return api.getDocumentChunks(filename)
  }

  return {
    documents,
    stats,
    loading,
    uploading,
    error,
    refresh,
    reset,
    upload,
    remove,
    loadChunks,
  }
})
