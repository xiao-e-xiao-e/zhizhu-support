export interface RagParams {
  top_k: number
  temperature: number
  similarity_threshold: number
}

export interface ChunkHit {
  id: string
  content: string
  source: string
  chunk_index: number
  similarity: number
  distance: number
}

export interface DocumentItem {
  source: string
  chunks: number
}

export interface Stats {
  total_chunks: number
  sources: number
  space: string
  embedding_model: string
}

export interface AppConfig {
  llm_configured: boolean
  api_base_url: string
  chat_model: string
  embedding_model: string
  embedding_dimension: number | null
  embedding_error: string | null
  max_tokens: number
  defaults: {
    chunk_size: number
    chunk_overlap: number
    top_k: number
    temperature: number
    similarity_threshold: number
  }
  collection: Record<string, unknown>
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  contexts?: ChunkHit[]
  /** 前端本地状态：正在流式接收 */
  streaming?: boolean
  /** 前端本地状态：本条消息出错 */
  error?: string
}

export interface SessionSummary {
  name: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface SessionDetail {
  name: string
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export interface UploadResult {
  filename: string
  chunks: number
  ok: boolean
  error: string | null
}

export interface UploadResponse {
  results: UploadResult[]
  total_chunks: number
  failed: number
}

export interface AskPayload {
  question: string
  session?: string | null
  top_k: number
  temperature: number
  similarity_threshold: number
  llm?: {
    api_key?: string
    api_base_url?: string
    chat_model?: string
  } | null
}

export interface AskResult {
  answer: string
  sources: string[]
  contexts: ChunkHit[]
}
