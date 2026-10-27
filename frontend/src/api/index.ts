import { http } from './client'
import type {
  AppConfig,
  AskPayload,
  AskResult,
  ChunkHit,
  DocumentItem,
  SessionDetail,
  SessionSummary,
  Stats,
  UploadResponse,
} from '@/types'

/* ---------- 系统 ---------- */

export async function getConfig(): Promise<AppConfig> {
  const { data } = await http.get<AppConfig>('/config')
  return data
}

export async function getStats(): Promise<Stats> {
  const { data } = await http.get<Stats>('/documents/stats')
  return data
}

/* ---------- 文档 ---------- */

export async function listDocuments(): Promise<DocumentItem[]> {
  const { data } = await http.get<DocumentItem[]>('/documents')
  return data
}

export async function uploadDocuments(
  files: File[],
  chunkSize: number,
  chunkOverlap: number,
): Promise<UploadResponse> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('chunk_size', String(chunkSize))
  form.append('chunk_overlap', String(chunkOverlap))

  const { data } = await http.post<UploadResponse>('/documents/upload', form)
  return data
}

export async function previewDocument(
  file: File,
  limit = 2000,
): Promise<{ filename: string; characters: number; truncated: boolean; text: string }> {
  const form = new FormData()
  form.append('file', file)
  form.append('limit', String(limit))
  const { data } = await http.post('/documents/preview', form)
  return data
}

export async function getDocumentChunks(
  filename: string,
): Promise<{ chunk_index: number; content: string }[]> {
  const { data } = await http.get(`/documents/${encodeURIComponent(filename)}/chunks`)
  return data
}

export async function deleteDocument(filename: string): Promise<void> {
  await http.delete(`/documents/${encodeURIComponent(filename)}`)
}

export async function searchDocuments(
  query: string,
  topK: number,
  similarityThreshold: number,
): Promise<ChunkHit[]> {
  const { data } = await http.post<ChunkHit[]>('/documents/search', {
    query,
    top_k: topK,
    similarity_threshold: similarityThreshold,
  })
  return data
}

/* ---------- 问答 ---------- */

export async function askOnce(payload: AskPayload): Promise<AskResult> {
  const { data } = await http.post<AskResult>('/chat/ask', payload)
  return data
}

export interface StreamHandlers {
  onContexts?: (contexts: ChunkHit[]) => void
  onDelta?: (text: string) => void
  onDone?: (data: { sources: string[]; contexts: ChunkHit[] }) => void
  onError?: (message: string) => void
}

function parseSseEvent(raw: string, handlers: StreamHandlers): void {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (dataLines.length === 0) return

  let payload: unknown
  try {
    payload = JSON.parse(dataLines.join('\n'))
  } catch {
    return
  }

  switch (event) {
    case 'contexts':
      handlers.onContexts?.(payload as ChunkHit[])
      break
    case 'delta':
      handlers.onDelta?.(payload as string)
      break
    case 'done':
      handlers.onDone?.(payload as { sources: string[]; contexts: ChunkHit[] })
      break
    case 'error':
      handlers.onError?.((payload as { message?: string })?.message ?? '未知错误')
      break
    default:
      break
  }
}

/**
 * SSE 流式问答。
 * 用 fetch + ReadableStream 手工解析，因为 EventSource 只支持 GET，
 * 而这里需要 POST 传参数与消息体。
 */
export async function askStream(
  payload: AskPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok || !response.body) {
    let detail = ''
    try {
      const body = await response.json()
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      detail = await response.text().catch(() => '')
    }
    throw new Error(detail || `请求失败 (HTTP ${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      if (raw.trim()) parseSseEvent(raw, handlers)
      boundary = buffer.indexOf('\n\n')
    }
  }

  if (buffer.trim()) parseSseEvent(buffer, handlers)
}

/* ---------- 会话 ---------- */

export async function listSessions(): Promise<SessionSummary[]> {
  const { data } = await http.get<SessionSummary[]>('/sessions')
  return data
}

export async function getSession(name: string): Promise<SessionDetail> {
  const { data } = await http.get<SessionDetail>(`/sessions/${encodeURIComponent(name)}`)
  return data
}

export async function saveSession(
  name: string,
  messages: { role: string; content: string; sources?: string[]; contexts?: ChunkHit[] }[],
): Promise<SessionDetail> {
  const { data } = await http.put<SessionDetail>(`/sessions/${encodeURIComponent(name)}`, {
    messages: messages.map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources ?? [],
      contexts: m.contexts ?? [],
    })),
  })
  return data
}

export async function deleteSession(name: string): Promise<void> {
  await http.delete(`/sessions/${encodeURIComponent(name)}`)
}

export function sessionExportUrl(name: string): string {
  return `/api/sessions/${encodeURIComponent(name)}/export`
}
