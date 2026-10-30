<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ScopePicker from './ScopePicker.vue'
import { createTicket } from '@/api/support'
import type { KnowledgeScope, TicketPriority } from '@/types'

const props = defineProps<{ modelValue: boolean; conversationName?: string; messageId?: number; question?: string; scope?: KnowledgeScope }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void; (e: 'created', id: string): void }>()
const open = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const form = reactive({ title: '', description: '', priority: 'normal' as TicketPriority })
const scope = ref<KnowledgeScope>({ product_id: null, version_id: null })
const attach = ref(true)
const busy = ref(false)
const error = ref('')
let key = ''
watch(() => props.modelValue, value => {
  if (!value) return
  form.title = (props.question ?? '').slice(0, 160)
  form.description = props.question ? `${props.question}\n\n已尝试的步骤：\n实际现象：` : ''
  form.priority = 'normal'
  scope.value = { product_id: props.scope?.product_id ?? null, version_id: props.scope?.version_id ?? null }
  attach.value = true; error.value = ''; key = crypto.randomUUID()
})
async function submit() {
  if (busy.value || !form.title.trim() || !form.description.trim()) return
  busy.value = true; error.value = ''
  try {
    const ticket = await createTicket({ ...form, ...scope.value, idempotency_key: key,
      conversation_name: attach.value ? props.conversationName || null : null,
      message_id: attach.value && props.conversationName ? props.messageId || null : null })
    ElMessage.success('工单已提交')
    open.value = false
    emit('created', ticket.id)
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>

<template>
  <el-drawer v-model="open" title="提交支持工单" size="min(480px, 100vw)" :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="问题标题" required><el-input v-model="form.title" maxlength="160" show-word-limit placeholder="简要描述遇到的问题" /></el-form-item>
      <el-form-item label="产品与版本"><ScopePicker v-model="scope" /></el-form-item>
      <el-form-item label="问题描述" required><el-input v-model="form.description" type="textarea" :rows="6" maxlength="8000" show-word-limit placeholder="请描述操作步骤、报错信息和已尝试的解决方法" /></el-form-item>
      <el-form-item label="优先级"><el-select v-model="form.priority"><el-option label="一般" value="normal" /><el-option label="较低" value="low" /><el-option label="紧急" value="high" /></el-select></el-form-item>
      <el-checkbox v-if="conversationName" v-model="attach">附上相关对话（客服可见，最多 12 条）</el-checkbox>
    </el-form>
    <template #footer><el-button :disabled="busy" @click="open = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!form.title.trim() || !form.description.trim()" @click="submit">确认提交</el-button></template>
  </el-drawer>
</template>
