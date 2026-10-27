import axios, { type InternalAxiosRequestConfig } from 'axios'

type SessionRequest = InternalAxiosRequestConfig & { authGeneration?: number }
let authGeneration = 0

export function getRequestSession() { return authGeneration }

export function resetRequestSession() { authGeneration++ }

/** 统一 axios 实例：所有接口走 /api 前缀，开发期由 Vite 代理到后端。 */
export const http = axios.create({
  baseURL: '/api',
  timeout: 180_000,
  withCredentials: true,
  headers: { 'X-CSRF-Protection': '1' },
})

http.interceptors.request.use((config: SessionRequest) => {
  config.authGeneration = authGeneration
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && error.config?.authGeneration === authGeneration
      && !['/auth/me', '/auth/login'].includes(error.config?.url)) {
      window.dispatchEvent(new Event('auth-expired'))
    }
    const detail = error?.response?.data?.detail
    let message: string
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item: { msg?: string }) => item?.msg ?? JSON.stringify(item))
        .join('；')
    } else if (error?.code === 'ERR_NETWORK') {
      message = '网络连接暂时中断，请检查连接后重试'
    } else {
      message = error?.message ?? '请求失败'
    }
    return Promise.reject(new Error(message))
  },
)
