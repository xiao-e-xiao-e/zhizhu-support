<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { Delete, Document, Search, UploadFilled, View } from '@element-plus/icons-vue'

import * as api from '@/api'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { useCatalogStore } from '@/stores/catalog'
import ScopePicker from '@/components/ScopePicker.vue'
import { http } from '@/api/client'
import type { ChunkHit, DocumentItem, KnowledgeScope, KnowledgeRevision, RevisionHistory } from '@/types'
import { useAuthStore } from '@/stores/auth'

const library = useLibraryStore()
const settings = useSettingsStore()
const catalog = useCatalogStore()
const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const workerOnline = ref<boolean | null>(null)
const versionsOpen = ref(false)
const selectedId = ref('')
const selected = computed(() => library.documents.find(d => d.id === selectedId.value))
const versions = ref<RevisionHistory>({ revision: 1, revisions: [], events: [] })
const actionBusy = ref(false)
const stateLabels: Record<string, string> = { queued: '等待入库', processing: '正在入库', ready: '待发布', published: '已发布', superseded: '历史发布', failed: '入库失败' }
const eventLabels: Record<string, string> = { upload: '上传修订', index_ready: '入库完成', index_failed: '入库失败', publish: '发布修订', withdraw: '撤回发布', archive: '归档', restore: '恢复', scope: '修改分类', retry: '重试任务', legacy_import: '旧资料登记' }
let timer: ReturnType<typeof setInterval> | undefined
let refreshing = false
let disposed = false

async function loadVersions() {
  if (selectedId.value) versions.value = (await http.get<RevisionHistory>(`/documents/${selectedId.value}/revisions`)).data
}
async function refresh() {
  if (refreshing || disposed) return
  refreshing = true
  try {
    await library.refresh()
    if (disposed) return
    workerOnline.value = (await http.get<{ worker_online: boolean }>('/documents/jobs')).data.worker_online
    if (versionsOpen.value) await loadVersions()
  } catch (e) { if (!disposed) ElMessage.error((e as Error).message) }
  finally { refreshing = false }
}
onMounted(() => { void refresh(); timer = setInterval(() => void refresh(), 4000) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
async function openVersions(doc: DocumentItem) {
  selectedId.value = doc.id
  try { await loadVersions(); versionsOpen.value = true }
  catch (e) { ElMessage.error((e as Error).message) }
}
async function changeDocument(action: string, revisionId?: string) {
  const doc = selected.value
  if (!doc || actionBusy.value) return
  if (['publish', 'withdraw', 'archive'].includes(action)) {
    try { await ElMessageBox.confirm(action === 'publish' ? '发布后，问答将立即使用此修订，并保留历史版本供回滚。' : action === 'archive' ? '归档后，此文档将立即退出问答检索。原始文件和历史修订保留。' : '撤回后，此文档将暂时退出问答检索。', '确认文档操作', { confirmButtonText: '确认', cancelButtonText: '取消' }) }
    catch { return }
  }
  actionBusy.value = true
  try {
    await http.post(`/documents/${doc.id}/${action}`, { revision: versions.value.revision, revision_id: revisionId ?? null })
    await library.refresh(); await loadVersions(); ElMessage.success('文档已更新')
  } catch (e) { ElMessage.error((e as Error).message); await refresh() }
  finally { actionBusy.value = false }
}
async function retryRevision(row: KnowledgeRevision) {
  if (!row.job) return
  actionBusy.value = true
  try { await http.post(`/documents/jobs/${row.job.id}/retry`); await library.refresh(); await loadVersions(); ElMessage.success('已重新排队') }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { actionBusy.value = false }
}
const scope = ref<KnowledgeScope>({ product_id: null, version_id: null })
const scopeOpen = ref(false)
const scopeDocument = ref('')
const editScope = ref<KnowledgeScope>({ product_id: null, version_id: null })
const scopeBusy = ref(false)

function scopeLabel(document: DocumentItem) {
  const product = catalog.products.find(p => p.id === document.product_id)
  return product ? `${product.name} ${product.versions.find(v => v.id === document.version_id)?.name || '全部版本'}` : '未分类'
}
function openScope(document: DocumentItem) {
  scopeDocument.value = document.id
  selectedId.value = document.id
  editScope.value = { product_id: document.product_id ?? null, version_id: document.version_id ?? null }
  scopeOpen.value = true
}
async function saveScope() {
  scopeBusy.value = true
  try { await http.patch(`/documents/${encodeURIComponent(scopeDocument.value)}/scope`, { ...editScope.value, revision: selected.value?.revision }); await library.refresh(); scopeOpen.value = false; ElMessage.success('文档分类已更新') }
  catch (e) { ElMessage.error((e as Error).message) }
  finally { scopeBusy.value = false }
}

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
      scope.value,
    )

    if (result.failed > 0) {
      ElMessage.warning(
        `已接受 ${result.results.length - result.failed} 个文件，${result.failed} 个文件提交失败`,
      )
      result.results
        .filter((item) => !item.ok)
        .forEach((item) => ElMessage.error(`${item.filename}：${item.error}`))
    } else {
      ElMessage.success(
        `已接受 ${result.results.length} 个文件，后台处理完成后请审核发布；相同内容自动去重`,
      )
    }

    pendingFiles.value = []
    previewText.value = ''
    previewInfo.value = ''
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function viewChunks(id: string, title: string, revisionId?: string) {
  try {
    chunkRows.value = (await http.get(`/documents/${id}/chunks`, { params: { revision_id: revisionId } })).data
    chunkTitle.value = title
    chunkDrawer.value = true
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
      scope.value,
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
            上传、后台处理、审核发布与历史回滚。问答仅使用已发布的修订。
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

      <el-alert v-if="workerOnline === false" title="后台处理进程暂未连接，已提交文件会保留在队列中；请联系管理员检查 worker。" type="warning" :closable="false" show-icon style="margin-bottom: 18px" />
      <el-alert v-if="library.error" :title="library.error" type="error" :closable="false" style="margin-bottom: 18px" />

      <section class="card block">
        <div class="document-scope"><span class="section-label">上传与检索范围</span><ScopePicker v-model="scope" /><p>相同分类和文件名创建连续修订；不同产品或版本可使用相同文件名。未选择范围时检索全部已发布资料。</p></div>
        <el-upload
          drag
          multiple
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileChange"
          accept=".pdf,.docx,.html,.htm,.csv,.md,.markdown,.txt"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">把文件拖到这里，或<em>点击选择</em></div>
          <div class="upload-hint">
            支持 PDF、DOCX、HTML、CSV、Markdown、TXT；最多 10 个文件，每个不超过 20 MB
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
                <span>提交后台入库</span>
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
          <span class="section-label">文档与修订</span>
          <el-button link size="small" :loading="library.loading" @click="refresh()">
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
          <el-table-column label="当前发布" width="110"><template #default="{ row }">{{ row.archived ? '已归档' : row.published_revision ? `修订 ${row.published_revision}` : '未发布' }}</template></el-table-column>
          <el-table-column label="最新修订" min-width="180"><template #default="{ row }"><div v-if="row.latest">#{{ row.latest.number }} · {{ stateLabels[row.latest.state] }}<p v-if="row.latest.job" class="chunk-hint">{{ row.latest.job.state === 'succeeded' ? '入库完成' : row.latest.job.phase }} · {{ row.latest.job.progress }}%</p></div></template></el-table-column>
          <el-table-column label="产品与版本" min-width="170"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column>
          <el-table-column label="操作" width="220" align="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openVersions(row)">版本管理</el-button>
              <el-button link size="small" :disabled="!!row.published_revision" @click="openScope(row)">分类</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty-state">
          <el-icon :size="26"><Document /></el-icon>
          <div class="empty-state__title">知识库还是空的</div>
          <div class="empty-state__hint">
            上传第一份文档，入库后由管理员审核发布，即可供智能助手查询
          </div>
        </div>
      </section>

      <section class="card block">
        <div class="block__head">
          <span class="section-label">快速检索</span>
        </div>
        <p class="block__desc">
          检索当前范围内的已发布资料，用来检查问答可用的证据
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
    <el-dialog v-model="scopeOpen" :title="`文档分类：${selected?.source ?? ''}`" width="560px"><p>已发布文档需要先撤回，才能修改分类。</p><ScopePicker v-model="editScope" /><template #footer><el-button :disabled="scopeBusy" @click="scopeOpen = false">取消</el-button><el-button type="primary" :loading="scopeBusy" @click="saveScope">保存分类</el-button></template></el-dialog>
    <el-dialog v-model="versionsOpen" :title="`版本管理 · ${selected?.source ?? ''}`" width="min(1080px, 95vw)">
      <p v-if="selected">{{ scopeLabel(selected) }} · {{ selected.archived ? '已归档' : selected.published_revision ? `当前发布修订 ${selected.published_revision}` : '尚未发布' }}</p>
      <div v-if="isAdmin" class="version-actions">
        <el-button v-if="selected?.published_revision" :disabled="actionBusy" @click="changeDocument('withdraw')">撤回发布</el-button>
        <el-button v-if="!selected?.archived" type="danger" plain :disabled="actionBusy" @click="changeDocument('archive')">归档文档</el-button>
        <el-button v-else :disabled="actionBusy" @click="changeDocument('restore')">恢复文档</el-button>
      </div>
      <el-table :data="versions.revisions" row-key="id">
        <el-table-column label="修订" width="70"><template #default="{ row }">#{{ row.number }}</template></el-table-column>
        <el-table-column label="状态" min-width="170"><template #default="{ row }">{{ stateLabels[row.state] }}<p v-if="row.job" class="chunk-hint">{{ row.job.state === 'succeeded' ? '入库完成' : row.job.phase }} · {{ row.job.progress }}% · 尝试 {{ row.job.attempts }}/{{ row.job.max_attempts }}</p><el-text v-if="row.job?.error" type="danger">{{ row.job.error }}</el-text></template></el-table-column>
        <el-table-column prop="chunks" label="分块" width="65" />
        <el-table-column label="上传时间" width="170"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" min-width="240"><template #default="{ row }">
          <el-button v-if="['ready', 'published', 'superseded'].includes(row.state)" link @click="viewChunks(selectedId, `${selected?.source} #${row.number}`, row.id)">分块</el-button>
          <a v-if="row.original_available" class="original-link" :href="`/api/documents/${selectedId}/revisions/${row.id}/original`">下载原件</a>
          <el-button v-if="row.job?.state === 'failed'" link type="warning" :disabled="actionBusy" @click="retryRevision(row)">重试</el-button>
          <el-button v-if="isAdmin && !selected?.archived && ['ready', 'superseded'].includes(row.state)" link type="primary" :disabled="actionBusy" @click="changeDocument('publish', row.id)">{{ row.state === 'superseded' ? '回滚至此版本' : '发布' }}</el-button>
        </template></el-table-column>
      </el-table>
      <el-collapse class="audit-log"><el-collapse-item title="操作记录" name="events"><p v-for="(item, index) in versions.events" :key="index">{{ new Date(item.created_at).toLocaleString() }} · {{ eventLabels[item.action] ?? item.action }} · {{ item.actor_id ? '操作人 ' + item.actor_id.slice(0, 8) : '后台处理' }}</p></el-collapse-item></el-collapse>
      <p class="chunk-hint">发布后生效；新修订处理失败不影响原发布版本。下载原件与历史预览仅供客服和管理员，发布与回滚由管理员执行。</p>
    </el-dialog>
  </div>
</template>

<style scoped>
.version-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.original-link { color: var(--brand-600); font-size: 13px; margin: 0 12px; }
.audit-log { margin-top: 20px; }
.document-scope { display: grid; gap: 10px; margin-bottom: 20px; }
.document-scope p { color: var(--text-secondary); font-size: 12px; }
@media (max-width: 600px) {
  .head { flex-direction: column; gap: 12px; }
  .block { padding: 16px; }
  .pending__head { flex-wrap: wrap; gap: 10px; }
}
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
