import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/knowledge', name: 'knowledge', component: () => import('@/views/KnowledgeView.vue'), meta: { title: '产品资料' } },
    { path: '/assistant', name: 'assistant', component: () => import('@/views/ChatView.vue'), meta: { title: '智能助手' } },
    { path: '/faqs', name: 'faqs', component: () => import('@/views/FAQView.vue'), meta: { title: 'FAQ 知识运营', staff: true } },
    { path: '/products', name: 'products', component: () => import('@/views/ProductsView.vue'), meta: { title: '产品与版本', staff: true } },
    { path: '/tickets', name: 'tickets', component: () => import('@/views/TicketsView.vue'), meta: { title: '工单工作台' } },
    { path: '/tickets/:id', name: 'ticket-detail', component: () => import('@/views/TicketDetailView.vue'), meta: { title: '工单详情' } },
    { path: '/feedback', name: 'feedback', component: () => import('@/views/FeedbackView.vue'), meta: { title: '回答反馈' } },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录', public: true } },
    { path: '/account', name: 'account', component: () => import('@/views/AccountView.vue'), meta: { title: '账号设置' } },
    { path: '/', redirect: '/assistant' },
    { path: '/chat', name: 'chat', redirect: to => ({path: '/assistant', query: to.query, hash: to.hash}) },
    {
      path: '/documents',
      name: 'documents',
      component: () => import('@/views/DocumentsView.vue'),
      meta: { title: '文档管理', staff: true },
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('@/views/HistoryView.vue'),
      meta: { title: '对话历史' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/assistant' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restore()
  if (!to.meta.public && !auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && auth.user) return { name: 'assistant' }
  if (to.meta.staff && !auth.isStaff) return { name: 'assistant' }
})

router.afterEach((to) => {
  const title = to.meta?.title as string | undefined
  document.title = title ? `${title} · 知识库` : '智能客服工作台'
})
