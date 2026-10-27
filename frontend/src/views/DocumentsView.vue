<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { Delete, Document, Search, UploadFilled, View } from '@element-plus/icons-vue'

import * as api from '@/api'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import type { ChunkHit } from '@/types'

const library = useLibraryStore()
const settings = useSettingsStore()

const pendingFiles = ref<File[]>([])
const previewText = ref('')
const previewInfo = ref('')
const previewLoading = ref(false)

const chunkDrawer = ref(false)
const chunkRows = ref<{ chunk_index: number; content: string }[]>([])
const chunkTitle = ref('')

const searchQuery = ref('')
const searchResults = ref<ChunkHit[]>([])
const searching = ref(false)

const totalChunks = computed(() => library.stats.total_chunks)

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function handleFileChange(file: UploadFile) {
  const raw = file.raw
  if (!raw) return
  pendingFiles.value = [
    ...pendingFiles.value.filter((item) => item.name !== raw.name),
    raw,
  ]
}

function dropFile(name: string) {
  pendingFiles.value = pendingFiles.value.filter((item) => item.name !== name)
}

async function doPreview() {
  const first = pendingFiles.value[0]
  if (!first) return
  previewLoading.value = true
  try {
    const result = await api.previewDocument(first, 2000)
    previewText.value = result.text
    previewInfo.value = `${result.filename} · 共 ${result.characters} 字符${
      result.truncated ? '（仅显示前 2000）' : ''
    }`
  } catch (e) {
    ElMessage.error((e as Error).message)
    previewText.value = ''
  } finally {
    previewLoading.value = false
  }
}

async function doUpload() {
  if (!pendingFiles.value.length) return
  try {
    const result = await library.upload(
      pendingFiles.value,
      settings.rag.chunkSize,
      settings.rag.chunkOverlap,
    )

    if (result.failed > 0) {
      ElMessage.warning(
        `入库完成：新增 ${result.total_chunks} 个文本块，${result.failed} 个文件失败`,
      )
      result.results
        .filter((item) => !item.ok)
        .forEach((item) => ElMessage.error(`${item.filename}：${item.error}`))
    } else {
      ElMessage.success(
        `入库完成，${result.results.length} 个文件共新增 ${result.total_chunks} 个文本块`,
      )
    }

    pendingFiles.value = []
    previewText.value = ''
    previewInfo.value = ''
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function viewChunks(source: string) {
  try {
    chunkRows.value = await library.loadChunks(source)
    chunkTitle.value = source
    chunkDrawer.value = true
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function removeDoc(source: string) {
  try {
    await ElMessageBox.confirm(
      `删除后「${source}」的全部分块会从向量库移除，确定继续吗？`,
      '删除文档',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await library.remove(source)
    ElMessage.success(`已删除 ${source}`)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function doSearch() {
  const query = searchQuery.value.trim()
  if (!query) return
  searching.value = true
  try {
    searchResults.value = await api.searchDocuments(
      query,
      settings.rag.topK,
      settings.rag.similarityThreshold,
    )
    if (!searchResults.value.length) {
      ElMessage.info('没有命中片段，可以试试调低侧栏的相似度阈值')
    }
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    searching.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="head">
        <div>
          <h1 class="page-title">文档管理</h1>
          <p class="page-desc">
            支持 PDF、DOCX、HTML、CSV、Markdown、TXT 与常见代码文件；
            上传后按段落边界切分并编码为语义向量
          </p>
        </div>
        <div class="head__stats">
          <div class="head__stat">
            <b>{{ totalChunks }}</b>
            <span>文本块</span>
          </div>
          <div class="head__stat">
            <b>{{ library.stats.sources }}</b>
            <span>文件</span>
          </div>
        </div>
      </header>

      <section class="card block">
        <el-upload
          drag
          multiple
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileChange"
          accept=".pdf,.docx,.html,.htm,.csv,.md,.markdown,.txt,.py,.js,.ts,.json,.yaml,.yml"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">把文件拖到这里，或<em>点击选择</em></div>
          <div class="upload-hint">
            单个文件失败不影响其他文件；同名文件会覆盖旧版本
          </div>
        </el-upload>

        <div v-if="pendingFiles.length" class="pending">
          <div class="pending__head">
            <span class="section-label">待入库 {{ pendingFiles.length }} 个文件</span>
            <div class="pending__actions">
              <el-button
                size="small"
                :loading="previewLoading"
                @click="doPreview"
              >
                <el-icon><View /></el-icon>
                <span>解析预览</span>
              </el-button>
              <el-button
                type="primary"
                size="small"
                :loading="library.uploading"
                @click="doUpload"
              >
                <el-icon><UploadFilled /></el-icon>
                <span>解析并入库</span>
              </el-button>
            </div>
          </div>

          <div class="file-list">
            <div v-for="file in pendingFiles" :key="file.name" class="file-row">
              <el-icon class="file-row__icon"><Document /></el-icon>
              <span class="file-row__name">{{ file.name }}</span>
              <span class="file-row__size">{{ formatSize(file.size) }}</span>
              <el-button link size="small" @click="dropFile(file.name)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>

          <div v-if="previewText" class="preview">
            <div class="preview__head">{{ previewInfo }}</div>
            <pre class="preview__body">{{ previewText }}</pre>
          </div>
        </div>

        <p class="chunk-hint">
          当前分块参数：块大小 {{ settings.rag.chunkSize }} 字符 · 重叠
          {{ settings.rag.chunkOverlap }} 字符（可在左侧「分块参数」中调整）
        </p>
      </section>

      <section class="card block">
        <div class="block__head">
          <span class="section-label">已入库文档</span>
          <el-button link size="small" :loading="library.loading" @click="library.refresh()">
            刷新
          </el-button>
        </div>

        <el-table
          v-if="library.documents.length"
          :data="library.documents"
          style="width: 100%"
        >
          <el-table-column prop="source" label="文件名" min-width="240">
            <template #default="{ row }">
              <span class="doc-name">
                <el-icon><Document /></el-icon>
                {{ row.source }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="chunks" label="分块数" width="110" align="center" />
          <el-table-column label="操作" width="170" align="right">
            <template #default="{ row }">
              <el-button link size="small" @click="viewChunks(row.source)">
                查看分块
              </el-button>
              <el-button link type="danger" size="small" @click="removeDoc(row.source)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty-state">
          <el-icon :size="26"><Document /></el-icon>
          <div class="empty-state__title">知识库还是空的</div>
          <div class="empty-state__hint">
            上传第一份文档后，就可以到「智能问答」里基于它提问了
          </div>
        </div>
      </section>

      <section class="card block">
        <div class="block__head">
          <span class="section-label">快速检索</span>
        </div>
        <p class="block__desc">
          只做向量检索、不调用大模型，用来直观检查知识库里到底存了什么
        </p>

        <el-input
          v-model="searchQuery"
          placeholder="输入一句话或关键词，看看能召回哪些片段"
          clearable
          @keydown.enter="doSearch"
        >
          <template #append>
            <el-button :loading="searching" @click="doSearch">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>

        <div v-if="searchResults.length" class="search-results">
          <div v-for="hit in searchResults" :key="hit.id" class="search-hit">
            <div class="search-hit__head">
              <span class="search-hit__file">{{ hit.source }}</span>
              <span class="search-hit__index">片段 #{{ hit.chunk_index }}</span>
              <span class="search-hit__score">{{ hit.similarity.toFixed(3) }}</span>
            </div>
            <pre class="search-hit__body">{{ hit.content }}</pre>
          </div>
        </div>
      </section>
    </div>

    <el-drawer v-model="chunkDrawer" size="620px" :title="`分块预览 · ${chunkTitle}`">
      <div class="drawer-body">
        <div v-for="row in chunkRows" :key="row.chunk_index" class="drawer-chunk">
          <div class="drawer-chunk__head">
            片段 #{{ row.chunk_index }} · {{ row.content.length }} 字符
          </div>
          <pre class="drawer-chunk__body">{{ row.content }}</pre>
        </div>
      </div>
    </el-drawer>
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

.head__stats {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.head__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 82px;
  padding: 8px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.head__stat b {
  font-size: 19px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.head__stat span {
  font-size: 11px;
  color: var(--text-tertiary);
}

.block {
  padding: 20px 22px;
  margin-bottom: 20px;
}

.block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.block__desc {
  margin: -6px 0 12px;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

.block :deep(.el-upload-dragger) {
  padding: 30px 20px;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  transition: all 0.18s ease;
}

.block :deep(.el-upload-dragger:hover) {
  border-color: var(--brand-500);
  background: var(--brand-50);
}

.upload-icon {
  font-size: 32px;
  color: var(--brand-500);
}

.upload-text {
  margin-top: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.upload-text em {
  font-style: normal;
  color: var(--brand-600);
  font-weight: 500;
}

.upload-hint {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.pending {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.pending__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.pending__actions {
  display: flex;
  gap: 8px;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  font-size: 13px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.file-row__icon {
  color: var(--text-tertiary);
}

.file-row__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-row__size {
  font-size: 11.5px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.preview {
  margin-top: 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.preview__head {
  padding: 7px 12px;
  font-size: 11.5px;
  color: var(--text-tertiary);
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.preview__body {
  margin: 0;
  padding: 12px;
  max-height: 260px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
}

.chunk-hint {
  margin-top: 14px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.doc-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 12.5px;
}

.search-results {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-hit {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.search-hit__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  font-size: 12px;
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.search-hit__file {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-primary);
}

.search-hit__index {
  color: var(--text-tertiary);
}

.search-hit__score {
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--brand-600);
  font-weight: 500;
}

.search-hit__body {
  margin: 0;
  padding: 10px 12px;
  max-height: 220px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-chunk {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.drawer-chunk__head {
  padding: 6px 12px;
  font-size: 11.5px;
  color: var(--text-tertiary);
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.drawer-chunk__body {
  margin: 0;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
}
</style>
