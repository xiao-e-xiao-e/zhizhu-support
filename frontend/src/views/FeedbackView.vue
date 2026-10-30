<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { listFeedback } from '@/api/support'
import type { FeedbackRating, FeedbackRecord } from '@/types'
import { formatTime } from '@/utils/support'

const auth = useAuthStore()
const rating = ref<FeedbackRating | ''>('unresolved')
const rows = ref<FeedbackRecord[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const error = ref('')
async function refresh(reset = false) {
  if (reset) page.value = 1
  loading.value = true; error.value = ''
  try { const data = await listFeedback(page.value, rating.value || undefined); rows.value = data.items; total.value = data.total }
  catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
}
onMounted(() => refresh())
</script>

<template>
  <div class="support-page"><header class="support-head"><div><h1 class="page-title">{{ auth.isStaff ? '回答反馈' : '我的反馈' }}</h1><p class="page-desc">查看未解决的问题，发现知识与回答中的改进机会</p></div></header>
    <div class="support-filters"><el-select v-model="rating" clearable placeholder="全部反馈" aria-label="反馈类型"><el-option label="未解决" value="unresolved" /><el-option label="有帮助" value="helpful" /></el-select><el-button :loading="loading" @click="refresh(true)">查询</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-if="!rows.length && !loading" class="card support-section empty-state">暂无符合条件的反馈</div>
    <section v-for="row in rows" :key="row.id" class="card support-section feedback-item"><div class="support-head"><el-tag :type="row.rating === 'helpful' ? 'success' : 'warning'">{{ row.rating === 'helpful' ? '有帮助' : '未解决' }}</el-tag><span class="support-muted">{{ row.user_name }} · {{ formatTime(row.updated_at) }}</span></div><h2>{{ row.question || '未记录问题' }}</h2><p v-if="row.reason" class="feedback-reason">反馈：{{ row.reason }}</p><el-collapse><el-collapse-item title="查看当时的回答" :name="row.id"><p class="feedback-answer">{{ row.answer }}</p><p v-if="row.sources.length">参考资料：{{ row.sources.join('、') }}</p></el-collapse-item></el-collapse><router-link v-if="row.ticket_id" :to="`/tickets/${row.ticket_id}`">查看关联工单 →</router-link></section>
    <el-pagination v-model:current-page="page" layout="prev, pager, next, total" :page-size="20" :total="total" :disabled="loading" @current-change="refresh()" />
  </div>
</template>

<style scoped>
.feedback-item h2 { margin: 16px 0; }
.feedback-answer, .feedback-reason { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; }
.feedback-reason { margin-bottom: 16px; }
</style>
