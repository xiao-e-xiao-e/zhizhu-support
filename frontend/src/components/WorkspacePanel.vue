<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
const WorkspacePanelContent = defineAsyncComponent(() => import('./WorkspacePanelContent.vue'))
const panel = useWorkspaceStore()
const wide = ref(false)
const media = window.matchMedia('(min-width: 1280px)')
function update() { wide.value = media.matches }
onMounted(() => { update(); media.addEventListener('change', update) })
onUnmounted(() => media.removeEventListener('change', update))
const open = computed({ get: () => !!panel.kind && !wide.value, set: value => { if (!value) panel.close() } })
</script>
<template>
  <aside v-if="wide && panel.kind" class="workspace-panel" aria-label="详情面板"><WorkspacePanelContent /></aside>
  <el-drawer v-if="!wide" v-model="open" :with-header="false" size="min(440px, 100vw)" class="workspace-drawer" destroy-on-close><WorkspacePanelContent /></el-drawer>
</template>
<style scoped>
.workspace-panel { width: 400px; flex-shrink: 0; height: 100%; background: #fcfbfe; border-left: 1px solid var(--border-default); overflow: hidden; }
</style>
<style>.workspace-drawer .el-drawer__body { padding: 0; overflow: hidden; }.mobile-menu-drawer .el-drawer__body { padding: 0; }</style>
