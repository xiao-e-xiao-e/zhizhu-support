import type { ChunkHit, IngestionJob, KnowledgeScope, TicketPriority } from '@/types'

export interface ToolStep {
  id: string; number: number; name: string; status: 'running' | 'succeeded' | 'failed' | 'awaiting_confirmation'
  input: Record<string, unknown>; output: Record<string, unknown>; error: string | null; elapsed_ms: number; created_at: string
}
export interface TicketProposal { title: string; description: string; priority: TicketPriority }
export interface SimilarTicket extends KnowledgeScope { citation?: string; id: string; title: string; solution: string; status: string; similarity: number }
export interface TicketState { id: string; title: string; status: string; priority: string; updated_at: string; citation?: string }
export interface AssistantRun extends KnowledgeScope {
  session?: string | null; message_id?: number | null
  id: string; kind: 'assistant' | 'faq'; status: 'queued' | 'running' | 'awaiting_confirmation' | 'completed' | 'failed' | 'cancelled'
  question: string; parent_id: string | null; model: string; ticket_id: string | null; error_code: string | null; error: string | null
  revision: number; expires_at: string; created_at: string; updated_at: string; steps?: ToolStep[]
  result: { needs_input?: boolean; answer?: string; contexts?: ChunkHit[]; sources?: string[]; related_tickets?: SimilarTicket[]
    ticket_status?: TicketState | null; ticket_statuses?: TicketState[]
    proposal?: TicketProposal | null; ticket_id?: string; faq_id?: string
    usage?: { total_tokens: number; model_calls?: number }; elapsed_ms?: number }
}
export type FAQState = 'generating' | 'failed' | 'draft' | 'review' | 'rejected' | 'indexing' | 'published'
export interface FAQDraft extends KnowledgeScope {
  id: string; ticket_id: string | null; question: string; answer: string; state: FAQState; revision: number
  author_id: string; reviewer_id: string | null; review_note: string; run_id: string | null
  document_id: string | null; revision_id: string | null; knowledge_state: string | null; job: IngestionJob | null
  created_at: string; updated_at: string; source_snapshot?: { title: string; problem: string; solution: string }
  events?: { action: string; note: string; actor_id: string; created_at: string }[]
}
