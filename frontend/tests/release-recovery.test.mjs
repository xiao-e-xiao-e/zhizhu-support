import { test } from 'node:test'
import assert from 'node:assert/strict'
import { installReleaseRecovery, isAssetLoadError } from '../src/utils/releaseRecovery.ts'

function environment({ latest = 'new-release', online = true, storageBlocked = false } = {}) {
  const originals = new Map()
  const calls = { reloads: [], fetches: 0, notices: [], listeners: new Map(), errors: [] }
  const storage = new Map()
  const set = (key, value) => {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  }
  set('location', { href: 'http://localhost/chat', replace: path => calls.reloads.push(path), assign: path => calls.reloads.push(path) })
  set('navigator', { onLine: online })
  set('sessionStorage', {
    getItem: key => storage.get(key),
    setItem: (key, value) => {
      if (storageBlocked) throw Error('Blocked')
      storage.set(key, value)
    },
  })
  set('document', {
    visibilityState: 'visible',
    querySelector: () => ({ content: 'old-release' }),
    createElement: tag => ({ tag, children: [], setAttribute() {}, remove() {}, append(...children) { this.children.push(...children) } }),
    body: { append: element => calls.notices.push(element) },
    addEventListener: (name, handler) => calls.listeners.set(name, handler),
  })
  set('window', { addEventListener: (name, handler) => calls.listeners.set(name, handler) })
  set('DOMParser', class {
    parseFromString(html) { return { querySelector: () => html ? { content: html } : null } }
  })
  set('fetch', async (_url, options) => {
    calls.fetches++
    assert.equal(options.cache, 'no-store')
    return new Response(latest, { headers: { 'Content-Type': 'text/html' } })
  })
  let errorHandler
  installReleaseRecovery({ onError: handler => { errorHandler = handler } })
  return {
    ...calls, calls,
    error: (message = 'Failed to fetch dynamically imported module: /assets/old.js') => errorHandler(new Error(message), { fullPath: '/tickets?status=new' }),
    restore() {
      for (const [key, descriptor] of originals) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor)
        else delete globalThis[key]
      }
    },
  }
}

async function settled() {
  for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve))
}

test('a missing route chunk reloads the requested route only once for a new release', async () => {
  const env = environment()
  try {
    env.error()
    await settled()
    assert.deepEqual(env.calls.reloads, ['/tickets?status=new'])
    env.error()
    await settled()
    assert.equal(env.calls.reloads.length, 1)
    assert.equal(env.calls.notices.at(-1).children[1].textContent, '重新加载')
  } finally { env.restore() }
})

test('offline and same-release failures offer a retry without reload loops', async () => {
  for (const options of [{ online: false }, { latest: 'old-release' }, { latest: '' }, { storageBlocked: true }]) {
    const env = environment(options)
    try {
      env.error('Unable to preload CSS for /assets/route.css')
      await settled()
      assert.equal(env.calls.reloads.length, 0)
      assert.equal(env.calls.notices.length, 1)
      if (options.online === false) assert.equal(env.calls.fetches, 0)
      env.calls.notices[0].children[1].onclick()
      assert.deepEqual(env.calls.reloads, ['/tickets?status=new'])
    } finally { env.restore() }
  }
})

test('resuming an old page offers an update without discarding ongoing work', async () => {
  const env = environment()
  try {
    env.calls.listeners.get('visibilitychange')()
    await settled()
    assert.equal(env.calls.reloads.length, 0)
    assert.match(env.calls.notices[0].children[0].textContent, /工作台已更新/)
  } finally { env.restore() }
})

test('ordinary application errors are not treated as stale assets', () => {
  assert.equal(isAssetLoadError(new Error('Invalid product ID')), false)
  assert.equal(isAssetLoadError(new Error('Importing a module script failed.')), true)
})
