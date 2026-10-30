<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useCatalogStore } from '@/stores/catalog'
import { listTickets } from '@/api/support'
import TicketCreateDialog from '@/components/TicketCreateDialog.vue'
import type { TicketStatus, TicketSummary } from '@/types'
import { statusLabels, priorityLabels, formatTime } from '@/utils/support'

const auth = useAuthStore()
const catalog = useCatalogStore()
const router = useRouter()
const tickets = ref<TicketSummary[]>([])
const page = ref(1)
const total = ref(0)
const status = ref<TicketStatus | ''>('')
const product = ref('')
const mine = ref(false)
const creating = ref(false)
const loading = ref(false)
const error = ref('')
async function refresh(reset = false) {
  if (reset) page.value = 1
  loading.value = true; error.value = ''
  try {
    const data = await listTickets({ page: page.value, status: status.value || undefined, product_id: product.value || undefined, mine: mine.value })
    tickets.value = data.items; total.value = data.total
  } catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
}
onMounted(async () => {
  try { await catalog.refresh() } catch (e) { error.value = (e as Error).message }
  await refresh()
})
function openTicket(id: string) { void router.push(`/tickets/${id}`) }
</script>

<template>
  <div class="support-page">
    <header class="support-head"><div><h1 class="page-title">{{ auth.isStaff ? '工单工作台' : '我的工单' }}</h1><p class="page-desc">提交问题、查看处理进度，与客服协作解决问题</p></div><el-button type="primary" @click="creating = true">新建工单</el-button></header>
    <section class="card support-section">
      <div class="support-filters">
        <el-select v-model="status" clearable placeholder="全部状态" aria-label="工单状态"><el-option v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" /></el-select>
        <el-select v-model="product" clearable placeholder="全部产品" aria-label="筛选产品"><el-option v-for="item in catalog.products" :key="item.id" :label="item.name" :value="item.id" /></el-select>
        <el-checkbox v-if="auth.isStaff" v-model="mine">仅我提交</el-checkbox><el-button :loading="loading" @click="refresh(true)">查询</el-button>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-table v-loading="loading" :data="tickets" empty-text="暂无工单，遇到问题时可以提交支持工单" class="ticket-table" @row-click="(row: TicketSummary) => openTicket(row.id)">
        <el-table-column label="问题" min-width="240"><template #default="{ row }"><el-button link type="primary" @click.stop="openTicket(row.id)">{{ row.title }}</el-button><div class="support-muted">{{ row.product_name || '未指定产品' }} {{ row.version_name || '' }}</div></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'resolved' ? 'success' : row.status === 'closed' ? 'info' : 'primary'">{{ statusLabels[row.status as TicketStatus] }}</el-tag></template></el-table-column>
        <el-table-column label="优先级" width="90"><template #default="{ row }">{{ priorityLabels[row.priority as keyof typeof priorityLabels] }}</template></el-table-column>
        <el-table-column v-if="auth.isStaff" prop="creator_name" label="提交者" width="120" />
        <el-table-column label="处理人" width="120"><template #default="{ row }">{{ row.assignee_name || '待分配' }}</template></el-table-column>
        <el-table-column label="更新时间" width="180"><template #default="{ row }">{{ formatTime(row.updated_at) }}</template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" layout="prev, pager, next, total" :total="total" :page-size="20" :disabled="loading" @current-change="refresh()" />
    </section>
    <TicketCreateDialog v-model="creating" @created="openTicket" />
  </div>
</template>
