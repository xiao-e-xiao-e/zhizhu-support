<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import SourceDetails from './SourceDetails.vue'
import TicketDraftEditor from './TicketDraftEditor.vue'
import AssistantPreferences from './AssistantPreferences.vue'
const panel = useWorkspaceStore()
</script>
<template>
  <div class="panel-content">
    <header><div><small>{{ panel.kind === 'sources' ? '回答依据' : panel.kind === 'ticket' ? '人工支持' : '工作空间' }}</small><h2>{{ panel.kind === 'sources' ? '资料来源' : panel.kind === 'ticket' ? '工单草稿' : '助手设置' }}</h2></div><el-button text circle aria-label="关闭详情面板" @click="panel.close()"><el-icon><Close /></el-icon></el-button></header>
    <div class="panel-scroll"><SourceDetails v-if="panel.kind === 'sources'" /><TicketDraftEditor v-else-if="panel.kind === 'ticket'" :key="panel.runId" /><AssistantPreferences v-else-if="panel.kind === 'settings'" /></div>
  </div>
</template>
<style scoped>
.panel-content { height: 100%; display: flex; flex-direction: column; background: #fcfbfe; }header { display: flex; justify-content: space-between; align-items: center; padding: 22px 24px; flex-shrink: 0; }small { color: #9b93ab; font-size: 10px; letter-spacing: .08em; }h2 { font-size: 17px; margin-top: 3px; }.panel-scroll { flex: 1; min-height: 0; overflow-y: auto; }
</style>
