import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '@/api'
import type { DocumentItem, Stats, UploadResponse } from '@/types'

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

  async function refresh() {
    loading.value = true
    try {
      const [docs, stat] = await Promise.all([api.listDocuments(), api.getStats()])
      documents.value = docs
      stats.value = stat
      error.value = ''
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  async function upload(
    files: File[],
    chunkSize: number,
    chunkOverlap: number,
  ): Promise<UploadResponse> {
    uploading.value = true
    try {
      const result = await api.uploadDocuments(files, chunkSize, chunkOverlap)
      await refresh()
      return result
    } finally {
      uploading.value = false
    }
  }

  async function remove(filename: string) {
    await api.deleteDocument(filename)
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
    upload,
    remove,
    loadChunks,
  }
})
