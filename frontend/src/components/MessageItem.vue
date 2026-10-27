<script setup lang="ts">
import { computed } from 'vue'
import { CopyDocument, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import SourcePanel from './SourcePanel.vue'
import type { ChatMessage } from '@/types'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ (e: 'regenerate'): void }>()

const isUser = computed(() => props.message.role === 'user')

// markdown-it 已关闭原始 HTML（html: false），模型输出中的标签会被转义，
// 因此这里的 v-html 只承载受控的 Markdown 渲染结果。
const html = computed(() => renderMarkdown(props.message.content))

const waiting = computed(
  () => props.message.streaming && !props.message.content && !props.message.error,
)

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
            <span class="msg__waiting-text">正在检索知识库…</span>
          </div>
          <div v-else class="md-body" v-html="html" />
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

      <div v-if="!message.streaming" class="msg__actions">
        <el-button link size="small" @click="copyContent">
          <el-icon><CopyDocument /></el-icon>
          <span>复制</span>
        </el-button>
        <el-button v-if="!isUser" link size="small" @click="emit('regenerate')">
          <el-icon><Refresh /></el-icon>
          <span>重新生成</span>
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  gap: 12px;
  padding: 6px 0;
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
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  color: #fff;
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
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
}

.msg--user .msg__bubble {
  background: var(--brand-600);
  border-color: var(--brand-600);
  color: #fff;
}

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
  opacity: 0;
  transition: opacity 0.15s ease;
}

.msg:hover .msg__actions {
  opacity: 1;
}

.msg--user .msg__actions {
  justify-content: flex-end;
}
</style>
