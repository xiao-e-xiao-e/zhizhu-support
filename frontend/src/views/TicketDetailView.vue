<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/support'
import { createFAQ } from '@/api/workflows'
import { useAuthStore } from '@/stores/auth'
import type { TicketDetail, TicketEvent, TicketStatus } from '@/types'
import { statusLabels, priorityLabels, formatTime } from '@/utils/support'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const id = String(route.params.id)
const ticket = ref<TicketDetail | null>(null)
const events = ref<TicketEvent[]>([])
const eventPage = ref(1)
const eventTotal = ref(0)
const assignees = ref<{ id: string; username: string }[]>([])
const assignee = ref<string | null>(null)
const reply = ref('')
const solution = ref('')
const solutionOpen = ref(false)
const busy = ref(false)
const loading = ref(true)
const loadingOlder = ref(false)
const faqBusy = ref(false)
const error = ref('')
const isCreator = computed(() => ticket.value?.creator_id === auth.user?.id)

async function refresh() {
  const [detail, timeline] = await Promise.all([api.getTicket(id), api.getTicketEvents(id)])
  ticket.value = detail; assignee.value = detail.assignee_id
  events.value = [...timeline.items].reverse(); eventPage.value = 1; eventTotal.value = timeline.total
}
onMounted(async () => {
  try { await refresh(); if (auth.isStaff) assignees.value = await api.listAssignees() }
  catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
})
async function mutate(fn: (value: TicketDetail) => Promise<unknown>) {
  if (busy.value || !ticket.value) return false
  busy.value = true; error.value = ''
  try { await fn(ticket.value); await refresh(); return true }
  catch (e) {
    error.value = (e as Error).message
    try { await refresh() } catch { /* 原错误保留 */ }
    return false
  } finally { busy.value = false }
}
async function sendReply() {
  if (await mutate(value => api.replyTicket(id, reply.value, value.revision))) { reply.value = ''; ElMessage.success('回复已发送') }
}
async function status(target: TicketStatus, note = '') {
  if (target === 'closed') {
    try { await ElMessageBox.confirm('确认问题已经解决并关闭工单？关闭后不能继续回复。', '确认关闭') }
    catch { return }
  }
  if (await mutate(value => api.changeTicketStatus(id, target, value.revision, note))) {
    solutionOpen.value = false; solution.value = ''; ElMessage.success('工单状态已更新')
  }
}
async function reopen() {
  try {
    const { value } = await ElMessageBox.prompt('请补充仍未解决的情况，方便客服继续处理。', '重新打开工单', { inputType: 'textarea', inputPattern: /\S/, inputErrorMessage: '请填写情况说明' })
    await status('in_progress', value)
  } catch { /* 用户取消 */ }
}
async function older() {
  loadingOlder.value = true
  try { const data = await api.getTicketEvents(id, eventPage.value + 1); events.value = [...data.items].reverse().concat(events.value); eventPage.value++; eventTotal.value = data.total }
  catch (e) { error.value = (e as Error).message }
  finally { loadingOlder.value = false }
}
function eventLabel(event: TicketEvent) {
  if (event.kind === 'created') return '提交了工单'
  if (event.kind === 'comment') return '回复'
  if (event.kind === 'assigned') return `将处理人设为 ${event.details.to_assignee || '待分配'}`
  return `状态：${statusLabels[event.details.from_status as TicketStatus]} → ${statusLabels[event.details.to_status as TicketStatus]}`
}
async function prepareFAQ(mode: 'model' | 'manual') {
  if (!ticket.value || faqBusy.value) return
  faqBusy.value = true; error.value = ''
  try { const draft = await createFAQ(ticket.value.id, mode, crypto.randomUUID()); await router.push({ path: '/faqs', query: { id: draft.id, ...(mode === 'model' && draft.state === 'generating' ? { generate: '1' } : {}) } }) }
  catch (e) { error.value = (e as Error).message }
  finally { faqBusy.value = false }
}
</script>

<template>
  <div v-loading="loading" class="support-page">
    <el-button link @click="router.push('/tickets')">← 返回工单列表</el-button>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="detail-alert" />
    <template v-if="ticket">
      <header class="support-head detail-head"><div><h1 class="page-title">{{ ticket.title }}</h1><p class="page-desc">{{ ticket.creator_name }} 提交于 {{ formatTime(ticket.created_at) }}</p></div><el-tag size="large" :type="ticket.status === 'resolved' ? 'success' : ticket.status === 'closed' ? 'info' : 'primary'">{{ statusLabels[ticket.status] }}</el-tag></header>
      <div class="ticket-layout">
        <div>
          <section class="card support-section"><h2>问题描述</h2><p class="preserve-lines">{{ ticket.description }}</p>
            <div class="support-muted">产品：{{ ticket.product_name || '未指定' }} {{ ticket.version_name || '' }} · 优先级：{{ priorityLabels[ticket.priority] }}</div>
          </section>
          <section v-if="ticket.conversation_snapshot.length" class="card support-section"><el-collapse><el-collapse-item title="查看提交时附带的对话" name="context"><article v-for="(message, index) in ticket.conversation_snapshot" :key="index" class="snapshot-message"><b>{{ message.role === 'user' ? '用户' : '助手' }}</b><p class="preserve-lines">{{ message.content }}</p><p v-if="message.sources.length" class="support-muted">参考资料：{{ message.sources.join('、') }}</p></article></el-collapse-item></el-collapse></section>
          <section class="card support-section"><h2>处理记录</h2><el-button v-if="events.length < eventTotal" link :loading="loadingOlder" @click="older">加载更早记录</el-button>
            <article v-for="event in events" :key="event.id" class="ticket-event"><div class="event-head"><b>{{ event.actor_name }} · {{ eventLabel(event) }}</b><time>{{ formatTime(event.created_at) }}</time></div><p v-if="event.content" class="preserve-lines">{{ event.content }}</p></article>
            <form v-if="ticket.status !== 'closed'" class="reply-form" @submit.prevent="sendReply"><el-input v-model="reply" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="补充问题信息或回复处理建议" /><el-button native-type="submit" type="primary" :loading="busy" :disabled="!reply.trim()">发送回复</el-button></form>
            <p v-else class="support-muted">工单已由提交者确认关闭。</p>
          </section>
        </div>
        <aside><section class="card support-section"><h2>处理与跟进</h2><p>处理人：{{ ticket.assignee_name || '待分配' }}</p>
            <template v-if="auth.isStaff && ticket.status !== 'closed'">
              <el-select v-model="assignee" clearable placeholder="选择处理人" aria-label="选择处理人"><el-option v-for="user in assignees" :key="user.id" :label="user.username" :value="user.id" /></el-select>
              <el-button :disabled="busy || (assignee || null) === ticket.assignee_id" @click="mutate(value => api.assignTicket(id, assignee || null, value.revision))">分配工单</el-button>
              <el-button v-if="ticket.status === 'new'" type="primary" :disabled="busy" @click="mutate(value => api.assignTicket(id, auth.user!.id, value.revision))">接单处理</el-button>
              <el-button v-if="ticket.status === 'in_progress'" type="success" :disabled="busy" @click="solutionOpen = true">标记已解决</el-button>
            </template>
            <template v-if="ticket.status === 'resolved'"><p class="support-muted">已提供解决方案，等待提交者确认。</p><el-button v-if="isCreator" type="success" :disabled="busy" @click="status('closed', '提交者确认问题已解决')">确认关闭</el-button><el-button v-if="isCreator || auth.isStaff" :disabled="busy" @click="reopen">仍未解决，继续处理</el-button></template>
          </section><section v-if="auth.isStaff && ['resolved', 'closed'].includes(ticket.status)" class="card support-section"><h2>沉淀为知识</h2><p class="support-muted">从解决说明起草 FAQ，经过管理员审核和发布后用于共享问答。</p><el-button type="primary" :loading="faqBusy" @click="prepareFAQ('model')">生成 FAQ 草稿</el-button><el-button :disabled="faqBusy" @click="prepareFAQ('manual')">人工整理 FAQ</el-button></section></aside>
      </div>
    </template>
    <el-dialog v-model="solutionOpen" title="填写解决说明" width="560px" :close-on-click-modal="!busy"><el-input v-model="solution" type="textarea" :rows="5" maxlength="4000" placeholder="记录问题原因和解决方法，提交者将据此确认" /><template #footer><el-button :disabled="busy" @click="solutionOpen = false">取消</el-button><el-button type="success" :loading="busy" :disabled="!solution.trim()" @click="status('resolved', solution)">提交解决方案</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.detail-head { margin-top: 18px; }
.detail-alert { margin-top: 16px; }
.ticket-layout { display: grid; grid-template-columns: minmax(0, 1fr) 280px; align-items: start; gap: 22px; }
.ticket-layout aside .el-button { display: block; width: 100%; margin: 12px 0 0; }
.ticket-layout aside p { margin: 12px 0; }
.ticket-event { padding: 18px 0; border-bottom: 1px solid var(--border-default); }
.event-head { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
time { color: var(--text-secondary); font-size: 12px; white-space: nowrap; }
.preserve-lines { white-space: pre-wrap; overflow-wrap: anywhere; margin: 12px 0; line-height: 1.8; }
.snapshot-message { padding: 10px; border-bottom: 1px solid var(--border-default); }
.reply-form { display: grid; gap: 12px; justify-items: start; margin-top: 20px; width: 100%; }
.reply-form .el-textarea { width: 100%; }
@media(max-width: 1050px) { .ticket-layout { grid-template-columns: 1fr; } .ticket-layout aside { grid-row: 1; } .event-head { flex-direction: column; } }
</style>
