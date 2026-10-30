<script setup lang="ts">
import { computed, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
const settings = useSettingsStore()
const library = useLibraryStore()
const auth = useAuthStore()
const advancedOpen = ref<string[]>([])

const embeddingModel = computed(() => settings.config?.embedding_model ?? '加载中…')
const embeddingDimension = computed(() => settings.config?.embedding_dimension)
const collectionSpace = computed(() => library.stats.space || '—')
const llmHint = computed(() =>
  settings.llmReady ? '模型已就绪' : '模型尚未配置，请联系管理员',
)

</script>
<template><div class="preferences">
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

        <div v-if="auth.isStaff" class="meta-line">
          <span>向量空间</span>
          <code>{{ collectionSpace }}</code>
        </div>
        <div v-if="auth.isStaff" class="meta-line">
          <span>嵌入模型</span>
          <code :title="embeddingModel">{{ embeddingModel }}</code>
        </div>
        <div v-if="auth.isStaff && embeddingDimension" class="meta-line">
          <span>向量维度</span>
          <code>{{ embeddingDimension }}</code>
        </div>
      </section>

      <section v-if="auth.isStaff" class="panel">
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

      <el-collapse v-if="auth.isStaff" v-model="advancedOpen" class="sidebar__collapse">
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
            <div class="field__row"><span>对话模型</span><b>{{ settings.config?.chat_model || '—' }}</b></div>
            <p class="field__hint">{{ llmHint }}。模型配置由团队管理员统一维护。</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div></template>
<style scoped>
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

.preferences { padding: 0 24px 24px; } .panel { margin-bottom: 24px; }
</style>
