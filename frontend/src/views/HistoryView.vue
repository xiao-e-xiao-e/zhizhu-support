<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Delete, Download, FolderOpened, Refresh } from '@element-plus/icons-vue'

import * as api from '@/api'
import { useChatStore } from '@/stores/chat'
import { useConversationsStore } from '@/stores/conversations'
import type { SessionSummary } from '@/types'

const router = useRouter()
const chat = useChatStore()

const sessions = ref<SessionSummary[]>([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    sessions.value = await api.listSessions()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function loadSession(name: string) {
  try {
    const detail = await api.getSession(name)
    chat.loadSession(name, detail.messages, { product_id: detail.product_id ?? null, version_id: detail.version_id ?? null })
    ElMessage.success(`已加载「${name}」`)
    router.push({path: '/assistant', query: {session: name}})
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function removeSession(name: string) {
  try {
    await ElMessageBox.confirm(`确定删除会话「${name}」吗？历史记录无法恢复，已提交到工单或反馈中的对话副本会保留。`, '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.deleteSession(name)
    if (chat.sessionName === name) chat.clear()
    void useConversationsStore().refresh()
    ElMessage.success('已删除')
    await refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function exportSession(name: string) {
  window.open(api.sessionExportUrl(name), '_blank')
}

function formatTime(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="head">
        <div>
          <h1 class="page-title">对话历史</h1>
          <p class="page-desc">
            查看和继续自己的历史会话，也可以导出为 Markdown
          </p>
        </div>
        <el-button :loading="loading" @click="refresh">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
      </header>

      <div v-if="sessions.length" class="grid">
        <article v-for="item in sessions" :key="item.name" class="session card">
          <div class="session__top">
            <div class="session__icon">
              <el-icon><Clock /></el-icon>
            </div>
            <div class="session__meta">
              <h3 class="session__name">{{ item.name }}</h3>
              <div class="session__sub">
                <span>{{ item.message_count }} 条消息</span>
                <span class="dot-sep">·</span>
                <span>{{ formatTime(item.updated_at) }}</span>
              </div>
            </div>
          </div>

          <div class="session__actions">
            <el-button size="small" type="primary" plain @click="loadSession(item.name)">
              继续对话
            </el-button>
            <el-button size="small" @click="exportSession(item.name)">
              <el-icon><Download /></el-icon>
              <span>导出</span>
            </el-button>
            <el-button size="small" type="danger" plain @click="removeSession(item.name)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </article>
      </div>

      <div v-else class="card empty-state">
        <el-icon :size="26"><FolderOpened /></el-icon>
        <div class="empty-state__title">还没有保存过对话</div>
        <div class="empty-state__hint">
          在「智能助手」中开始对话，记录会自动保存在这里
        </div>
        <el-button type="primary" plain style="margin-top: 8px" @click="router.push('/assistant')">
          去提问
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.session {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  transition: box-shadow 0.18s ease, border-color 0.18s ease;
}

.session:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
}

.session__top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.session__icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 9px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 15px;
}

.session__meta {
  min-width: 0;
}

.session__name {
  font-size: 14.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session__sub {
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.dot-sep {
  margin: 0 5px;
}

.session__actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>
