import type { Router } from 'vue-router'

const reloadKey = 'knowledge-release-reload'

export function isAssetLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS|Failed to load module script|Expected a JavaScript-or-Wasm module script/i.test(message)
}

/** Recover failed route chunks after a deployment, at most once per target release. */
export function installReleaseRecovery(router: Router) {
  const loadedRelease = document.querySelector<HTMLMetaElement>('meta[name="app-release"]')?.content
  let checking = false
  let recovering = false
  let banner: HTMLDivElement | null = null

  function notice(message: string, target = location.href) {
    banner?.remove()
    banner = document.createElement('div')
    banner.className = 'release-notice'
    banner.setAttribute('role', 'alert')
    const text = document.createElement('span')
    text.textContent = message
    const retry = document.createElement('button')
    retry.type = 'button'
    retry.textContent = '重新加载'
    retry.onclick = () => { location.assign(target) }
    banner.append(text, retry)
    document.body.append(banner)
  }

  async function latestRelease(): Promise<string | null> {
    if (!navigator.onLine) return null
    try {
      const response = await fetch('/index.html', { cache: 'no-store', signal: AbortSignal.timeout(5000) })
      if (!response.ok || !response.headers.get('Content-Type')?.includes('text/html')) return null
      const html = new DOMParser().parseFromString(await response.text(), 'text/html')
      return html.querySelector<HTMLMetaElement>('meta[name="app-release"]')?.content ?? null
    } catch { return null }
  }

  function claimReload(release: string): boolean {
    try {
      const previous = JSON.parse(sessionStorage.getItem(reloadKey) || 'null')
      if (previous?.release === release && Date.now() - previous.at < 60_000) return false
      sessionStorage.setItem(reloadKey, JSON.stringify({ release, at: Date.now() }))
      return true
    } catch {
      // A blocked storage area cannot enforce a reload limit across navigation.
      return false
    }
  }

  async function recover(error: unknown, target: string): Promise<boolean> {
    if (!isAssetLoadError(error)) return false
    if (recovering) return true
    recovering = true
    try {
      const latest = await latestRelease()
      if (loadedRelease && latest && latest !== loadedRelease && claimReload(latest)) {
        location.replace(target)
      } else {
        notice(latest && latest !== loadedRelease
          ? '工作台已更新，请重新加载后继续。'
          : '页面资源暂时无法加载，请检查网络连接后重试。', target)
      }
    } finally { recovering = false }
    return true
  }

  router.onError((error, to) => {
    if (isAssetLoadError(error)) void recover(error, to.fullPath)
    else console.error(error)
  })

  async function checkForUpdate() {
    if (checking || document.visibilityState !== 'visible' || !loadedRelease) return
    checking = true
    try {
      const latest = await latestRelease()
      if (latest && latest !== loadedRelease) notice('工作台已更新，请重新加载后继续。')
    } finally { checking = false }
  }

  window.addEventListener('pageshow', () => { void checkForUpdate() })
  window.addEventListener('online', () => { void checkForUpdate() })
  document.addEventListener('visibilitychange', () => { void checkForUpdate() })
}
