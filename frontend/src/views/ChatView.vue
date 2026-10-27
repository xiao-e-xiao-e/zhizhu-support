<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Top, VideoPause, EditPen, Reading, Tickets, ChatLineSquare } from '@element-plus/icons-vue'

import MessageItem from '@/components/MessageItem.vue'
import ScopePicker from '@/components/ScopePicker.vue'
import TicketCreateDialog from '@/components/TicketCreateDialog.vue'
import { getSession } from '@/api'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { conversationTitle } from '@/stores/conversations'
import { rateAnswer } from '@/api/support'
import type { FeedbackRating } from '@/types'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'

const router = useRouter()
const route = useRoute()
const chat = useChatStore()
const settings = useSettingsStore()

const input = ref('')
const panel = useWorkspaceStore()
const auth = useAuthStore()
const title = computed(() => conversationTitle(chat.sessionName) || '智能助手')
const scroller = ref<HTMLElement | null>(null)
const ticketOpen = ref(false)
const selectedAnswer = ref(-1)
const ticketQuestion = ref('')
const feedbackOpen = ref(false)
const feedbackReason = ref('')
const feedbackBusy = ref(false)
const feedbackError = ref('')
watch(() => chat.sessionName, () => { input.value = ''; panel.close() })

const examples = [
  { icon: Reading, title: '了解产品用法', description: '查找指南，获取有依据的解答', question: '如何排查登录失败？' },
  { icon: Tickets, title: '查找解决方案', description: '参考已经解决的相似问题', question: '帮我查找已解决的相似工单' },
  { icon: ChatLineSquare, title: '寻求人工协助', description: '整理问题，交给客服跟进', question: '帮我整理一个需要客服处理的问题' },
]
const loadingSession = ref(false)
let loadGeneration = 0
onUnmounted(() => { loadGeneration++ })
async function openFromUrl() {
  const name = typeof route.query.session === 'string' ? route.query.session : ''
  if (!name || name === chat.sessionName) return
  if (chat.streaming) { ElMessage.warning('请先停止当前回复，再打开其他对话'); return }
  const request = ++loadGeneration, owner = auth.user?.id
  loadingSession.value = true
  try {
    const saved = await getSession(name)
    if (request !== loadGeneration || owner !== auth.user?.id || route.query.session !== name) return
    chat.loadSession(saved.name, saved.messages, {product_id: saved.product_id ?? null, version_id: saved.version_id ?? null})
    await scrollToBottom()
  } catch (e) { if (request === loadGeneration && owner === auth.user?.id) ElMessage.error((e as Error).message) }
  finally { if (request === loadGeneration) loadingSession.value = false }
}
onMounted(async () => {
  await openFromUrl()
  if (typeof route.query.question === 'string') input.value = route.query.question.slice(0, 4000)
})
watch(() => route.query.session, openFromUrl)
watch(() => chat.sessionName, name => {
  if (!loadingSession.value) void router.replace({ path: '/assistant', query: name ? { session: name } : {} })
})

async function scrollToBottom() {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => chat.messages.length, scrollToBottom)
watch(() => chat.messages.at(-1)?.run?.steps?.length, scrollToBottom)
watch(
  () => chat.messages[chat.messages.length - 1]?.content,
  () => scrollToBottom(),
)

async function send(text?: string) {
  const question = (text ?? input.value).trim()
  if (!question || chat.streaming || loadingSession.value) return

  input.value = ''
  await chat.send(question, {
    topK: settings.rag.topK,
    temperature: settings.rag.temperature,
    similarityThreshold: settings.rag.similarityThreshold,
  })
}
function inputKey(event: KeyboardEvent) {
  if (!event.isComposing) { event.preventDefault(); void send() }
}

async function saveCurrent() {
  if (!chat.messages.length || chat.streaming) return
  try {
    const { value } = await ElMessageBox.prompt('为这段对话起个名字，方便下次继续。', '重命名对话', {
      inputValue: conversationTitle(chat.sessionName), inputValidator: value => !!value?.trim() || '请输入对话名称',
      confirmButtonText: '保存', cancelButtonText: '取消',
    })
    await chat.save(value.trim())
    ElMessage.success('对话已重命名')
  } catch (e) { if (e instanceof Error) ElMessage.error(e.message) }
}

async function clearAll() {
  if (!chat.messages.length) return
  try {
    await ElMessageBox.confirm(
      '开始新的对话？当前记录已自动保存，可在对话历史中继续。',
      '开始新会话',
      { type: 'warning', confirmButtonText: '开始新对话', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  chat.clear()
  loadGeneration++; loadingSession.value = false
}

async function regenerate() {
  if (chat.streaming) return
  const previous = chat.messages.slice(0, -1).reverse().find(m => m.role === 'user')
  if (previous) await send(previous.content)
}

async function prepareTicket(index: number) {
  selectedAnswer.value = index
  if (!chat.messages[index]?.id) {
    try { await chat.save(chat.sessionName || `支持会话 ${crypto.randomUUID().slice(0, 8)}`) }
    catch (e) { ElMessage.error((e as Error).message); return }
  }
  ticketQuestion.value = chat.messages.slice(0, index).reverse().find(m => m.role === 'user')?.content || '需要人工协助'
  panel.close()
  ticketOpen.value = true
}
async function rate(index: number, rating: FeedbackRating) {
  const message = chat.messages[index]
  if (!message?.id) return
  selectedAnswer.value = index
  if (rating === 'unresolved') {
    feedbackReason.value = message.feedback?.reason || ''; feedbackError.value = ''; feedbackOpen.value = true
    return
  }
  try { message.feedback = await rateAnswer(message.id, rating); ElMessage.success('感谢反馈') }
  catch (e) { ElMessage.error((e as Error).message) }
}
async function submitUnresolved(createTicket = false) {
  const message = chat.messages[selectedAnswer.value]
  if (!message?.id || feedbackBusy.value) return
  feedbackBusy.value = true; feedbackError.value = ''
  try {
    message.feedback = await rateAnswer(message.id, 'unresolved', feedbackReason.value)
    feedbackOpen.value = false
    ElMessage.success('未解决反馈已记录')
    if (createTicket) await prepareTicket(selectedAnswer.value)
  } catch (e) { feedbackError.value = (e as Error).message }
  finally { feedbackBusy.value = false }
}
function ticketCreated(id: string) { void router.push(`/tickets/${id}`) }

</script>

<template>
  <div class="chat" :class="{ 'chat--empty': !chat.messages.length }">
    <header class="chat__head">
      <div class="chat__identity"><span class="assistant-dot" /><span class="chat__title">{{ title }}</span><span v-if="!chat.messages.length" class="assistant-tag">产品知识 · 问题协作</span></div>
      <div class="chat__tools"><el-button v-if="chat.messages.length" text circle aria-label="重命名对话" :disabled="chat.streaming || loadingSession" @click="saveCurrent"><el-icon><EditPen /></el-icon></el-button><el-button v-if="chat.messages.length" text circle aria-label="开始新对话" @click="clearAll"><el-icon><Plus /></el-icon></el-button></div>
    </header>
    <div ref="scroller" v-loading="loadingSession" class="chat__body">
      <div v-if="!chat.messages.length" class="chat__welcome">
        <div class="welcome-mark">知<span>✦</span></div>
        <h1>有什么可以帮你？</h1>
        <p>从一个问题开始，让知识成为解决问题的下一步。</p>
      </div>
      <div v-else class="chat__list">
        <MessageItem v-for="(msg, index) in chat.messages" :key="index" :message="msg" :can-regenerate="index === chat.messages.length - 1 && !chat.streaming && (!msg.run || msg.run.status === 'completed')" @regenerate="regenerate" @feedback="rate(index, $event)" @ticket="prepareTicket(index)" />
      </div>
    </div>
    <footer class="chat__composer">
      <el-alert v-if="chat.error" :title="chat.error" type="error" :closable="false" class="connection-error" />
      <div class="composer">
        <el-input v-model="input" aria-label="向智能助手提问" maxlength="4000" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none" placeholder="提问，或者描述你遇到的问题…" :disabled="chat.streaming || loadingSession" @keydown.enter.exact="inputKey" />
        <div class="composer__bottom"><ScopePicker v-model="chat.scope" compact :disabled="chat.messages.length > 0 || chat.streaming || loadingSession" /><span class="composer__shortcut">Enter 发送</span><el-button v-if="chat.streaming" class="composer__send" circle aria-label="停止回复" @click="chat.stop()"><el-icon><VideoPause /></el-icon></el-button><el-button v-else class="composer__send" type="primary" circle aria-label="发送消息" :disabled="!input.trim() || loadingSession" @click="send()"><el-icon><Top /></el-icon></el-button></div>
      </div>
      <p class="composer__hint">{{ chat.messages.length ? '对话自动保存 · Shift + Enter 换行 · 新对话可切换产品' : '查询产品资料、参考相似工单，或整理一个待处理的问题' }}</p>
      <div v-if="!chat.messages.length" class="welcome-examples"><button v-for="item in examples" :key="item.title" type="button" class="example-card" :disabled="loadingSession" @click="input = item.question"><el-icon><component :is="item.icon" /></el-icon><strong>{{ item.title }}</strong><span>{{ item.description }}</span><span class="example-arrow">↗</span></button></div>
      <p v-if="!chat.messages.length" class="welcome-note">回答可追溯来源，工单由你确认后提交</p>
    </footer>
    <TicketCreateDialog v-model="ticketOpen" :conversation-name="chat.sessionName" :message-id="chat.messages[selectedAnswer]?.id" :question="ticketQuestion" :scope="chat.scope" @created="ticketCreated" />
    <el-dialog v-model="feedbackOpen" title="反馈未解决的问题" width="540px" :close-on-click-modal="!feedbackBusy"><el-alert v-if="feedbackError" :title="feedbackError" type="error" :closable="false" /><el-input v-model="feedbackReason" type="textarea" :rows="4" maxlength="1000" placeholder="哪些内容没有解决问题？可以补充报错或缺失的信息（可选）" /><template #footer><el-button :loading="feedbackBusy" @click="submitUnresolved()">提交反馈</el-button><el-button type="primary" :loading="feedbackBusy" @click="submitUnresolved(true)">提交并转工单</el-button></template></el-dialog>
  </div>
</template>
<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; overflow: hidden; background: white; }
.chat__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; height: 72px; padding: 0 36px; flex-shrink: 0; }.chat__identity { display: flex; align-items: center; gap: 9px; min-width: 0; }.assistant-dot { width: 7px; height: 7px; background: #9e89d9; border-radius: 50%; flex-shrink: 0; }.chat__title { font-size: 13px; font-weight: 500; color: #645b70; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }.assistant-tag { font-size: 10px; color: #aaa0b7; white-space: nowrap; padding-left: 10px; border-left: 1px solid #eae5f1; }.chat__tools { display: flex; flex-shrink: 0; }
.chat__body { flex: 1; min-height: 0; overflow-y: auto; padding: 0 44px; scroll-behavior: smooth; }.chat__list { max-width: 820px; margin: 0 auto; padding: 14px 0 30px; }.chat__composer { flex-shrink: 0; padding: 12px 44px 18px; }.composer { max-width: 820px; margin: 0 auto; border: 1px solid #e5deee; border-radius: 22px; background: #fff; box-shadow: 0 5px 24px #52416b08; padding: 14px 16px 12px; transition: border-color .2s, box-shadow .2s; }.composer:focus-within { border-color: #b7a6dc; box-shadow: 0 5px 24px #8061a812; }.composer :deep(.el-textarea__inner) { padding: 4px 3px 12px; font-family: inherit; font-size: 15px; line-height: 1.8; box-shadow: none; background: transparent; color: #4c405c; }.composer :deep(.el-textarea__inner::placeholder) { color: #b0a6ba; }.composer__bottom { display: flex; align-items: center; gap: 8px; }.composer__shortcut { margin-left: auto; font-size: 10px; color: #b6acbf; white-space: nowrap; }.composer__send { width: 34px; height: 34px; flex-shrink: 0; font-size: 19px; }.composer__hint { text-align: center; font-size: 11px; color: #9688a3; margin: 10px auto 0; }.connection-error { max-width: 820px; margin: 0 auto 12px; }
.chat--empty .chat__body { flex: 0 0 auto; margin-top: clamp(28px, 10vh, 110px); overflow: visible; }.chat--empty .chat__composer { padding-top: 28px; overflow-y: auto; }.chat--empty .composer { max-width: 710px; }.chat__welcome { text-align: center; }.welcome-mark { position: relative; display: grid; place-items: center; margin: 0 auto 24px; width: 55px; height: 55px; border-radius: 18px; background: #f2ecfb; font-size: 27px; color: #8b71bd; transform: rotate(-6deg); }.welcome-mark span { position: absolute; top: -8px; right: -8px; font-size: 23px; color: #b29bd6; }.chat__welcome h1 { font-size: clamp(25px, 2.5vw, 32px); font-weight: 500; color: #51415e; letter-spacing: -.04em; }.chat__welcome p { font-size: 14px; color: #8a7c97; margin-top: 12px; }.welcome-examples { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; max-width: 710px; margin: 32px auto 0; }.example-card { position: relative; display: flex; flex-direction: column; align-items: flex-start; text-align: left; border: 1px solid #eee9f3; background: #fdfcfe; border-radius: 14px; padding: 17px; font-family: inherit; cursor: pointer; transition: background .15s, transform .15s; }.example-card:hover { background: #f8f4fc; transform: translateY(-2px); }.example-card .el-icon { font-size: 18px; color: #a08bba; margin-bottom: 13px; }.example-card strong { font-size: 13px; font-weight: 500; color: #796688; }.example-card > span:not(.example-arrow) { font-size: 11px; color: #9686a3; margin-top: 6px; }.example-arrow { position: absolute; top: 14px; right: 15px; color: #beb1ca; }.welcome-note { margin-top: 30px; text-align: center; font-size: 11px; letter-spacing: .03em; color: #9e90aa; }
@media(max-width: 760px) { .chat__head { height: 48px; padding: 0 18px; }.assistant-tag { display: none; }.chat__body { padding: 0 18px; }.chat__composer { padding: 10px 16px 14px; }.chat--empty .chat__body { margin-top: clamp(15px, 5vh, 60px); }.chat--empty .chat__composer { padding-top: 24px; }.chat__welcome p { font-size: 12px; }.welcome-mark { margin-bottom: 18px; }.welcome-examples { gap: 8px; margin-top: 24px; }.example-card { padding: 13px 10px; }.example-card > span:not(.example-arrow) { display: none; }.example-card strong { font-size: 11px; }.example-card .el-icon { margin-bottom: 10px; }.example-arrow { display: none; }.welcome-note { margin-top: 22px; }.composer { border-radius: 18px; padding: 12px; }.composer__shortcut { display: none; }.composer__send { margin-left: auto; }.composer__hint { font-size: 10px; } }
@media(max-height: 720px) { .chat--empty .chat__body { margin-top: 10px; }.welcome-mark { margin-bottom: 12px; }.welcome-examples { margin-top: 18px; }.welcome-note { margin-top: 14px; } }
</style>
