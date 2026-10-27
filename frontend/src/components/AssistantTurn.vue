<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import type { AssistantRun } from '@/types/workflows'
import RunTrace from './RunTrace.vue'
import { statusLabels } from '@/utils/support'
import type { TicketStatus } from '@/types'
import { useWorkspaceStore } from '@/stores/workspace'
const panel = useWorkspaceStore()

const props = defineProps<{ run: AssistantRun }>()
const chat = useChatStore()
const busy = ref(false)
const statuses = computed(() => props.run.result.ticket_statuses ?? (props.run.result.ticket_status ? [props.run.result.ticket_status] : []))
const labels: Record<string, string> = { queued: '等待回复', running: '正在处理', awaiting_confirmation: '待你确认', completed: '已完成', failed: '回复未完成', cancelled: '已停止' }
async function act(action: () => Promise<unknown>) {
  if (busy.value || chat.streaming) return
  busy.value = true
  try { await action() } catch (e) { ElMessage.error((e as Error).message) }
  finally { busy.value = false }
}
</script>

<template>
  <div class="assistant-turn">
    <span class="turn-status">{{ run.result.needs_input ? '请补充信息' : labels[run.status] }}</span>
    <article v-for="(ticket, i) in run.result.related_tickets ?? []" :key="ticket.id" class="related-ticket">
      <router-link :to="`/tickets/${ticket.id}`">[{{ ticket.citation ?? `工单${i + 1}` }}] {{ ticket.title }}</router-link>
      <details><summary>查看解决方案</summary><p>{{ ticket.solution }}</p></details>
    </article>
    <p v-for="ticket in statuses" :key="ticket.id" class="ticket-link">[{{ ticket.citation || '工单' }}] <router-link :to="`/tickets/${ticket.id}`">{{ ticket.title }}</router-link> · {{ statusLabels[ticket.status as TicketStatus] }}</p>
    <p v-if="run.ticket_id" class="ticket-link"><router-link :to="`/tickets/${run.ticket_id}`">查看已提交工单 →</router-link><span class="support-muted">编号：{{ run.ticket_id }}</span></p>
    <section v-if="run.status === 'awaiting_confirmation' && run.result.proposal" class="proposal-card">
      <div class="draft-summary"><span class="draft-icon">↗</span><div><h3>{{ run.result.proposal.title }}</h3><p>工单草稿已整理，等待你核对并提交</p></div></div>
      <el-button type="primary" plain @click="panel.openTicket(run.id)">查看并确认 →</el-button>
    </section>
    <div v-if="!chat.streaming" class="turn-actions">
      <el-button v-if="run.status === 'queued'" link type="primary" :disabled="busy" @click="act(() => chat.execute(run))">继续处理</el-button>
      <el-button v-if="['failed', 'cancelled'].includes(run.status)" link type="primary" :disabled="busy" @click="act(() => chat.retry(run.id))">重新尝试</el-button>
      <el-button v-if="['queued', 'running'].includes(run.status)" link :disabled="busy" @click="act(() => chat.cancelRun(run.id))">取消本次回复</el-button>
      <el-button v-if="['queued', 'running', 'awaiting_confirmation'].includes(run.status)" link :disabled="busy" @click="act(() => chat.refreshRun(run.id))">刷新状态</el-button>
    </div>
    <details v-if="run.steps?.length" class="processing-details"><summary>处理过程 · {{ run.steps.length }} 个步骤</summary><RunTrace :steps="run.steps" /></details>
  </div>
</template>

<style scoped>
.assistant-turn { margin-top: 10px; width: 100%; font-size: 13px; }
.turn-status { color: #a194ae; font-size: 10px; }
.proposal-card { margin-top: 16px; padding: 18px; background: #faf8fe; border: 1px solid #e7def5; border-radius: 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }.draft-summary { display: flex; gap: 12px; align-items: center; }.draft-icon { color: #8c76b5; font-size: 25px; }.proposal-card .draft-summary p { margin: 5px 0 0; font-size: 11px; }.proposal-card .draft-summary h3 { margin: 0; font-size: 13px; }
.proposal-card h3 { font-size: 15px; margin-bottom: 8px; }.proposal-card p { margin-bottom: 16px; color: var(--text-secondary); }
.related-ticket, .ticket-link { margin-top: 12px; line-height: 1.8; overflow-wrap: anywhere; }.related-ticket p { white-space: pre-wrap; }.ticket-link span { display: block; }
.related-ticket details summary { color: #9b90a6; font-size: 11px; cursor: pointer; }.processing-details { margin-top: 12px; font-size: 11px; }.processing-details > summary { cursor: pointer; color: var(--text-secondary); margin-bottom: 12px; }
.turn-actions { margin-top: 6px; }
</style>
