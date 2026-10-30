<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { brand } from '@/config/branding'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
async function submit() {
  if (!username.value.trim() || !password.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    password.value = ''
    const redirect = route.query.redirect
    await router.replace(typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
      ? redirect : '/assistant')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">知</div>
      <h1>{{ brand.name }}</h1>
      <p class="product-name">{{ brand.description }}</p>
      <p class="intro">查找产品知识，获得排查建议，跟进问题处理。</p>
      <form @submit.prevent="submit()">
        <label for="username">用户名</label>
        <el-input id="username" v-model="username" autocomplete="username" maxlength="64" size="large" placeholder="请输入用户名" />
        <label for="password">密码</label>
        <el-input id="password" v-model="password" type="password" autocomplete="current-password" maxlength="128" show-password size="large" placeholder="请输入密码" />
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
        <el-button type="primary" native-type="submit" size="large" :loading="loading" :disabled="!username.trim() || !password">登录</el-button>
      </form>
      <p class="hint">账号由团队管理员创建。忘记密码或尚无账号时，请联系管理员。</p>
    </section>

  </main>
</template>

<style scoped>
.login-page { min-height: 100vh; display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 28px; padding: 32px 24px; background: radial-gradient(ellipse at top, #e0e7ff, #f4f5f7 65%); }
.login-card { width: 100%; max-width: 420px; padding: 36px; background: white; border: 1px solid var(--border-default); border-radius: 18px; box-shadow: var(--shadow-md); }
.login-brand { width: 44px; height: 44px; display: grid; place-items: center; background: var(--brand-600); color: white; border-radius: 12px; font-size: 22px; margin-bottom: 22px; }
h1 { font-size: 24px; margin-bottom: 8px; }
.product-name { color: var(--brand-600); font-size: 13px; margin-bottom: 12px; }
.intro { color: var(--text-secondary); margin-bottom: 24px; }
label { display: block; margin: 16px 0 6px; font-weight: 500; }
.login-card .el-button { width: 100%; margin-top: 24px; }
.el-alert { margin-top: 16px; }
.hint { color: var(--text-secondary); font-size: 12px; margin-top: 22px; }
@media(max-width: 600px) { .login-page { padding: 20px 16px; } .login-card { padding: 24px; } }
</style>
