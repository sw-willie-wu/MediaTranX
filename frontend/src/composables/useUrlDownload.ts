/**
 * URL 影片下載編排:偵測到 URL → probe → 確認卡 → submit 背景任務。
 * Module-level singleton state(單一 <UrlDownloadCard> 反映之)。enabled 守門在此。
 */
import { ref } from 'vue'
import { apiFetch } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useTaskStore } from '@/stores/tasks'
import { useVideoDownloadStore, type QualityMode } from '@/stores/videoDownload'

export interface ProbeFormat {
  format_id: string
  height: number
  ext: string
  note: string
}
export interface ProbeData {
  downloadable: boolean
  title: string
  duration: number
  uploader: string
  thumbnail: string
  formats: ProbeFormat[]
  reason: string
}
export interface FormatIntent {
  mode: QualityMode
  max_height?: number
  format_id?: string
}

export function buildFormatIntent(
  settings: { quality_mode: QualityMode; max_height: number },
  selectedFormatId: string,
): FormatIntent {
  if (settings.quality_mode === 'cap') return { mode: 'cap', max_height: settings.max_height }
  if (settings.quality_mode === 'ask') return { mode: 'ask', format_id: selectedFormatId }
  return { mode: 'auto' }
}

// ── singleton state ──
const visible = ref(false)
const loading = ref(false)
const probe = ref<ProbeData | null>(null)
const error = ref('') // reason code, '' when none
const pendingUrl = ref('')
const selectedFormatId = ref('')

export function useUrlDownload() {
  const store = useVideoDownloadStore()
  const tasks = useTaskStore()
  const { show } = useToast()

  function cancel(): void {
    visible.value = false
    loading.value = false
    probe.value = null
    error.value = ''
    pendingUrl.value = ''
    selectedFormatId.value = ''
  }

  async function handlePastedUrl(url: string): Promise<void> {
    if (!store.enabled) return // fail-closed gate
    pendingUrl.value = url
    visible.value = true
    loading.value = true
    error.value = ''
    probe.value = null
    try {
      const res = await apiFetch('/video/download/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      const data = (await res.json()) as ProbeData
      if (!res.ok || !data.downloadable) {
        error.value = data?.reason || 'unknown'
      } else {
        probe.value = data
        selectedFormatId.value = data.formats?.[0]?.format_id ?? ''
      }
    } catch {
      error.value = 'network'
    } finally {
      loading.value = false
    }
  }

  async function confirm(): Promise<void> {
    if (!probe.value) return
    const body = {
      url: pendingUrl.value,
      title: probe.value.title || 'video',
      format_intent: buildFormatIntent(store.settings, selectedFormatId.value),
    }
    try {
      const res = await apiFetch('/video/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        tasks.refreshTasks()
        tasks.startPolling()
      } else {
        show('video_download.toast.submit_failed', { type: 'error' })
      }
    } catch {
      show('video_download.toast.submit_failed', { type: 'error' })
    } finally {
      cancel() // hide card; progress now lives in the task manager
    }
  }

  return { visible, loading, probe, error, selectedFormatId, handlePastedUrl, confirm, cancel }
}
