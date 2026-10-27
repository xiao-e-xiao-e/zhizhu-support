import axios from 'axios'

/** 统一 axios 实例：所有接口走 /api 前缀，开发期由 Vite 代理到后端。 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 180_000,
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail
    let message: string
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item: { msg?: string }) => item?.msg ?? JSON.stringify(item))
        .join('；')
    } else if (error?.code === 'ERR_NETWORK') {
      message = '无法连接后端服务，请确认后端已在 8000 端口启动'
    } else {
      message = error?.message ?? '请求失败'
    }
    return Promise.reject(new Error(message))
  },
)
