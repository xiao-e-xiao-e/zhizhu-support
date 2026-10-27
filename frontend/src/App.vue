<script setup lang="ts">
import { onMounted } from 'vue'

import AppSidebar from '@/components/AppSidebar.vue'
import { useLibraryStore } from '@/stores/library'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()
const library = useLibraryStore()

onMounted(async () => {
  await settings.loadConfig()
  await library.refresh()
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar />
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
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
</style>
