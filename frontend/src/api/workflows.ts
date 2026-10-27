import { http, getRequestSession } from './client'
import { consumeAssistantEvents } from '@/utils/assistantStream'
import type { KnowledgeScope, PageResult, TicketDetail } from '@/types'
import type { AssistantRun, FAQDraft, FAQState, TicketProposal, ToolStep } from '@/types/workflows'

export const listRuns = async (page = 1) => (await http.get<PageResult<AssistantRun>>('/agent/runs', { params: { page } })).data
export const getRun = async (id: string) => (await http.get<AssistantRun>(`/agent/runs/${id}`)).data
export const createRun = async (question: string, scope: KnowledgeScope, key: string, session?: string, options?: {topK: number; temperature: number; similarityThreshold: number}) => (await http.post<AssistantRun>('/agent/runs', { question, ...scope, request_key: key, session, top_k: options?.topK, temperature: options?.temperature, similarity_threshold: options?.similarityThreshold })).data
export const retryRun = async (id: string, key: string) => (await http.post<AssistantRun>(`/agent/runs/${id}/retry`, { request_key: key })).data
export const cancelRun = async (id: string) => (await http.post<AssistantRun>(`/agent/runs/${id}/cancel`)).data
export const confirmTicket = async (id: string, proposal: TicketProposal) => (await http.post<TicketDetail>(`/agent/runs/${id}/confirm-ticket`, { ...proposal, confirmed: true })).data

export async function streamRun(id: string, handlers: { onRun: (run: AssistantRun) => void; onStep: (step: ToolStep) => void; onDelta: (delta: {run_id: string; offset: number; text: string}) => void; onReset: (id: string) => void }, signal: AbortSignal) {
  const requestSession = getRequestSession()
  const response = await fetch(`/api/agent/runs/${id}/stream`, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Protection': '1' }, signal })
  if (!response.ok || !response.body) {
    if (response.status === 401 && requestSession === getRequestSession()) window.dispatchEvent(new Event('auth-expired'))
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `执行请求失败 (${response.status})`)
  }
  let finished = false
  await consumeAssistantEvents(response.body, (kind, data) => {
    const payload = data as Record<string, unknown>
    if (kind === 'run' || kind === 'done') { handlers.onRun(data as AssistantRun); if (kind === 'done') finished = true }
    else if (kind === 'step') handlers.onStep(data as ToolStep)
    else if (kind === 'answer_delta') {
      if (typeof payload.run_id !== 'string' || typeof payload.text !== 'string' || !Number.isSafeInteger(payload.offset) || Number(payload.offset) < 0) throw new Error('回复片段格式异常')
      handlers.onDelta(payload as {run_id: string; offset: number; text: string})
    }
    else if (kind === 'answer_reset') handlers.onReset(String(payload.run_id))
    else if (kind === 'error') throw new Error(String(payload.message || '执行失败，请查看记录'))
  })
  if (!finished) throw new Error('连接已断开，请刷新执行记录查看结果')
}

export const listFAQs = async (state?: FAQState, page = 1) => (await http.get<PageResult<FAQDraft>>('/faqs', { params: { state, page } })).data
export const getFAQ = async (id: string) => (await http.get<FAQDraft>(`/faqs/${id}`)).data
export const createFAQ = async (ticketId: string, mode: 'model' | 'manual', key: string) => (await http.post<FAQDraft>('/faqs', { ticket_id: ticketId, mode, request_key: key })).data
export const generateFAQ = async (id: string) => (await http.post<FAQDraft>(`/faqs/${id}/generate`)).data
export const saveFAQ = async (faq: FAQDraft, question: string, answer: string) => (await http.patch<FAQDraft>(`/faqs/${faq.id}`, { revision: faq.revision, question, answer })).data
export const faqAction = async (faq: FAQDraft, action: 'submit' | 'revise' | 'publish', note = '') => (await http.post<FAQDraft>(`/faqs/${faq.id}/${action}`, { revision: faq.revision, note })).data
export const reviewFAQ = async (faq: FAQDraft, decision: 'approve' | 'reject', note: string, reviewed: boolean) => (await http.post<FAQDraft>(`/faqs/${faq.id}/review`, { revision: faq.revision, decision, note, reviewed_no_sensitive_data: reviewed })).data
export const regenerateFAQ = async (faq: FAQDraft, key: string) => (await http.post<FAQDraft>(`/faqs/${faq.id}/regenerate`, { revision: faq.revision, request_key: key })).data
export const getGaps = async () => (await http.get<{ question: string; count: number; linked_tickets: number; updated_at: string }[]>('/faqs/gaps')).data
