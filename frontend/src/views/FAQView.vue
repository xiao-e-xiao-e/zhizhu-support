<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/workflows'
import { http } from '@/api/client'
import RunTrace from '@/components/RunTrace.vue'
import { useAuthStore } from '@/stores/auth'
import { useCatalogStore } from '@/stores/catalog'
import { useLibraryStore } from '@/stores/library'
import type { AssistantRun, FAQDraft, FAQState } from '@/types/workflows'
import { formatTime } from '@/utils/support'

const route = useRoute(), router = useRouter(), auth = useAuthStore(), catalog = useCatalogStore(), library = useLibraryStore()
const items = ref<FAQDraft[]>([]), total = ref(0), page = ref(1), filter = ref<FAQState | undefined>()
const selected = ref<FAQDraft | null>(null), dialog = ref(false), busy = ref(false), error = ref('')
const question = ref(''), answer = ref(''), note = ref(''), reviewed = ref(false), trace = ref<AssistantRun | null>(null)
const gaps = ref<Awaited<ReturnType<typeof api.getGaps>>>([])
const labels: Record<FAQState, string> = { generating: '生成中', failed: '生成未完成', draft: '编辑中', review: '待审核', rejected: '已退回', indexing: '审核通过，入库中', published: '已发布' }
const eventLabels: Record<string, string> = { created: '创建草稿', generated: '模型生成完成', edited: '编辑', regenerate: '重新生成', submit: '提交审核', approve: '批准并排队入库', reject: '退回', publish: '发布知识', revise: '退回编辑' }
const editable = computed(() => !!selected.value && ['draft', 'rejected', 'failed'].includes(selected.value.state))
const isAdmin = computed(() => auth.user?.role === 'admin')
let timer: ReturnType<typeof setInterval> | undefined, polling = false, disposed = false
function accept(faq: FAQDraft) { selected.value = faq; question.value = faq.question; answer.value = faq.answer }
function scopeLabel(faq: FAQDraft) { const p = catalog.products.find(v => v.id === faq.product_id); return p ? `${p.name} ${p.versions.find(v => v.id === faq.version_id)?.name ?? '全部版本'}` : '未分类' }
async function load() { const result = await api.listFAQs(filter.value, page.value); items.value = result.items; total.value = result.total }
async function refreshSelected() { if (selected.value) { accept(await api.getFAQ(selected.value.id)); if (selected.value.run_id) trace.value = await api.getRun(selected.value.run_id) } }
async function open(id: string, generate = false) {
  error.value = ''; trace.value = null; reviewed.value = false; note.value = ''
  try { accept(await api.getFAQ(id)); dialog.value = true; if (selected.value?.run_id) trace.value = await api.getRun(selected.value.run_id); if (generate && selected.value?.state === 'generating') await runGeneration() }
  catch (e) { error.value = (e as Error).message }
}
watch(() => route.query.id, value => { if (typeof value === 'string') void open(value, route.query.generate === '1') }, { immediate: true })
onMounted(async () => {
  try { await Promise.all([load(), catalog.refresh(), api.getGaps().then(v => { gaps.value = v })]) } catch (e) { error.value = (e as Error).message }
  timer = setInterval(async () => {
    if (disposed || polling || busy.value || !dialog.value || !selected.value || !['generating', 'indexing'].includes(selected.value.state)) return
    polling = true
    try { await refreshSelected(); await load() } catch { /* 手动刷新会显示错误 */ } finally { polling = false }
  }, 4000)
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
async function mutate(operation: () => Promise<FAQDraft>) {
  if (busy.value) return false
  busy.value = true; error.value = ''
  try { const faq = await operation(); if (!disposed) { accept(faq); await load(); if (faq.run_id) trace.value = await api.getRun(faq.run_id) } return true }
  catch (e) { error.value = (e as Error).message; return false }
  finally { busy.value = false }
}
async function save() { return !!selected.value && await mutate(() => api.saveFAQ(selected.value!, question.value, answer.value)) }
async function act(action: 'submit' | 'revise' | 'publish') {
  if (!selected.value) return
  if (action === 'submit' && (question.value !== selected.value.question || answer.value !== selected.value.answer)) { if (!await save()) return }
  if (action === 'publish') { try { await ElMessageBox.confirm('发布后所有有权访问该范围的用户都能检索此 FAQ，请确认内容适合共享。', '发布 FAQ', { confirmButtonText: '确认发布', cancelButtonText: '取消' }) } catch { return } }
  if (await mutate(() => api.faqAction(selected.value!, action))) { ElMessage.success('FAQ 状态已更新'); if (action === 'publish') await library.refresh() }
}
async function review(decision: 'approve' | 'reject') {
  if (!selected.value) return
  if (await mutate(() => api.reviewFAQ(selected.value!, decision, note.value, reviewed.value))) ElMessage.success(decision === 'approve' ? '审核通过，已提交后台入库' : '已退回修改')
}
async function runGeneration() { if (selected.value) await mutate(() => api.generateFAQ(selected.value!.id)) }
async function regenerate() {
  if (!selected.value) return
  try { await ElMessageBox.confirm('重新生成会根据最新解决说明覆盖当前草稿，请先保留需要的修改。', '重新生成 FAQ', { confirmButtonText: '重新生成', cancelButtonText: '取消' }) } catch { return }
  if (await mutate(() => api.regenerateFAQ(selected.value!, crypto.randomUUID()))) await runGeneration()
}
async function retryIndex() { if (!selected.value?.job) return; busy.value = true; try { await http.post(`/documents/jobs/${selected.value.job.id}/retry`); await refreshSelected(); ElMessage.success('入库任务已重新排队') } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
</script>

<template>
  <div class="support-page">
    <header class="support-head"><div><h1 class="page-title">FAQ 知识运营</h1><p class="page-desc">把已解决工单整理为知识：编辑、审核、后台入库，再发布共享。</p></div><el-button @click="router.push('/tickets')">从已解决工单创建</el-button></header>
    <el-alert v-if="error && !dialog" :title="error" type="error" :closable="false" show-icon />
    <section class="card support-section"><div class="faq-toolbar"><el-select v-model="filter" clearable placeholder="全部状态" aria-label="FAQ 状态" style="width: 210px" @change="page = 1; load()"><el-option v-for="(label, value) in labels" :key="value" :label="label" :value="value" /></el-select><el-button @click="load">刷新列表</el-button></div>
      <el-table :data="items"><el-table-column label="问题" min-width="260"><template #default="{ row }"><el-button link type="primary" @click="router.push({ path: '/faqs', query: { id: row.id } })">{{ row.question || '待生成 FAQ' }}</el-button></template></el-table-column><el-table-column label="范围" min-width="150"><template #default="{ row }">{{ scopeLabel(row) }}</template></el-table-column><el-table-column label="状态" min-width="160"><template #default="{ row }">{{ labels[row.state as FAQState] }}</template></el-table-column><el-table-column label="更新时间" width="175"><template #default="{ row }">{{ formatTime(row.updated_at) }}</template></el-table-column></el-table>
      <p v-if="!items.length" class="support-muted empty-faq">尚无 FAQ，请在已解决或已关闭的工单详情中创建。</p><el-pagination v-if="total > 20" v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load" />
    </section>
    <section class="card support-section"><h2>未解决问题线索</h2><p class="support-muted">按“未解决”反馈中的相同问题聚合，显示频次最高的 20 项，供客服判断知识缺口；不代表已经核实的产品缺陷。</p><el-table :data="gaps"><el-table-column prop="question" label="问题" min-width="260" /><el-table-column prop="count" label="未解决反馈" width="120" /><el-table-column prop="linked_tickets" label="已关联工单" width="120" /></el-table><p v-if="!gaps.length" class="support-muted empty-faq">暂无未解决反馈。</p></section>
    <el-dialog v-model="dialog" title="FAQ 草稿与审核" width="min(1000px, 95vw)" :close-on-click-modal="!busy" :show-close="!busy">
      <template v-if="selected"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon /><div class="faq-toolbar"><el-tag>{{ labels[selected.state] }}</el-tag><span>{{ scopeLabel(selected) }}</span><router-link v-if="selected.ticket_id" :to="`/tickets/${selected.ticket_id}`">查看原工单</router-link><el-button link :disabled="busy" @click="refreshSelected">刷新草稿</el-button></div>
        <el-alert title="模型草稿可能有遗漏。审核时请核对解决依据、适用版本，并移除客户身份、联系方式、凭据及专属地址。原工单和解决快照仅客服可见，发布只包含下方问答内容。" type="info" :closable="false" />
        <el-collapse class="faq-evidence"><el-collapse-item title="查看生成依据与操作记录" name="source"><h3>问题</h3><p class="preserve-lines">{{ selected.source_snapshot?.problem }}</p><h3>解决说明</h3><p class="preserve-lines">{{ selected.source_snapshot?.solution }}</p><p v-for="(event, i) in selected.events ?? []" :key="i">{{ formatTime(event.created_at) }} · {{ eventLabels[event.action] ?? event.action }} {{ event.note }}</p></el-collapse-item><el-collapse-item v-if="trace" title="查看模型执行记录" name="trace"><RunTrace :steps="trace.steps ?? []" /></el-collapse-item></el-collapse>
        <el-form label-position="top"><el-form-item label="FAQ 问题"><el-input v-model="question" maxlength="240" show-word-limit :disabled="!editable || busy" /></el-form-item><el-form-item label="FAQ 答案（Markdown）"><el-input v-model="answer" type="textarea" :rows="9" maxlength="8000" show-word-limit :disabled="!editable || busy" /></el-form-item></el-form>
        <div v-if="selected.state === 'generating'" class="faq-buttons"><el-button type="primary" :loading="busy" @click="runGeneration">继续生成</el-button><p class="support-muted">生成任务只由发起人执行，失败时可重试或人工整理；不会自动发布。</p></div>
        <div v-if="editable" class="faq-buttons"><el-button :loading="busy" :disabled="!question.trim() || !answer.trim()" @click="save">保存草稿</el-button><el-button :disabled="busy" @click="regenerate">模型重新生成</el-button><el-button v-if="selected.state !== 'failed'" type="primary" :disabled="busy || !question.trim() || !answer.trim()" @click="act('submit')">提交审核</el-button></div>
        <p v-if="selected.review_note" class="review-note">审核意见：{{ selected.review_note }}</p>
        <section v-if="selected.state === 'review' && isAdmin" class="review-panel"><h3>管理员审核</h3><el-input v-model="note" type="textarea" :rows="3" maxlength="1000" placeholder="审核意见；退回时必须填写原因" /><el-checkbox v-model="reviewed">已核对事实、适用范围和敏感信息，适合发布为共享知识</el-checkbox><div class="faq-buttons"><el-button type="primary" :disabled="busy || !reviewed" @click="review('approve')">批准并入库</el-button><el-button type="warning" :disabled="busy || !note.trim()" @click="review('reject')">退回修改</el-button></div></section>
        <section v-if="selected.state === 'indexing'" class="index-panel"><p>后台处理：{{ selected.job?.phase }} · {{ selected.job?.progress ?? 0 }}%</p><el-text v-if="selected.job?.error" type="danger">{{ selected.job.error }}</el-text><el-button v-if="selected.job?.state === 'failed'" :disabled="busy" @click="retryIndex">重试入库</el-button><el-button v-if="isAdmin" type="primary" :disabled="busy || !['ready', 'superseded', 'published'].includes(selected.knowledge_state ?? '')" @click="act('publish')">发布 FAQ</el-button></section>
        <p v-if="selected.state === 'published'" class="support-muted">知识修订当前状态：{{ selected.knowledge_state === 'published' ? '已发布，可用于问答' : '已撤回或归档，请在文档管理中核对' }}。后续修改仍需重新审核。</p>
        <div class="faq-buttons"><el-button v-if="['review', 'indexing', 'published'].includes(selected.state)" :disabled="busy" @click="act('revise')">{{ selected.state === 'published' ? '修改为新草稿' : '退回编辑' }}</el-button><el-button v-if="selected.document_id" :disabled="busy" @click="router.push('/documents')">查看知识修订</el-button></div>
      </template>
    </el-dialog>
  </div>
</template>
<style scoped>
.faq-toolbar, .faq-buttons { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 14px 0; }
.faq-buttons .el-button { margin-left: 0; }
.empty-faq { padding: 20px 0; }
.faq-evidence { margin: 18px 0; }
.preserve-lines { white-space: pre-wrap; overflow-wrap: anywhere; margin: 12px 0; line-height: 1.7; }
.review-panel, .index-panel { padding: 18px; border: 1px solid var(--border-default); border-radius: 8px; margin: 18px 0; }
.review-panel .el-checkbox { white-space: normal; height: auto; margin-top: 14px; }
.review-note { margin: 16px 0; color: var(--text-secondary); }
</style>
