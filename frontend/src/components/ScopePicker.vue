<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useCatalogStore } from '@/stores/catalog'
import type { KnowledgeScope } from '@/types'

const props = defineProps<{ modelValue: KnowledgeScope; disabled?: boolean; compact?: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: KnowledgeScope): void }>()
const catalog = useCatalogStore()
const activeProducts = computed(() => catalog.products.filter(p => p.is_active))
const versions = computed(() => activeProducts.value.find(p => p.id === props.modelValue.product_id)?.versions.filter(v => v.is_active) ?? [])
onMounted(async () => {
  if (!catalog.initialized) {
    try { await catalog.refresh() } catch (e) { ElMessage.error((e as Error).message) }
  }
})
function productChanged(value: string | undefined) { emit('update:modelValue', { product_id: value || null, version_id: null }) }
function versionChanged(value: string | undefined) { emit('update:modelValue', { ...props.modelValue, version_id: value || null }) }
</script>

<template>
  <div class="scope-picker" :class="{ compact }">
    <el-select :model-value="modelValue.product_id" :disabled="disabled" clearable filterable :placeholder="compact ? '全部产品' : '选择产品（可选）'" aria-label="产品" @update:model-value="productChanged">
      <el-option v-for="product in activeProducts" :key="product.id" :label="product.name" :value="product.id" />
    </el-select>
    <el-select v-if="!compact || modelValue.product_id" :model-value="modelValue.version_id" :disabled="disabled || !modelValue.product_id" clearable :placeholder="compact ? '全部版本' : '选择版本（可选）'" aria-label="产品版本" @update:model-value="versionChanged">
      <el-option v-for="version in versions" :key="version.id" :label="version.name" :value="version.id" />
    </el-select>
  </div>
</template>

<style scoped>
.scope-picker { display: flex; gap: 10px; flex-wrap: wrap; }
.scope-picker .el-select { width: 220px; max-width: 100%; }
.compact { gap: 6px; }.compact .el-select { width: 160px; }.compact :deep(.el-select__wrapper) { min-height: 28px; background: #f7f6fa; box-shadow: none; border-radius: 7px; font-size: 12px; }.compact :deep(.el-select__wrapper.is-disabled) { background: #f7f6fa; }.compact :deep(.el-select__wrapper.is-disabled .el-select__selected-item) { color: #777180; }
@media(max-width: 480px) { .compact .el-select { width: 132px; } }
</style>
