import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const releaseId = Date.now().toString(36)

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), {
    name: 'release-marker',
    transformIndexHtml: () => [{
      tag: 'meta',
      attrs: { name: 'app-release', content: releaseId },
      injectTo: 'head',
    }],
  }],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 显式绑定 IPv4 回环：默认的 localhost 在 Windows 上会解析到 IPv6 ::1，
    // 导致 127.0.0.1 访问不通，也和后端 127.0.0.1:8000 不在同一族上
    host: '127.0.0.1',
    port: 5173,
    // 端口被占用时直接失败，而不是悄悄换到 5174 —— 端口漂移比报错更难排查
    strictPort: true,
    // 开发期把 /api 转发到后端，前端代码里只写相对路径，
    // 生产环境交给同域的 Nginx / 静态托管即可，无需改代码。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
