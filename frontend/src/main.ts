import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// 样式加载顺序：Element Plus 在前，本地样式在后，保证主题变量覆盖生效
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import './style.css'

import App from './App.vue'
import { router } from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
