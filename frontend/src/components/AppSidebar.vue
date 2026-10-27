<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  Clock,
  Files,
  Refresh,
} from '@element-plus/icons-vue'

import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const settings = useSettingsStore()
const library = useLibraryStore()

const navItems = [
  { name: 'chat', path: '/chat', label: '智能问答', desc: '检索增强生成', icon: ChatDotRound },
  { name: 'documents', path: '/documents', label: '文档管理', desc: '上传与入库', icon: Files },
  { name: 'history', path: '/history', label: '对话历史', desc: '保存与导出', icon: Clock },
]

const advancedOpen = ref<string[]>([])

const embeddingModel = computed(() => settings.config?.embedding_model ?? '加载中…')
const embeddingDimension = computed(() => settings.config?.embedding_dimension)
const collectionSpace = computed(() => library.stats.space || '—')
const llmHint = computed(() =>
  settings.llmReady ? '已配置，可直接提问' : '未配置，请填写 API Key',
)
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <div class="brand-mark">知</div>
      <div class="brand-text">
        <div class="brand-title">知识库</div>
        <div class="brand-sub">RAG 智能问答</div>
      </div>
    </div>

    <nav class="sidebar__nav">
      <router-link
        v-for="item in navItems"
        :key="item.name"
        :to="item.path"
        class="nav-item"
        :class="{ 'nav-item--active': route.name === item.name }"
      >
        <el-icon class="nav-item__icon"><component :is="item.icon" /></el-icon>
        <span class="nav-item__body">
          <span class="nav-item__label">{{ item.label }}</span>
          <span class="nav-item__desc">{{ item.desc }}</span>
        </span>
      </router-link>
    </nav>

    <div class="sidebar__scroll">
      <section class="panel">
        <div class="panel__head">
          <span class="section-label">知识库状态</span>
          <el-button
            link
            size="small"
            :loading="library.loading"
            @click="library.refresh()"
          >
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>

        <div class="stat-grid">
          <div class="stat">
            <div class="stat__value">{{ library.stats.total_chunks }}</div>
            <div class="stat__label">文档块</div>
          </div>
          <div class="stat">
            <div class="stat__value">{{ library.stats.sources }}</div>
            <div class="stat__label">文件</div>
          </div>
        </div>

        <div class="meta-line">
          <span>向量空间</span>
          <code>{{ collectionSpace }}</code>
        </div>
        <div class="meta-line">
          <span>嵌入模型</span>
          <code :title="embeddingModel">{{ embeddingModel }}</code>
        </div>
        <div v-if="embeddingDimension" class="meta-line">
          <span>向量维度</span>
          <code>{{ embeddingDimension }}</code>
        </div>
      </section>

      <section class="panel">
        <div class="panel__head">
          <span class="section-label">检索与生成</span>
          <el-button link size="small" @click="settings.resetRag()">重置</el-button>
        </div>

        <div class="field">
          <div class="field__row">
            <span>检索数量 Top-K</span>
            <b>{{ settings.rag.topK }}</b>
          </div>
          <el-slider v-model="settings.rag.topK" :min="1" :max="20" :show-tooltip="false" />
        </div>

        <div class="field">
          <div class="field__row">
            <span>相似度阈值</span>
            <b>{{ settings.rag.similarityThreshold.toFixed(2) }}</b>
          </div>
          <el-slider
            v-model="settings.rag.similarityThreshold"
            :min="0"
            :max="1"
            :step="0.05"
            :show-tooltip="false"
          />
          <p class="field__hint">低于该值的片段会被丢弃，0 表示不过滤</p>
        </div>

        <div class="field">
          <div class="field__row">
            <span>生成温度</span>
            <b>{{ settings.rag.temperature.toFixed(2) }}</b>
          </div>
          <el-slider
            v-model="settings.rag.temperature"
            :min="0"
            :max="1.5"
            :step="0.05"
            :show-tooltip="false"
          />
          <p class="field__hint">越低越保守严谨，越高越有创造性</p>
        </div>
      </section>

      <el-collapse v-model="advancedOpen" class="sidebar__collapse">
        <el-collapse-item name="chunk">
          <template #title>
            <span class="section-label">分块参数</span>
          </template>

          <div class="field">
            <div class="field__row">
              <span>块大小（字符）</span>
              <b>{{ settings.rag.chunkSize }}</b>
            </div>
            <el-input-number
              v-model="settings.rag.chunkSize"
              :min="100"
              :max="3000"
              :step="50"
              size="small"
              controls-position="right"
              style="width: 100%"
            />
          </div>

          <div class="field">
            <div class="field__row">
              <span>重叠（字符）</span>
              <b>{{ settings.rag.chunkOverlap }}</b>
            </div>
            <el-input-number
              v-model="settings.rag.chunkOverlap"
              :min="0"
              :max="500"
              :step="20"
              size="small"
              controls-position="right"
              style="width: 100%"
            />
            <p class="field__hint">仅在重新上传文档时生效</p>
          </div>
        </el-collapse-item>

        <el-collapse-item name="llm">
          <template #title>
            <span class="section-label">模型配置</span>
          </template>

          <div class="field">
            <div class="field__row"><span>API Key</span></div>
            <el-input
              v-model="settings.llm.apiKey"
              type="password"
              size="small"
              show-password
              placeholder="留空则使用后端 .env"
            />
            <p class="field__hint">{{ llmHint }}，仅保存在本机浏览器</p>
          </div>

          <div class="field">
            <div class="field__row"><span>API Base URL</span></div>
            <el-input
              v-model="settings.llm.apiBaseUrl"
              size="small"
              placeholder="https://api.deepseek.com"
            />
          </div>

          <div class="field">
            <div class="field__row"><span>对话模型</span></div>
            <el-input
              v-model="settings.llm.chatModel"
              size="small"
              placeholder="deepseek-v4-flash"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
  flex-shrink: 0;
  height: 100vh;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 18px 14px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--brand-500), var(--brand-700));
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}

.brand-title {
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.brand-sub {
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 10px 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-item:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
  text-decoration: none;
}

.nav-item--active {
  background: var(--brand-50);
  color: var(--brand-700);
}

.nav-item__icon {
  font-size: 16px;
  flex-shrink: 0;
}

.nav-item__body {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.nav-item__label {
  font-size: 13.5px;
  font-weight: 500;
}

.nav-item__desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

.nav-item--active .nav-item__desc {
  color: var(--brand-500);
}

.sidebar__scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 20px;
  border-top: 1px solid var(--border-subtle);
}

.panel {
  padding: 14px 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
}

.stat {
  padding: 8px 10px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.stat__value {
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat__label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.meta-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 0;
  font-size: 11.5px;
  color: var(--text-secondary);
}

.meta-line code {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-tertiary);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field {
  margin-bottom: 14px;
}

.field:last-child {
  margin-bottom: 0;
}

.field__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.field__row b {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.field__hint {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-tertiary);
}

.sidebar__collapse {
  border: none;
}

.sidebar__collapse :deep(.el-collapse-item__header) {
  height: 44px;
  padding: 0 8px;
  border-bottom: none;
  background: transparent;
}

.sidebar__collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}

.sidebar__collapse :deep(.el-collapse-item__content) {
  padding: 0 8px 12px;
}

.sidebar__collapse :deep(.el-collapse) {
  border: none;
}
</style>
