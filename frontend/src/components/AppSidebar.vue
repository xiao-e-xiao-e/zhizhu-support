<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Files, Tickets, ChatLineSquare, Collection, Clock, Setting, SwitchButton, Fold, Expand } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { useChatStore } from '@/stores/chat'
import { useConversationsStore, conversationTitle } from '@/stores/conversations'
import { useWorkspaceStore } from '@/stores/workspace'
defineProps<{ mobile?: boolean }>()
const emit = defineEmits<{ navigate: [] }>()
const auth = useAuthStore(), chat = useChatStore(), settings = useSettingsStore()
const recent = useConversationsStore(), workspace = useWorkspaceStore()
const route = useRoute(), router = useRouter()
const nav = computed(() => [
  { path: '/assistant', label: '智能助手', icon: ChatLineSquare },
  { path: '/knowledge', label: '产品资料', icon: Files },
  { path: '/tickets', label: auth.isStaff ? '工单工作台' : '我的工单', icon: Tickets },
  { path: '/feedback', label: auth.isStaff ? '回答反馈' : '我的反馈', icon: ChatLineSquare },
])
const management = [
  { path: '/products', label: '产品与版本', icon: Collection },
  { path: '/documents', label: '文档管理', icon: Files },
  { path: '/faqs', label: 'FAQ 知识运营', icon: Collection },
]
async function switchConversation(name = '') {
  if (chat.streaming) {
    try { await ElMessageBox.confirm('当前回复正在进行，停止后切换对话？', '切换对话', { confirmButtonText: '停止并切换', cancelButtonText: '继续当前对话' }) }
    catch { return }
    await chat.stop()
  }
  workspace.close()
  if (!name) chat.clear()
  await router.push({ path: '/assistant', query: name ? { session: name } : {} })
  emit('navigate')
}
async function logout() {
  try { await auth.logout(); settings.config = null; await router.replace('/login') }
  catch (e) { ElMessage.error((e as Error).message) }
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': workspace.collapsed && !mobile }">
    <div class="sidebar__brand">
      <router-link to="/assistant" class="brand-mark" aria-label="智能客服工作台">知</router-link>
      <span class="brand-title sidebar-label">智能客服工作台</span>
      <button v-if="!mobile" class="icon-button collapse-button" :aria-label="workspace.collapsed ? '展开侧栏' : '收起侧栏'" @click="workspace.collapsed = !workspace.collapsed"><el-icon><Expand v-if="workspace.collapsed" /><Fold v-else /></el-icon></button>
    </div>
    <button class="new-chat" title="新对话" @click="switchConversation()"><el-icon><Plus /></el-icon><span class="sidebar-label">新对话</span></button>
    <div class="sidebar__scroll">
      <nav class="sidebar__nav" aria-label="工作台导航">
        <router-link v-for="item in nav" :key="item.path" :to="item.path" :title="item.label" class="nav-item" :class="{ active: route.path.startsWith(item.path) }" @click="emit('navigate')"><el-icon><component :is="item.icon" /></el-icon><span class="sidebar-label">{{ item.label }}</span></router-link>
      </nav>
      <nav v-if="auth.isStaff" class="sidebar__nav management" aria-label="知识运营">
        <p class="section-title sidebar-label">知识运营</p>
        <router-link v-for="item in management" :key="item.path" :to="item.path" :title="item.label" class="nav-item" :class="{ active: route.path.startsWith(item.path) }" @click="emit('navigate')"><el-icon><component :is="item.icon" /></el-icon><span class="sidebar-label">{{ item.label }}</span></router-link>
      </nav>
      <section class="recent sidebar-label" aria-label="最近对话">
        <div class="recent__head"><span class="section-title">最近对话</span><button class="icon-button" aria-label="刷新最近对话" :disabled="recent.loading" @click="recent.refresh()">↻</button></div>
        <p v-if="recent.error" class="recent__empty">加载失败 <button @click="recent.refresh()">重试</button></p>
        <p v-else-if="!recent.items.length" class="recent__empty">{{ recent.loading ? '正在加载…' : '开始对话后，记录会保存在这里' }}</p>
        <button v-for="item in recent.items.slice(0, 8)" :key="item.name" class="recent-item" :class="{ active: route.path === '/assistant' && chat.sessionName === item.name }" :title="conversationTitle(item.name)" @click="switchConversation(item.name)">{{ conversationTitle(item.name) }}</button>
      </section>
      <router-link to="/history" class="nav-item history-link" title="全部对话" @click="emit('navigate')"><el-icon><Clock /></el-icon><span class="sidebar-label">全部对话</span></router-link>
    </div>
    <div class="sidebar__bottom">
      <button class="nav-item" title="助手设置" @click="workspace.openSettings(); emit('navigate')"><el-icon><Setting /></el-icon><span class="sidebar-label">助手设置</span></button>
      <div class="account-row">
        <router-link to="/account" class="account-link" title="账号设置" @click="emit('navigate')"><span class="account-avatar">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span><span class="sidebar-label account-name">{{ auth.user?.username }}<small>{{ auth.isStaff ? '团队工作空间' : '个人工作空间' }}</small></span></router-link>
        <button class="icon-button sidebar-label" aria-label="退出登录" @click="logout"><el-icon><SwitchButton /></el-icon></button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar { display: flex; flex-direction: column; width: 244px; flex-shrink: 0; height: 100%; background: #f7f7fa; border-right: 1px solid #eeedf3; padding: 0 12px; transition: width .18s; }
.sidebar__brand { display: flex; align-items: center; gap: 9px; height: 76px; flex-shrink: 0; padding: 0 6px; }
.brand-mark { display: grid; place-items: center; width: 30px; height: 32px; border-radius: 10px; background: var(--brand-600); color: white; font-size: 17px; font-weight: 600; flex-shrink: 0; text-decoration: none; }
.brand-title { font-size: 14px; font-weight: 600; white-space: nowrap; }.collapse-button { margin-left: auto; }
.icon-button { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 0; border-radius: 6px; background: transparent; color: #888595; cursor: pointer; font-size: 17px; flex-shrink: 0; }.icon-button:hover { background: #ebeaf1; color: var(--text-primary); }
.new-chat { display: flex; align-items: center; gap: 12px; min-height: 42px; padding: 0 14px; border: 1px solid #dcd6f7; border-radius: 11px; background: #efeafa; color: #6250bf; font: 500 14px var(--font-sans); cursor: pointer; margin-bottom: 20px; flex-shrink: 0; }.new-chat:hover { background: #e6dff9; }
.sidebar__scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }.sidebar__nav { display: grid; gap: 3px; }.nav-item { display: flex; width: 100%; align-items: center; gap: 12px; padding: 10px 13px; border: 0; border-radius: 9px; font: 14px var(--font-sans); color: #676473; background: transparent; cursor: pointer; white-space: nowrap; text-decoration: none; text-align: left; }.nav-item .el-icon { font-size: 17px; flex-shrink: 0; }.nav-item:hover,.recent-item:hover { background: #eeedf3; }.nav-item.active { background: #eeebf8; color: #6750c5; font-weight: 600; }
.management { margin-top: 22px; }.section-title { font-size: 11px; font-weight: 500; color: #817a8d; letter-spacing: .06em; }.management .section-title { padding: 0 13px 5px; }.recent { margin-top: 30px; }.recent__head { display: flex; align-items: center; justify-content: space-between; padding: 0 8px 8px 13px; }.recent-item { display: block; width: 100%; background: none; border: 0; padding: 9px 13px; border-radius: 8px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #6f6c7b; font: 13px var(--font-sans); cursor: pointer; }.recent-item.active { background: #eeebf8; color: #6750c5; }.recent__empty { font-size: 12px; color: #817a8d; padding: 8px 13px; }.recent__empty button { border: 0; color: var(--brand-600); background: none; cursor: pointer; }.history-link { margin-top: 10px; font-size: 12px; }.sidebar__bottom { padding: 10px 0 16px; margin-top: 10px; border-top: 1px solid #e9e7ef; }.account-row { display: flex; align-items: center; padding: 10px 7px 0; gap: 5px; }.account-link { display: flex; align-items: center; gap: 9px; min-width: 0; flex: 1; text-decoration: none; }.account-avatar { display: grid; place-items: center; flex-shrink: 0; width: 32px; height: 32px; border-radius: 50%; background: #e9e5f4; color: #70618e; font-weight: 600; }.account-name { font-size: 12px; color: #565160; overflow: hidden; text-overflow: ellipsis; }.account-name small { display: block; font-size: 10px; color: #9c96a6; }
.sidebar--collapsed { width: 72px; padding: 0 10px; }.sidebar--collapsed .sidebar-label { display: none; }.sidebar--collapsed .sidebar__brand { height: 104px; flex-direction: column; padding: 18px 0 10px; gap: 8px; }.sidebar--collapsed .collapse-button { margin: 0; }.sidebar--collapsed .new-chat,.sidebar--collapsed .nav-item { justify-content: center; padding-left: 0; padding-right: 0; }.sidebar--collapsed .account-row { padding: 10px 0 0; justify-content: center; }.sidebar--collapsed .account-link { justify-content: center; }.sidebar--collapsed .management { margin-top: 14px; }
</style>
