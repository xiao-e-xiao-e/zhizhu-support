import { http } from './client'
import type { FeedbackRating, FeedbackRecord, PageResult, Product, ProductVersion, TicketCreate, TicketDetail, TicketEvent, TicketStatus, TicketSummary } from '@/types'

export async function listProducts() { return (await http.get<Product[]>('/products')).data }
export async function createProduct(name: string, description: string) { return (await http.post<Product>('/products', { name, description })).data }
export async function setProductActive(id: string, is_active: boolean) { await http.patch(`/products/${id}`, { is_active }) }
export async function createVersion(id: string, name: string) { return (await http.post<ProductVersion>(`/products/${id}/versions`, { name })).data }
export async function setVersionActive(product: string, version: string, is_active: boolean) { await http.patch(`/products/${product}/versions/${version}`, { is_active }) }
export async function createTicket(payload: TicketCreate) { return (await http.post<TicketDetail>('/tickets', payload)).data }
export async function listTickets(params: { page: number; status?: TicketStatus; product_id?: string; mine?: boolean }) {
  return (await http.get<PageResult<TicketSummary>>('/tickets', { params })).data
}
export async function getTicket(id: string) { return (await http.get<TicketDetail>(`/tickets/${id}`)).data }
export async function getTicketEvents(id: string, page = 1) { return (await http.get<PageResult<TicketEvent>>(`/tickets/${id}/events`, { params: { page } })).data }
export async function listAssignees() { return (await http.get<{ id: string; username: string }[]>('/tickets/assignees')).data }
export async function assignTicket(id: string, assignee_id: string | null, expected_revision: number) {
  return (await http.post<TicketDetail>(`/tickets/${id}/assignee`, { assignee_id, expected_revision })).data
}
export async function changeTicketStatus(id: string, status: TicketStatus, expected_revision: number, note = '') {
  return (await http.post<TicketDetail>(`/tickets/${id}/status`, { status, expected_revision, note })).data
}
export async function replyTicket(id: string, content: string, expected_revision: number) {
  return (await http.post<TicketDetail>(`/tickets/${id}/comments`, { content, expected_revision })).data
}
export async function rateAnswer(id: number, rating: FeedbackRating, reason = '') {
  return (await http.put<FeedbackRecord>(`/feedback/messages/${id}`, { rating, reason })).data
}
export async function listFeedback(page: number, rating?: FeedbackRating) {
  return (await http.get<PageResult<FeedbackRecord>>('/feedback', { params: { page, rating } })).data
}
