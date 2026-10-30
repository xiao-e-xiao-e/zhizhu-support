import type { TicketStatus, TicketPriority } from '@/types'
export const statusLabels: Record<TicketStatus, string> = { new: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' }
export const priorityLabels: Record<TicketPriority, string> = { low: '较低', normal: '一般', high: '紧急' }
export function formatTime(value: string) { return new Date(value).toLocaleString('zh-CN', { hour12: false }) }
