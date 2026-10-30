<script setup lang="ts">
import type { ToolStep } from '@/types/workflows'
defineProps<{ steps: ToolStep[] }>()
const labels: Record<string, string> = { general_chat: '普通交流', get_assistant_info: '读取助手公开信息', ask_clarification: '补充问题信息', model: '模型调用', search_knowledge: '检索已发布知识', search_resolved_tickets: '检索相似已解决工单', get_ticket_status: '查询工单状态', create_ticket: '准备工单草稿', generate_faq: '生成 FAQ 草稿', unregistered_tool: '拒绝未注册工具' }
const states: Record<string, string> = { running: '执行中', succeeded: '完成', failed: '未完成', awaiting_confirmation: '等待确认' }
</script>
<template>
  <section class="run-trace"><h2>执行步骤</h2><p v-if="!steps.length" class="support-muted">尚未开始执行。</p>
    <article v-for="step in steps" :key="step.id" class="trace-step">
      <div class="trace-head"><b>{{ step.number }}. {{ labels[step.name] ?? step.name }}</b><span>{{ states[step.status] }} · {{ (step.elapsed_ms / 1000).toFixed(2) }} 秒</span></div>
      <p v-if="step.error" class="trace-error">{{ step.error }}</p>
      <p v-if="step.input.query" class="support-muted">检索问题：{{ step.input.query }}</p>
      <p v-if="step.input.ticket_id" class="support-muted">工单：{{ step.input.ticket_id }}</p>
      <details v-if="step.status !== 'running'"><summary>查看输入与结果</summary><pre>{{ JSON.stringify({ input: step.input, output: step.output }, null, 2) }}</pre></details>
    </article>
  </section>
</template>
<style scoped>
h2 { font-size: 15px; margin-bottom: 14px; }
.trace-step { border-top: 1px solid var(--border-default); padding: 14px 0; }
.trace-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 13px; }
.trace-head span, summary { color: var(--text-secondary); font-size: 12px; }
summary { cursor: pointer; margin-top: 10px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 260px; overflow: auto; padding: 12px; background: var(--bg-subtle); font-size: 12px; }
.trace-error { color: var(--el-color-danger); margin: 10px 0; }
</style>
