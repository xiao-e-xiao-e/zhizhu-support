<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { useWorkspaceStore } from '@/stores/workspace'
import { formatTime } from '@/utils/support'
import type { TicketProposal } from '@/types/workflows'
const chat = useChatStore(), panel = useWorkspaceStore()
const id = panel.runId
const run = computed(() => chat.messages.find(m => m.run?.id === id)?.run)
const draft = reactive<TicketProposal>({ ...(panel.ticketDrafts[id] ?? run.value?.result.proposal ?? { title: '', description: '', priority: 'normal' }) })
watch(draft, value => { panel.ticketDrafts[id] = { ...value } })
const busy = ref(false), error = ref('')
const now = ref(Date.now())
const expired = computed(() => !!run.value?.expires_at && new Date(run.value.expires_at).getTime() <= now.value)
onMounted(async () => { try { await chat.refreshRun(id) } catch (e) { error.value = (e as Error).message } })
const expiryTimer = window.setInterval(() => { now.value = Date.now() }, 1000)
onUnmounted(() => window.clearInterval(expiryTimer))
async function act(confirm: boolean) {
  if (busy.value || chat.streaming) return
  now.value = Date.now()
  if (confirm && expired.value) { error.value = '草稿确认时间已过，请重新整理工单。'; return }
  busy.value = true; error.value = ''
  try {
    if (confirm) { await chat.confirm(id, { ...draft }); ElMessage.success('工单已提交') }
    else await chat.cancelRun(id)
    delete panel.ticketDrafts[id]
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>
<template>
  <div class="draft-editor">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="run?.ticket_id"><div class="draft-result">工单已提交</div><p>客服可以查看你提交的问题和相关对话。</p><router-link :to="`/tickets/${run.ticket_id}`" @click="panel.close()">查看工单详情 →</router-link></template>
    <template v-else-if="run?.status === 'awaiting_confirmation'">
      <p class="draft-intro">检查并补充问题，确认提交后客服会收到工单。</p>
      <el-form label-position="top" @submit.prevent="act(true)">
        <el-form-item label="问题标题" required><el-input v-model="draft.title" aria-label="工单标题" maxlength="160" :disabled="busy" /></el-form-item>
        <el-form-item label="问题描述" required><el-input v-model="draft.description" aria-label="工单描述" type="textarea" :rows="9" maxlength="8000" :disabled="busy" /></el-form-item>
        <el-form-item label="优先级"><el-select v-model="draft.priority" :disabled="busy"><el-option label="一般" value="normal" /><el-option label="较低" value="low" /><el-option label="紧急" value="high" /></el-select></el-form-item>
        <p class="draft-expiry">确认有效至 {{ formatTime(run.expires_at) }}。关闭面板会保留草稿。</p>
        <div class="draft-footer"><el-button :disabled="busy || chat.streaming" @click="act(false)">放弃草稿</el-button><el-button type="primary" native-type="submit" :loading="busy" :disabled="chat.streaming || expired || !draft.title.trim() || !draft.description.trim()">确认提交工单</el-button></div>
      </el-form>
    </template>
    <p v-else class="draft-intro">{{ run?.status === 'cancelled' ? '此草稿已放弃，可以在对话中重新整理。' : '此草稿当前无法提交，请返回对话查看最新状态。' }}</p>
  </div>
</template>
<style scoped>
.draft-editor { padding: 0 24px 28px; }.draft-intro { font-size: 12px; color: #93899f; line-height: 1.9; margin-bottom: 24px; }.draft-expiry { font-size: 11px; line-height: 1.8; color: #99909f; margin: 20px 0; }.draft-footer { display: flex; justify-content: flex-end; position: sticky; bottom: -28px; background: #fcfbfe; padding: 16px 0; border-top: 1px solid #ece7f2; }.draft-result { font-weight: 600; color: #5d9074; margin-bottom: 12px; }.draft-editor > p { font-size: 12px; color: #93899f; margin-bottom: 18px; }.draft-editor > a { font-size: 13px; }
</style>
