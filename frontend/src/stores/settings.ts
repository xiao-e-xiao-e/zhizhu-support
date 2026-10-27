import { computed, reactive, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import * as api from '@/api'
import type { AppConfig } from '@/types'

const STORAGE_KEY = 'rag-kb-settings'

export const useSettingsStore = defineStore('settings', () => {
  const config = ref<AppConfig | null>(null)
  const loading = ref(false)
  const error = ref('')

  /** RAG 检索与分块参数 */
  const rag = reactive({
    topK: 5,
    temperature: 0.3,
    similarityThreshold: 0,
    chunkSize: 500,
    chunkOverlap: 100,
  })

  const llmReady = computed(() => Boolean(config.value?.llm_configured))

  function restore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return false
      const saved = JSON.parse(raw)
      if (saved?.rag) Object.assign(rag, saved.rag)
      // 重写旧格式，清除浏览器曾经持久化的模型密钥。
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ rag }))
      return true
    } catch {
      return false
    }
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ rag }))
    } catch {
      /* 隐私模式下 localStorage 不可写，忽略即可 */
    }
  }

  watch(rag, persist, { deep: true })

  async function loadConfig() {
    loading.value = true
    const hadLocal = restore()
    try {
      const data = await api.getConfig()
      config.value = data
      if (!hadLocal) {
        rag.topK = data.defaults.top_k
        rag.temperature = data.defaults.temperature
        rag.similarityThreshold = data.defaults.similarity_threshold
        rag.chunkSize = data.defaults.chunk_size
        rag.chunkOverlap = data.defaults.chunk_overlap
      }
      error.value = ''
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  function resetRag() {
    const defaults = config.value?.defaults
    rag.topK = defaults?.top_k ?? 5
    rag.temperature = defaults?.temperature ?? 0.3
    rag.similarityThreshold = defaults?.similarity_threshold ?? 0
    rag.chunkSize = defaults?.chunk_size ?? 500
    rag.chunkOverlap = defaults?.chunk_overlap ?? 100
  }

  return {
    config,
    loading,
    error,
    rag,
    llmReady,
    restore,
    loadConfig,
    resetRag,
  }
})
