/**
 * Update store — drives the "check for updates" UI (About section + global
 * UpdateModal). All real work is in the Electron main process; this store only
 * calls the `window.electron` update IPC and holds UI state. In a pure-browser
 * context (no `window.electron`) every action is a safe no-op.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import i18n from '@/i18n'
import { useToast } from '@/composables/useToast'

export type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'update-available'
  | 'up-to-date'
  | 'dev'
  | 'error'

// Module-level so App.vue's init() subscribes exactly once even if called again.
let subscribed = false

export const useUpdateStore = defineStore('update', () => {
  const status = ref<UpdateStatus>('idle')
  const current = ref('')
  const latest = ref('')
  const lastError = ref<string | null>(null)
  const frequency = ref<UpdateFrequency>('weekly')
  const downloading = ref(false)
  const downloadPercent = ref(0)
  const pendingInstaller = ref<string | null>(null)
  const modalVisible = ref(false)
  const installing = ref(false)

  const { show } = useToast()
  const t = i18n.global.t
  const api = () => (typeof window !== 'undefined' ? window.electron : undefined)

  function applyResult(r: UpdateCheckResult) {
    status.value = r.status as UpdateStatus
    if (r.current) current.value = r.current
    if (r.latest) latest.value = r.latest
    lastError.value = r.status === 'error' ? (r.error ?? 'generic') : null
  }

  /** Called once from App.vue boot: read prefs + subscribe to main→renderer pushes. */
  async function init() {
    const e = api()
    if (!e) return
    if (!subscribed) {
      subscribed = true
      e.onUpdateAvailable((r) => {
        applyResult(r)
        modalVisible.value = true
      })
      e.onUpdateDownloadProgress((p) => {
        downloadPercent.value = p.percent
      })
    }
    try {
      const prefs = await e.getUpdatePrefs()
      if (prefs) {
        frequency.value = prefs.frequency
        pendingInstaller.value = prefs.pendingInstaller
      }
    } catch {
      /* ignore */
    }
  }

  async function checkManually() {
    const e = api()
    if (!e) return
    status.value = 'checking'
    lastError.value = null
    try {
      const r = await e.checkForUpdates()
      applyResult(r)
      if (r.status === 'update-available') modalVisible.value = true
    } catch {
      status.value = 'error'
      lastError.value = 'generic'
    }
  }

  function setFrequency(f: UpdateFrequency) {
    frequency.value = f
    api()?.setUpdateFrequency(f)
  }

  async function download(then: 'install' | 'only') {
    const e = api()
    if (!e) return
    downloading.value = true
    downloadPercent.value = 0
    lastError.value = null
    try {
      const r = await e.downloadUpdate()
      downloading.value = false
      if (r?.error) {
        lastError.value = r.error
        // While the modal is open the error is shown inline in it (toasts render
        // behind the modal backdrop); only toast when no modal is covering it.
        if (!modalVisible.value) show(t('settings.about.update.download_failed'), { type: 'error' })
        return
      }
      pendingInstaller.value = r.path ?? null
      if (then === 'install') {
        await installNow()
      } else {
        modalVisible.value = false
        show(t('settings.about.update.download_done'), { type: 'success' })
      }
    } catch {
      downloading.value = false
      lastError.value = 'network'
      if (!modalVisible.value) show(t('settings.about.update.download_failed'), { type: 'error' })
    }
  }

  async function installNow() {
    const e = api()
    if (!e) return
    installing.value = true
    try {
      const r = await e.runInstaller()
      // On success the app quits before returning; reaching here means failure.
      installing.value = false
      if (r?.error) {
        lastError.value = r.error
        if (!modalVisible.value) show(t('settings.about.update.install_failed'), { type: 'error' })
      }
    } catch {
      installing.value = false
      lastError.value = 'launch'
      if (!modalVisible.value) show(t('settings.about.update.install_failed'), { type: 'error' })
    }
  }

  function dismissModal() {
    modalVisible.value = false
  }

  return {
    status,
    current,
    latest,
    lastError,
    frequency,
    downloading,
    downloadPercent,
    pendingInstaller,
    modalVisible,
    installing,
    init,
    checkManually,
    setFrequency,
    download,
    installNow,
    dismissModal,
  }
})
