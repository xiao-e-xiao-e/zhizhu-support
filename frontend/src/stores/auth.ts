import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { http, resetRequestSession } from '@/api/client'
import { useChatStore } from './chat'
import { useLibraryStore } from './library'
import { useCatalogStore } from './catalog'
import { useConversationsStore } from './conversations'
import { useWorkspaceStore } from './workspace'

export interface AuthUser {
  id: string
  username: string
  role: 'admin' | 'staff' | 'user'
  restrict_products: boolean
  product_ids: string[]
  is_active: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const isStaff = computed(() => ['admin', 'staff'].includes(user.value?.role ?? ''))

  function clear() {
    resetRequestSession()
    user.value = null
    useChatStore().clear()
    useCatalogStore().reset()
    useLibraryStore().reset()
    useConversationsStore().reset()
    useWorkspaceStore().reset()
  }

  async function restore() {
    if (initialized.value) return
    try {
      user.value = (await http.get<AuthUser>('/auth/me')).data
    } catch {
      clear()
    } finally {
      initialized.value = true
    }
  }

  async function login(username: string, password: string) {
    clear()
    user.value = (await http.post<AuthUser>('/auth/login', { username, password })).data
    initialized.value = true
  }

  async function logout() {
    await http.post('/auth/logout')
    clear()
  }

  return { user, initialized, isStaff, restore, login, logout, clear }
})
