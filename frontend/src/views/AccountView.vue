<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http } from '@/api/client'
import { useAuthStore, type AuthUser } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const users = ref<AuthUser[]>([])
const error = ref('')
const creating = ref(false)
const changing = ref(false)
const draft = reactive({ username: '', password: '', role: 'user', restrict_products: false, product_ids: [] as string[] })
const products = ref<{id: string; name: string}[]>([])
const permissionUser = ref<AuthUser | null>(null)
const permissions = reactive({ restrict_products: false, product_ids: [] as string[] })
function editPermissions(user: AuthUser) { permissionUser.value = user; permissions.restrict_products = user.restrict_products; permissions.product_ids = [...user.product_ids] }
async function savePermissions() {
  try { await http.patch(`/auth/users/${permissionUser.value!.id}`, permissions); permissionUser.value = null; await refresh(); ElMessage.success('产品权限已更新') }
  catch (e) { error.value = (e as Error).message }
}
const password = reactive({ old_password: '', new_password: '', confirm: '' })
const roles: Record<string, string> = { admin: '管理员', staff: '客服', user: '用户' }

async function refresh() {
  if (auth.user?.role !== 'admin') return
  try {
    users.value = (await http.get<AuthUser[]>('/auth/users')).data
    products.value = (await http.get('/products')).data
    error.value = ''
  } catch (e) { error.value = (e as Error).message }
}
onMounted(refresh)

async function createUser() {
  creating.value = true
  error.value = ''
  try {
    await http.post('/auth/users', draft)
    draft.username = ''; draft.password = ''; draft.role = 'user'; draft.restrict_products = false; draft.product_ids = []
    ElMessage.success('账号已创建')
    await refresh()
  } catch (e) { error.value = (e as Error).message }
  finally { creating.value = false }
}

async function toggle(user: AuthUser) {
  try {
    await ElMessageBox.confirm(`确定${user.is_active ? '停用' : '启用'}账号「${user.username}」？`, '账号状态')
  } catch { return }
  try {
    await http.patch(`/auth/users/${user.id}`, { is_active: !user.is_active })
    await refresh()
  } catch (e) { error.value = (e as Error).message }
}

async function changePassword() {
  if (password.new_password !== password.confirm) { ElMessage.error('两次新密码不一致'); return }
  changing.value = true
  try {
    await http.post('/auth/password', { old_password: password.old_password, new_password: password.new_password })
    password.old_password = ''; password.new_password = ''; password.confirm = ''
    auth.clear()
    ElMessage.success('密码已更新，请重新登录')
    await router.replace('/login')
  } catch (e) { error.value = (e as Error).message }
  finally { changing.value = false }
}
</script>

<template>
  <div class="account-page">
    <h1 class="page-title">账号设置</h1>
    <p class="page-desc">{{ auth.user?.username }} · {{ roles[auth.user?.role ?? 'user'] }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <section class="card section">
      <h2>修改密码</h2>
      <p>更新后，所有设备上的登录会话都会失效。</p>
      <form class="password-form" @submit.prevent="changePassword">
        <el-input v-model="password.old_password" type="password" autocomplete="current-password" placeholder="当前密码" show-password maxlength="128" />
        <el-input v-model="password.new_password" type="password" autocomplete="new-password" placeholder="新密码，至少 12 位" show-password minlength="12" maxlength="128" />
        <el-input v-model="password.confirm" type="password" autocomplete="new-password" placeholder="再次输入新密码" show-password maxlength="128" />
        <el-button type="primary" native-type="submit" :loading="changing" :disabled="!password.old_password || password.new_password.length < 12 || !password.confirm">更新密码</el-button>
      </form>
    </section>
    <section v-if="auth.user?.role === 'admin'" class="card section">
      <h2>团队账号</h2>
      <form class="create-form" @submit.prevent="createUser">
        <el-input v-model="draft.username" placeholder="用户名：字母、数字、点、下划线或短横线" maxlength="64" autocomplete="off" />
        <el-input v-model="draft.password" type="password" placeholder="初始密码，至少 12 位" autocomplete="new-password" show-password maxlength="128" />
        <el-select v-model="draft.role"><el-option v-for="(label, value) in roles" :key="value" :value="value" :label="label" /></el-select>
        <el-switch v-model="draft.restrict_products" active-text="指定可访问产品" />
        <el-select v-if="draft.restrict_products" v-model="draft.product_ids" multiple placeholder="选择产品"><el-option v-for="p in products" :key="p.id" :value="p.id" :label="p.name" /></el-select>
        <el-button type="primary" native-type="submit" :loading="creating" :disabled="draft.username.length < 3 || draft.password.length < 12">创建账号</el-button>
      </form>
      <el-table :data="users" style="width: 100%">
        <el-table-column prop="username" label="用户名" />
        <el-table-column label="角色"><template #default="{ row }">{{ roles[row.role] }}</template></el-table-column>
        <el-table-column label="状态"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '正常' : '已停用' }}</el-tag></template></el-table-column>
        <el-table-column label="产品范围"><template #default="{ row }">{{ row.restrict_products ? products.filter(p => row.product_ids.includes(p.id)).map(p => p.name).join('、') || '暂无产品权限' : '全部产品' }}</template></el-table-column>
        <el-table-column label="操作" width="180"><template #default="{ row }"><el-button link @click="editPermissions(row)">产品权限</el-button><el-button link :disabled="row.id === auth.user?.id" @click="toggle(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template></el-table-column>
      </el-table>
    </section>
    <el-dialog :model-value="!!permissionUser" title="产品访问权限" width="480px" @close="permissionUser = null">
      <p>{{ permissionUser?.username }}</p>
      <el-switch v-model="permissions.restrict_products" active-text="仅访问指定产品" inactive-text="全部产品" />
      <el-select v-if="permissions.restrict_products" v-model="permissions.product_ids" multiple placeholder="选择可访问的产品" style="width: 100%; margin: 18px 0"><el-option v-for="p in products" :key="p.id" :value="p.id" :label="p.name" /></el-select>
      <p v-if="permissions.restrict_products && !permissions.product_ids.length">未选择产品时，该账号将无法访问产品资料。</p>
      <template #footer><el-button @click="permissionUser = null">取消</el-button><el-button type="primary" @click="savePermissions">保存权限</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.account-page { height: 100%; overflow: auto; padding: 30px; }
.section { margin-top: 22px; padding: 24px; }
h2 { font-size: 17px; margin-bottom: 8px; }
p { color: var(--text-secondary); }
.password-form { display: grid; gap: 12px; max-width: 360px; margin-top: 18px; }
.create-form { display: grid; grid-template-columns: 2fr 2fr 1fr auto; gap: 12px; margin: 18px 0; }
@media (max-width: 1000px) { .create-form { grid-template-columns: 1fr; } }
</style>
