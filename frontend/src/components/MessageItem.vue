<script setup lang="ts">
import { computed } from 'vue'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import SourcePanel from './SourcePanel.vue'
import AssistantTurn from './AssistantTurn.vue'
import type { ChatMessage, FeedbackRating } from '@/types'
import { renderAnswerMarkdown } from '@/utils/markdown'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{ message: ChatMessage; canRegenerate?: boolean }>()
const emit = defineEmits<{ (e: 'regenerate'): void; (e: 'feedback', rating: FeedbackRating): void; (e: 'ticket'): void }>()

const isUser = computed(() => props.message.role === 'user')

// markdown-it 已关闭原始 HTML（html: false），模型输出中的标签会被转义，
// 因此这里的 v-html 只承载受控的 Markdown 渲染结果。
const panel = useWorkspaceStore()
const html = computed(() => renderAnswerMarkdown(props.message.content, props.message.contexts?.length ?? 0))
function openCitation(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-source-index]')
  if (!target) return
  const index = Number(target.dataset.sourceIndex)
  if (Number.isInteger(index) && props.message.contexts?.[index]) panel.openSources(props.message.contexts, props.message.sources, index)
}

const waiting = computed(
  () => props.message.streaming && !props.message.content && !props.message.error,
)
const waitingText = computed(() => {
  const steps = props.message.run?.steps ?? []
  if (steps.some(step => ['general_chat', 'get_assistant_info'].includes(step.name))) return '正在组织回复…'
  return steps.length ? '正在查询资料或处理问题…' : '正在理解你的问题…'
})

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文本')
  }
}
</script>

<template>
  <div class="msg" :class="isUser ? 'msg--user' : 'msg--assistant'">
    <div class="msg__avatar" :class="isUser ? 'msg__avatar--user' : 'msg__avatar--ai'">
      {{ isUser ? '我' : 'AI' }}
    </div>

    <div class="msg__main">
      <div class="msg__bubble">
        <div v-if="isUser" class="msg__plain">{{ message.content }}</div>

        <template v-else>
          <div v-if="waiting" class="msg__waiting">
            <span class="dot" />
            <span class="dot" />
            <span class="dot" />
            <span class="msg__waiting-text">{{ waitingText }}</span>
          </div>
          <div v-else class="md-body" @click="openCitation" v-html="html" />
          <span v-if="message.streaming && message.content" class="stream-caret" />
        </template>
      </div>

      <el-alert
        v-if="message.error"
        type="error"
        :closable="false"
        show-icon
        class="msg__error"
        :title="message.error"
      />

      <SourcePanel
        v-if="!isUser && !message.streaming"
        :sources="message.sources"
        :contexts="message.contexts"
      />
      <AssistantTurn v-if="!isUser && message.run" :run="message.run" />
      <details v-if="!isUser && message.retrieval && message.retrieval.status !== 'not_needed'" class="retrieval-trace">
        <summary>{{ message.retrieval.status === 'fallback' ? '已使用原始问题检索' : '本轮检索问题' }}</summary>
        <p>{{ message.retrieval.query }}</p>
      </details>

      <div v-if="!message.streaming" class="msg__actions">
        <el-button link size="small" @click="copyContent">
          <el-icon><CopyDocument /></el-icon>
          <span>复制</span>
        </el-button>
        <el-button v-if="!isUser && canRegenerate" link size="small" @click="emit('regenerate')">
          <el-icon><Refresh /></el-icon>
          <span>重新生成</span>
        </el-button>
        <template v-if="!isUser && message.content && !message.error && (!message.run || (message.run.status === 'completed' && !message.run.result.needs_input))">
          <el-button v-if="message.id" link size="small" :type="message.feedback?.rating === 'helpful' ? 'success' : 'default'" @click="emit('feedback', 'helpful')">{{ message.feedback?.rating === 'helpful' ? '已标记有帮助' : '有帮助' }}</el-button>
          <el-button v-if="message.id" link size="small" :type="message.feedback?.rating === 'unresolved' ? 'warning' : 'default'" @click="emit('feedback', 'unresolved')">{{ message.feedback?.rating === 'unresolved' ? '已反馈未解决' : '未解决' }}</el-button>
          <el-button v-if="!message.run?.ticket_id" link type="primary" size="small" @click="emit('ticket')">转为工单</el-button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.retrieval-trace { margin-top: 10px; color: var(--text-secondary); font-size: 12px; }
.msg {
  display: flex;
  gap: 12px;
  padding: 18px 0;
}

.msg--user {
  flex-direction: row-reverse;
}

.msg__avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  user-select: none;
}

.msg__avatar--user {
  background: var(--bg-page);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.msg__avatar--ai {
  background: #f1edfb;
  color: var(--brand-600);
}

.msg__main {
  min-width: 0;
  max-width: 100%;
}

.msg--user .msg__main {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.msg__bubble {
  padding: 0 0 8px;
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  border: 0;
}

.msg--user .msg__bubble {
  padding: 12px 18px;
  background: #f1eef9;
  color: #51465f;
  border-radius: 18px 5px 18px 18px;
}
.msg--user .msg__avatar { display: none; }
.msg--user .msg__main { max-width: 85%; }.msg--assistant .msg__main { flex: 1; }.msg--assistant :deep(.md-body) { font-size: 15px; line-height: 1.9; }.msg--user .msg__actions { margin-top: 3px; }.msg__actions :deep(.el-button) { font-size: 11px; color: #91869e; }.msg__actions :deep(.el-button:hover) { color: var(--brand-600); }

.msg__plain {
  font-size: 14.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg__waiting {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
}

.msg__waiting-text {
  margin-left: 6px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-500);
  animation: dot-pulse 1.2s ease-in-out infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.15s;
}

.dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes dot-pulse {
  0%,
  60%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

.msg__error {
  margin-top: 10px;
}

.msg__actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
  flex-wrap: wrap;
  opacity: 1;
  transition: opacity 0.15s ease;
}

.msg:hover .msg__actions {
  opacity: 1;
}

.msg--user .msg__actions {
  justify-content: flex-end;
}
</style>
