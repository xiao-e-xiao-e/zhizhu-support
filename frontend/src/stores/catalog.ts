import { ref } from 'vue'
import { defineStore } from 'pinia'
import { listProducts } from '@/api/support'
import type { Product } from '@/types'

export const useCatalogStore = defineStore('catalog', () => {
  const products = ref<Product[]>([])
  const initialized = ref(false)
  const loading = ref(false)
  let generation = 0
  async function refresh() {
    const current = ++generation
    loading.value = true
    try {
      const result = await listProducts()
      if (current === generation) { products.value = result; initialized.value = true }
    } finally { if (current === generation) loading.value = false }
  }
  function reset() { generation++; products.value = []; initialized.value = false; loading.value = false }
  return { products, initialized, loading, refresh, reset }
})
