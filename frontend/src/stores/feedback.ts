// frontend/src/stores/feedback.ts
import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { apiFetch } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'

export type FeedbackType = 'bug' | 'feature' | 'other'

export interface DiagnosticsSections {
  app_version: string
  env_summary: string
  task_context: string
  log_tail: string
}

const t = (k: string) => i18n.global.t(k)

export const useFeedbackStore = defineStore('feedback', () => {
  const modalVisible = ref(false)
  const form = reactive({ type: 'bug' as FeedbackType, description: '', email: '' })
  const includeDiagnostics = ref(true)
  const userTouchedInclude = ref(false)
  const taskId = ref<string | null>(null)
  const snapshot = ref<DiagnosticsSections | null>(null)
  const snapshotError = ref(false)
  const fetching = ref(false)
  const submitting = ref(false)
  const { show } = useToast()

  function defaultInclude(type: FeedbackType) {
    return type === 'bug'
  }

  async function fetchDiagnostics() {
    fetching.value = true
    snapshotError.value = false
    try {
      const q = taskId.value ? `?task_id=${encodeURIComponent(taskId.value)}` : ''
      const res = await apiFetch(`/feedback/diagnostics${q}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      snapshot.value = await res.json()
    } catch {
      snapshot.value = null
      snapshotError.value = true
    } finally {
      fetching.value = false
    }
  }

  async function openFeedback(opts?: { type?: FeedbackType; taskId?: string }) {
    form.type = opts?.type ?? 'bug'
    form.description = ''
    form.email = ''
    taskId.value = opts?.taskId ?? null
    userTouchedInclude.value = false
    includeDiagnostics.value = defaultInclude(form.type)
    snapshot.value = null
    snapshotError.value = false
    modalVisible.value = true
    if (includeDiagnostics.value) await fetchDiagnostics()
  }

  function dismiss() {
    modalVisible.value = false
  }

  async function setType(type: FeedbackType) {
    form.type = type
    if (!userTouchedInclude.value) {
      const next = defaultInclude(type)
      if (next !== includeDiagnostics.value) {
        includeDiagnostics.value = next
        if (next && !snapshot.value) await fetchDiagnostics()
      }
    }
  }

  async function toggleInclude(value: boolean) {
    userTouchedInclude.value = true
    includeDiagnostics.value = value
    if (value) {
      await fetchDiagnostics()   // spec §3.1：重新勾選一律重新 GET、換新快照
    } else {
      snapshot.value = null      // 取消勾選即丟棄舊快照，杜絕 stale
    }
  }

  async function submit() {
    if (submitting.value || !form.description.trim()) return
    // 勾選但無快照：先重試一次 GET，仍失敗 → toast + 自動取消勾選（不 POST 缺 body 吃 400；
    // 使用者可自行決定是否不附診斷送出）
    if (includeDiagnostics.value && !snapshot.value) {
      await fetchDiagnostics()
      if (!snapshot.value) {
        show(t('feedback.diag_fetch_failed'), { type: 'error' })
        includeDiagnostics.value = false
        userTouchedInclude.value = true
        return
      }
    }
    submitting.value = true
    try {
      const body: Record<string, unknown> = {
        type: form.type,
        description: form.description,
        include_diagnostics: includeDiagnostics.value,
      }
      if (form.email.trim()) body.email = form.email.trim()
      if (includeDiagnostics.value && snapshot.value) body.diagnostics = snapshot.value
      const res = await apiFetch('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.status === 204) {
        show(t('feedback.success'), { type: 'success' })
        modalVisible.value = false
        return
      }
      let prefill: string | undefined
      try {
        prefill = (await res.json())?.prefill_url
      } catch { /* 非 JSON 錯誤體 */ }
      showFailure(prefill)
    } catch {
      showFailure(undefined)
    } finally {
      submitting.value = false
    }
  }

  function showFailure(prefillUrl?: string) {
    show(t('feedback.failed'), {
      type: 'error',
      duration: 0,
      action: prefillUrl
        ? {
            label: t('feedback.use_browser'),
            callback: () => {
              const el = (window as any).electron
              if (el?.openExternal) el.openExternal(prefillUrl)
              else window.open(prefillUrl, '_blank')
            },
          }
        : undefined,
    })
  }

  return {
    modalVisible, form, includeDiagnostics, userTouchedInclude, taskId,
    snapshot, snapshotError, fetching, submitting,
    openFeedback, dismiss, setType, toggleInclude, fetchDiagnostics, submit,
  }
})
