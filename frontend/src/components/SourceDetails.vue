<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { renderMarkdown } from '@/utils/markdown'
const panel = useWorkspaceStore(), auth = useAuthStore()
const hit = computed(() => panel.contexts[panel.selectedSource])
</script>
<template>
  <div class="source-details">
    <div v-if="panel.contexts.length" class="source-tabs" aria-label="切换引用片段"><button v-for="(_, index) in panel.contexts" :key="index" :class="{ selected: panel.selectedSource === index }" :aria-pressed="panel.selectedSource === index" @click="panel.selectedSource = index">{{ index + 1 }}</button></div>
    <template v-if="hit">
      <div class="source-document"><el-icon><Document /></el-icon><div><h3>{{ hit.source }}</h3><p>{{ hit.revision_number ? `文档修订 ${hit.revision_number}` : '本次回答使用的资料' }}</p></div></div>
      <div class="excerpt-label">引用片段 · 资料 {{ panel.selectedSource + 1 }}</div>
      <article class="source-excerpt md-body" v-html="renderMarkdown(hit.content)" />
      <p class="source-note">此处展示本次回答检索时的片段。资料更新后，可在产品资料中查看当前版本。</p>
      <details v-if="auth.isStaff" class="source-meta"><summary>检索详情</summary><p>片段序号：{{ hit.chunk_index }}</p><p>相似度：{{ (hit.similarity * 100).toFixed(1) }}%</p><p v-if="hit.revision_id">修订编号：{{ hit.revision_id }}</p></details>
    </template>
    <template v-else><p class="source-note">该历史回答仅保存了来源文件名，暂时没有可展示的引用片段。</p><p v-for="name in panel.sources" :key="name" class="source-filename">{{ name }}</p></template>
    <router-link to="/knowledge" class="source-library" @click="panel.close()">前往产品资料 →</router-link>
  </div>
</template>
<style scoped>
.source-details { padding: 0 24px 28px; }.source-tabs { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 24px; }.source-tabs button { width: 32px; height: 32px; border: 1px solid #e6e1ee; background: white; border-radius: 9px; color: #82768f; cursor: pointer; }.source-tabs button.selected { background: var(--brand-600); color: white; border-color: var(--brand-600); }.source-document { display: flex; gap: 12px; align-items: flex-start; }.source-document .el-icon { font-size: 22px; color: var(--brand-500); margin-top: 3px; }h3 { font-size: 13px; overflow-wrap: anywhere; }.source-document p { font-size: 11px; color: #99909e; margin-top: 4px; }.excerpt-label { font-size: 11px; color: #948a9f; margin: 26px 0 10px; }.source-excerpt { background: white; padding: 18px; border: 1px solid #ece7f2; border-radius: 12px; overflow-wrap: anywhere; font-size: 13px; }.source-note { font-size: 11px; color: #99909e; line-height: 1.8; margin: 14px 0; }.source-meta { margin: 20px 0; font-size: 11px; color: #8a7f96; overflow-wrap: anywhere; }.source-meta summary { cursor: pointer; margin-bottom: 8px; }.source-library { display: inline-block; font-size: 12px; margin-top: 18px; }.source-filename { font-size: 13px; margin: 10px 0; overflow-wrap: anywhere; }
</style>
