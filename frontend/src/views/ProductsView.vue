<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCatalogStore } from '@/stores/catalog'
import * as api from '@/api/support'

const catalog = useCatalogStore()
const draft = reactive({ name: '', description: '' })
const versionNames = reactive<Record<string, string>>({})
const busy = ref(false)
const error = ref('')
async function action(fn: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await fn(); await catalog.refresh() }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
onMounted(() => action(() => catalog.refresh()))
async function addProduct() {
  await action(async () => { await api.createProduct(draft.name, draft.description); draft.name = ''; draft.description = ''; ElMessage.success('产品已创建') })
}
async function addVersion(id: string) {
  await action(async () => { await api.createVersion(id, versionNames[id] ?? ''); versionNames[id] = ''; ElMessage.success('版本已添加') })
}
async function toggleProduct(id: string, active: boolean) {
  try { await ElMessageBox.confirm(active ? '停用后将无法再选择该产品，已有会话与工单会保留。' : '确定重新启用该产品？', '产品状态') }
  catch { return }
  await action(() => api.setProductActive(id, !active))
}
</script>

<template>
  <div class="support-page">
    <header class="support-head"><div><h1 class="page-title">产品与版本</h1><p class="page-desc">组织产品资料，让问答与工单关联到明确的产品版本</p></div><el-button :loading="busy" @click="action(() => catalog.refresh())">刷新</el-button></header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <section class="card support-section">
      <h2>添加产品</h2>
      <form class="product-form" @submit.prevent="addProduct"><el-input v-model="draft.name" maxlength="100" placeholder="产品名称" /><el-input v-model="draft.description" maxlength="2000" placeholder="产品简介（可选）" /><el-button native-type="submit" type="primary" :loading="busy" :disabled="!draft.name.trim()">添加产品</el-button></form>
    </section>
    <div v-if="!catalog.products.length && !catalog.loading" class="card support-section empty-state">暂无产品，先添加一个产品及其版本。</div>
    <section v-for="product in catalog.products" :key="product.id" class="card support-section">
      <div class="support-head"><div><h2>{{ product.name }} <el-tag v-if="!product.is_active" type="info">已停用</el-tag></h2><p>{{ product.description || '暂无简介' }}</p></div><el-button :disabled="busy" @click="toggleProduct(product.id, product.is_active)">{{ product.is_active ? '停用产品' : '启用产品' }}</el-button></div>
      <div class="version-list"><div v-for="version in product.versions" :key="version.id" class="version-item"><span>{{ version.name }}</span><el-tag v-if="!version.is_active" type="info" size="small">已停用</el-tag><el-button link size="small" :disabled="busy" @click="action(() => api.setVersionActive(product.id, version.id, !version.is_active))">{{ version.is_active ? '停用' : '启用' }}</el-button></div></div>
      <form v-if="product.is_active" class="version-form" @submit.prevent="addVersion(product.id)"><el-input v-model="versionNames[product.id]" maxlength="80" placeholder="版本名称，例如 2.0" /><el-button native-type="submit" :disabled="busy || !versionNames[product.id]?.trim()">添加版本</el-button></form>
    </section>
  </div>
</template>

<style scoped>
.product-form { display: grid; grid-template-columns: 1fr 2fr auto; gap: 12px; margin-top: 16px; }
.version-list { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.version-item { display: flex; align-items: center; gap: 8px; padding: 6px 12px; background: var(--bg-page); border-radius: 8px; }
.version-form { display: flex; gap: 10px; max-width: 400px; }
@media(max-width: 900px) { .product-form { grid-template-columns: 1fr; } }
</style>
