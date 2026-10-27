<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppSidebar from '@/components/AppSidebar.vue'
import WorkspacePanel from '@/components/WorkspacePanel.vue'
import { useConversationsStore } from '@/stores/conversations'
import { useWorkspaceStore } from '@/stores/workspace'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'

const settings = useSettingsStore()
const library = useLibraryStore()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const mobileMenu = ref(false)
const recent = useConversationsStore()
watch(() => route.path, () => { mobileMenu.value = false; useWorkspaceStore().close(); void recent.refresh() })

watch(() => auth.user?.id, async (id) => {
  if (id) {
    void recent.refresh()
    await settings.loadConfig()
    if (auth.user?.id === id) await library.refresh()
  }
}, { immediate: true })

function expired() { auth.clear(); settings.config = null; void router.replace('/login') }
onMounted(() => window.addEventListener('auth-expired', expired))
onUnmounted(() => window.removeEventListener('auth-expired', expired))
</script>

<template>
  <router-view v-if="!auth.user && route.meta.public" />
  <div v-else-if="auth.user" class="app-shell">
    <AppSidebar class="desktop-sidebar" />
    <header class="mobile-topbar"><b>智能客服工作台</b><el-button aria-label="打开导航菜单" @click="mobileMenu = true">菜单</el-button></header>
    <el-drawer v-model="mobileMenu" title="导航菜单" direction="ltr" size="280px" :with-header="false" class="mobile-menu-drawer"><AppSidebar mobile style="width: 100%; height: 100%" @navigate="mobileMenu = false" /></el-drawer>
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <WorkspacePanel />
  </div>
  <div v-else class="app-loading">正在加载工作台…</div>
</template>

<style scoped>
.mobile-topbar { display: none; }
.mobile-menu-drawer :deep(.el-drawer__body) { padding: 0; }
.app-loading { min-height: 100vh; display: grid; place-items: center; color: var(--text-secondary); }
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-page);
}
@media (max-width: 760px) {
  .app-shell { flex-direction: column; height: 100dvh; }
  .desktop-sidebar { display: none; }
  .mobile-topbar { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; min-height: 52px; border-bottom: 1px solid var(--border-default); background: var(--bg-surface); }
  .app-main { height: auto; min-height: 0; }
}
</style>
