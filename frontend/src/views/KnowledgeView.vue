<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { DocumentItem } from '@/types'
import { http } from '@/api/client'
import { useLibraryStore } from '@/stores/library'
import { useCatalogStore } from '@/stores/catalog'
const library = useLibraryStore()
const catalog = useCatalogStore()
const router = useRouter()
const query = ref('')
const product = ref('')
const selected = ref('')
const content = ref<{chunk_index: number; content: string}[]>([])
const loading = ref(false)
const error = ref('')
const rows = computed(() => library.documents.filter(d => (!product.value || d.product_id === product.value) && d.source.toLowerCase().includes(query.value.toLowerCase())))
const productName = (id?: string | null) => catalog.products.find(p => p.id === id)?.name || '工作台'
const versionName = (id?: string | null) => catalog.products.flatMap(p => p.versions).find(v => v.id === id)?.name || '通用'
onMounted(async () => { await Promise.all([library.refresh(), catalog.refresh()]) })
function openRow(row: DocumentItem) { void read(row.id, row.source) }
async function read(id: string, source: string) {
  selected.value = source; loading.value = true; content.value = []; error.value = ''
  try { content.value = (await http.get(`/documents/${id}/chunks`)).data }
  catch (e) { error.value = (e as Error).message }
  finally { loading.value = false }
}
</script>
<template>
  <div class="knowledge-page">
    <header><div><h1 class="page-title">产品资料</h1><p class="page-desc">查阅使用指南、操作规范与常见问题解决方案。</p></div><el-button type="primary" @click="router.push('/assistant')">咨询产品问题</el-button></header>
    <div class="filters"><el-input v-model="query" clearable placeholder="搜索资料名称" /><el-select v-model="product" clearable placeholder="全部产品"><el-option v-for="p in catalog.products" :key="p.id" :value="p.id" :label="p.name" /></el-select></div>
    <el-alert v-if="library.error" :title="library.error" type="error" :closable="false" />
    <el-table v-loading="library.loading" :data="rows" empty-text="暂无可访问的已发布资料" @row-click="openRow">
      <el-table-column prop="source" label="资料名称" min-width="260" /><el-table-column label="产品" min-width="180"><template #default="{row}">{{ productName(row.product_id) }}</template></el-table-column><el-table-column label="版本" width="100"><template #default="{row}">{{ versionName(row.version_id) }}</template></el-table-column><el-table-column label="操作" width="100"><template #default="{row}"><el-button link type="primary" @click.stop="read(row.id, row.source)">阅读</el-button></template></el-table-column>
    </el-table>
    <el-drawer :model-value="!!selected" :title="selected" size="min(720px, 100%)" @close="selected = ''"><div v-loading="loading" class="reading"><el-alert v-if="error" :title="error" type="error" /><pre v-for="chunk in content" :key="chunk.chunk_index">{{ chunk.content }}</pre></div></el-drawer>
  </div>
</template>
<style scoped>
.knowledge-page { padding: 30px; height: 100%; overflow: auto; } header { display: flex; justify-content: space-between; align-items: center; gap: 18px; } .filters { display: flex; gap: 14px; margin: 24px 0; max-width: 650px; } .filters .el-select { width: 260px; flex-shrink: 0; } .reading { min-height: 120px; } pre { white-space: pre-wrap; font: inherit; line-height: 1.9; margin-bottom: 24px; } :deep(.el-table__row) { cursor: pointer; } @media(max-width: 760px) { .knowledge-page { padding: 20px; } header, .filters { flex-wrap: wrap; } }
</style>
