<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, FolderOpened, Promotion, VideoPause } from '@element-plus/icons-vue'

import MessageItem from '@/components/MessageItem.vue'
import { useChatStore } from '@/stores/chat'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'

const router = useRouter()
const chat = useChatStore()
const library = useLibraryStore()
const settings = useSettingsStore()

const input = ref('')
const sessionDraft = ref('')
const scroller = ref<HTMLElement | null>(null)

const examples = [
  '这个知识库主要包含哪些内容？',
  'RAG 的分块策略是怎么设计的？',
  '帮我对比一下文档里提到的几种方案',
]

const hasDocuments = () => library.stats.total_chunks > 0

async function scrollToBottom() {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => chat.messages.length, scrollToBottom)
watch(
  () => chat.messages[chat.messages.length - 1]?.content,
  () => scrollToBottom(),
)

async function send(text?: string) {
  const question = (text ?? input.value).trim()
  if (!question || chat.streaming) return

  if (!hasDocuments()) {
    ElMessage.warning('知识库还是空的，请先到「文档管理」上传文档')
    return
  }

  input.value = ''
  await chat.send(question, {
    topK: settings.rag.topK,
    temperature: settings.rag.temperature,
    similarityThreshold: settings.rag.similarityThreshold,
    llm: settings.llmPayload,
    autoSave: Boolean(chat.sessionName),
  })
}

async function saveCurrent() {
  const name = sessionDraft.value.trim()
  if (!name) {
    ElMessage.warning('请先输入会话名称')
    return
  }
  if (!chat.messages.length) {
    ElMessage.warning('当前还没有对话内容')
    return
  }
  try {
    await chat.save(name)
    ElMessage.success(`已保存：${name}`)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function clearAll() {
  if (!chat.messages.length) return
  try {
    await ElMessageBox.confirm(
      '未保存的对话内容将丢失，确定清空吗？',
      '清空当前对话',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  chat.clear()
  sessionDraft.value = ''
}

async function regenerate() {
  const messages = chat.messages
  if (messages.length < 2) return
  const last = messages[messages.length - 1]
  const prev = messages[messages.length - 2]
  if (last.role !== 'assistant' || prev.role !== 'user') return

  const question = prev.content
  messages.splice(messages.length - 2, 2)
  await send(question)
}

function goDocuments() {
  router.push('/documents')
}
</script>

<template>
  <div class="chat">
    <header class="chat__head">
      <div>
        <h1 class="page-title">智能问答</h1>
        <p class="page-desc">基于已入库文档检索并生成回答，答案可溯源到具体片段</p>
      </div>

      <div class="chat__tools">
        <el-input
          v-model="sessionDraft"
          placeholder="会话名称（填写后自动保存）"
          clearable
          style="width: 220px"
        />
        <el-button :disabled="!chat.messages.length" @click="saveCurrent">
          保存
        </el-button>
        <el-button :disabled="!chat.messages.length" @click="clearAll">
          <el-icon><Delete /></el-icon>
        </el-button>
      </div>
    </header>

    <div ref="scroller" class="chat__body">
      <div v-if="!chat.messages.length" class="chat__welcome">
        <div class="welcome-card">
          <div class="welcome-mark">知</div>
          <h2 class="welcome-title">向你的知识库提问</h2>
          <p class="welcome-sub">
            系统会先在向量库中检索相关片段，再交由大模型基于这些片段作答，
            并在下方给出可展开的检索详情与相似度分数。
          </p>

          <div v-if="!hasDocuments()" class="welcome-alert">
            <el-icon><FolderOpened /></el-icon>
            <span>知识库当前为空，先去上传几份文档吧</span>
            <el-button type="primary" link @click="goDocuments">前往文档管理</el-button>
          </div>

          <div v-else class="welcome-examples">
            <span class="welcome-examples__label">试试这些问题</span>
            <button
              v-for="item in examples"
              :key="item"
              type="button"
              class="example-chip"
              @click="send(item)"
            >
              {{ item }}
            </button>
          </div>
        </div>
      </div>

      <div v-else class="chat__list">
        <MessageItem
          v-for="(msg, index) in chat.messages"
          :key="index"
          :message="msg"
          @regenerate="regenerate"
        />
      </div>
    </div>

    <footer class="chat__composer">
      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 6 }"
          resize="none"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          :disabled="chat.streaming"
          @keydown.enter.exact.prevent="send()"
        />
        <el-button
          v-if="chat.streaming"
          class="composer__btn"
          type="danger"
          plain
          @click="chat.stop()"
        >
          <el-icon><VideoPause /></el-icon>
          <span>停止</span>
        </el-button>
        <el-button
          v-else
          class="composer__btn"
          type="primary"
          :disabled="!input.trim()"
          @click="send()"
        >
          <el-icon><Promotion /></el-icon>
          <span>发送</span>
        </el-button>
      </div>
      <p class="composer__hint">
        当前参数：Top-K {{ settings.rag.topK }} · 温度
        {{ settings.rag.temperature.toFixed(2) }} · 阈值
        {{ settings.rag.similarityThreshold.toFixed(2) }}
      </p>
    </footer>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.chat__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-shrink: 0;
  padding: 18px 32px 16px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
}

.chat__tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.chat__body {
  flex: 1;
  overflow-y: auto;
  padding: 0 32px;
}

.chat__list {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 0 32px;
}

.chat__welcome {
  display: grid;
  place-items: center;
  min-height: 100%;
  padding: 40px 0;
}

.welcome-card {
  max-width: 560px;
  padding: 36px 36px 32px;
  text-align: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-sm);
}

.welcome-mark {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  margin: 0 auto 16px;
  border-radius: 13px;
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  color: #fff;
  font-size: 21px;
  font-weight: 600;
}

.welcome-title {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.welcome-sub {
  margin-top: 8px;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.welcome-alert {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 22px;
  padding: 10px 14px;
  font-size: 13px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius-md);
}

.welcome-examples {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 24px;
}

.welcome-examples__label {
  width: 100%;
  margin-bottom: 2px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.example-chip {
  padding: 7px 13px;
  font-family: inherit;
  font-size: 12.5px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.example-chip:hover {
  color: var(--brand-700);
  background: var(--brand-50);
  border-color: var(--brand-200);
}

.chat__composer {
  flex-shrink: 0;
  padding: 14px 32px 18px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border-subtle);
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 900px;
  margin: 0 auto;
}

.composer :deep(.el-textarea__inner) {
  padding: 10px 14px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 1px var(--border-default) inset;
}

.composer :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px var(--brand-500) inset;
}

.composer__btn {
  height: 40px;
  flex-shrink: 0;
}

.composer__hint {
  max-width: 900px;
  margin: 8px auto 0;
  font-size: 11.5px;
  color: var(--text-tertiary);
}
</style>
