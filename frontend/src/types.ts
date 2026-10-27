import type { AssistantRun } from './types/workflows'
export interface RagParams {
  top_k: number
  temperature: number
  similarity_threshold: number
}

export interface ChunkHit {
  document_id?: string
  revision_id?: string
  revision_number?: number
  id: string
  content: string
  source: string
  chunk_index: number
  similarity: number
  distance: number
}

export interface DocumentItem {
  id: string
  revision: number
  archived: boolean
  published_revision: number | null
  published_revision_id: string | null
  latest: KnowledgeRevision | null
  source: string
  chunks: number
  product_id?: string | null
  version_id?: string | null
}

export interface IngestionJob {
  id: string; revision_id: string; state: 'queued' | 'running' | 'succeeded' | 'failed'
  phase: string; progress: number; attempts: number; max_attempts: number; error: string | null
  available_at: string; updated_at: string
}
export interface KnowledgeRevision {
  id: string; number: number; state: 'queued' | 'processing' | 'ready' | 'published' | 'superseded' | 'failed'
  sha256: string; size_bytes: number; chunks: number; chunk_size: number; chunk_overlap: number
  embedding_model: string; original_available: boolean; created_at: string; published_at: string; job: IngestionJob | null
}
export interface RevisionHistory {
  revision: number; revisions: KnowledgeRevision[]
  events: { action: string; revision_id: string | null; actor_id: string | null; created_at: string }[]
}
export interface RetrievalTrace {
  original_query: string; query: string; status: 'not_needed' | 'rewritten' | 'unchanged' | 'fallback'
  latency_ms: number; search_latency_ms: number; tokens: number
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
  run?: AssistantRun | null
  retrieval?: RetrievalTrace
  id?: number
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  contexts?: ChunkHit[]
  /** 前端本地状态：正在流式接收 */
  streaming?: boolean
  /** 前端本地状态：本条消息出错 */
  error?: string
  feedback?: { rating: FeedbackRating; reason: string; ticket_id?: string | null } | null
}

export interface SessionSummary {
  name: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface SessionDetail {
  id?: string
  product_id?: string | null
  version_id?: string | null
  name: string
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export interface UploadResult {
  document_id?: string
  revision_id?: string
  deduplicated?: boolean
  revision?: KnowledgeRevision
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
  product_id?: string | null
  version_id?: string | null
  question: string
  session?: string | null
  top_k: number
  temperature: number
  similarity_threshold: number
  history?: { role: 'user' | 'assistant'; content: string }[]
}

export interface AskResult {
  message_id?: number | null
  answer: string
  sources: string[]
  contexts: ChunkHit[]
}

export interface KnowledgeScope { product_id: string | null; version_id: string | null }
export interface ProductVersion { id: string; name: string; is_active: boolean }
export interface Product { id: string; name: string; description: string; is_active: boolean; versions: ProductVersion[] }
export type TicketStatus = 'new' | 'in_progress' | 'resolved' | 'closed'
export type TicketPriority = 'low' | 'normal' | 'high'
export type FeedbackRating = 'helpful' | 'unresolved'
export interface PageResult<T> { items: T[]; total: number; page: number; page_size: number }
export interface TicketSummary extends KnowledgeScope {
  id: string; title: string; status: TicketStatus; priority: TicketPriority
  creator_id: string; creator_name: string; assignee_id: string | null; assignee_name: string | null
  product_name: string | null; version_name: string | null; revision: number; created_at: string; updated_at: string
}
export interface TicketDetail extends TicketSummary {
  description: string; conversation_id: string | null; message_id: number | null
  conversation_snapshot: { role: 'user' | 'assistant'; content: string; sources: string[] }[]
}
export interface TicketCreate extends KnowledgeScope {
  title: string; description: string; priority: TicketPriority; idempotency_key: string
  conversation_name?: string | null; message_id?: number | null
}
export interface TicketEvent {
  id: number; kind: 'created' | 'comment' | 'status' | 'assigned'; content: string
  details: Record<string, string | null>; actor_name: string; created_at: string
}
export interface FeedbackRecord {
  id: string; message_id: number | null; rating: FeedbackRating; reason: string
  question: string; answer: string; sources: string[]; ticket_id: string | null; user_name: string; updated_at: string
}
