<script setup lang="ts">
import { Document } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import type { ChunkHit } from '@/types'
defineProps<{ sources?: string[]; contexts?: ChunkHit[] }>()
const panel = useWorkspaceStore()
</script>
<template>
  <div v-if="contexts?.length || sources?.length" class="source-strip">
    <span class="source-strip__label">参考来源</span>
    <template v-if="contexts?.length"><button v-for="(hit, index) in contexts.slice(0, 3)" :key="hit.id" class="source-chip" :title="hit.source" @click="panel.openSources(contexts, sources, index)"><span>{{ index + 1 }}</span>{{ hit.source }}</button><button v-if="contexts.length > 3" class="source-more" @click="panel.openSources(contexts, sources)">全部 {{ contexts.length }} 条 →</button></template>
    <template v-else><button v-for="name in sources" :key="name" class="source-chip" @click="panel.openSources([], sources)"><el-icon><Document /></el-icon>{{ name }}</button></template>
  </div>
</template>
<style scoped>
.source-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin: 12px 0; }.source-strip__label { color: #9b90a6; font-size: 10px; margin-right: 2px; }.source-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 210px; padding: 5px 9px; border: 1px solid #ebe6f2; background: #fbfafd; color: #897b99; border-radius: 7px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font: 11px var(--font-sans); cursor: pointer; }.source-chip span { color: #7d66b6; font-size: 10px; }.source-chip:hover { border-color: #ccbfeb; color: var(--brand-600); }.source-more { background: none; border: 0; font: 11px var(--font-sans); color: #8d7da3; cursor: pointer; }
</style>
