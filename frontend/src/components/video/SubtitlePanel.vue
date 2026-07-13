<script setup lang="ts">
/**
 * SubtitlePanel — 例外殼（統一參數元件 spec；批 2 Task 2.5）。
 * **不刪、不換 ToolParamHost**——保留自建 task 的職責：apiFetch('/video/subtitle/generate')
 * + 手動 taskStore.addTask + 自管 isLoading/error + 語言清單載入（殼責任）+ agent host。
 * 表單本體（source_language/model_size/output_format/翻譯區塊/進階區）已抽成
 * components/params/video/SubtitleParams.vue（＋ subtitle.meta.ts 提供 schema/buildSubmit/
 * modelRequirements）——本檔改持 `params` ref，透過 `<SubtitleParams v-model:params>` 收發。
 *
 * defineExpose 契約不變（VideoView 掛載法不變，:334-342 殼掛法，見該檔）；agentSchema 沿舊
 * 4 欄清單（language/whisper_model/vocal_separation/output_format，勿擴——殼不是 host）。
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import { isModelInstalled } from '@/components/params/modelGuardUtils'
import SubtitleParams from '@/components/params/video/SubtitleParams.vue'
import { META as SUBTITLE_META } from '@/components/params/video/subtitle.meta'

const { t } = useI18n()

const props = defineProps<{
  fileId: string | null
  mediaInfo: {
    duration: number
    width: number
    height: number
    fps: number
    video_codec: string
    audio_codec: string
    bitrate: number
    file_size: number
  } | null
}>()

const emit = defineEmits<{
  (e: 'submit', taskId: string): void
  (e: 'complete', taskId: string): void
}>()

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const isLoading = ref(false)
const error = ref<string | null>(null)

// ── params（表單本體交給 SubtitleParams.vue；殼只持有整包 params state） ──────────
const params = ref<Record<string, unknown>>(SUBTITLE_META.defaults())

// ── 語言清單（殼責任——source_language 選項來源，傳給 SubtitleParams 當 prop） ───────
const rawLanguages = ref<{ value: string; label: string }[]>([])

const languages = computed(() =>
  rawLanguages.value.map(item =>
    item.value === '' ? { ...item, label: t('common.auto_detect') } : item
  )
)

async function loadLanguages() {
  try {
    const res = await apiFetch('/audio/transcribe/languages')
    if (res.ok) rawLanguages.value = await res.json()
  } catch {}
}

// ── agent 欄位用的靜態清單（沿舊 4 欄清單，勿擴——見檔頭註解；與 SubtitleParams 內部的
// picker 清單各自獨立小重複，避免殼伸手進子元件內部狀態） ─────────────────────────
const modelSizesWithBadge = computed(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map(m => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
)

const outputFormats = computed(() => [
  { value: 'srt', label: t('video.subtitle.srt') },
  { value: 'vtt', label: t('video.subtitle.vtt') },
])

// ── 提交前模型 guard（沿 SUBTITLE_META.modelRequirements 依序：whisper → demucs(若
// vocal_separation) → align(若 align) → translate(若翻譯已啟用且非 remote)——與舊
// submitGenerate 四道 guard 語意等價，見 subtitle.meta.ts 檔頭註解） ─────────────────
async function preflight(): Promise<boolean> {
  const reqs = SUBTITLE_META.modelRequirements?.(params.value) ?? []
  for (const req of reqs) {
    const ready = isModelInstalled(modelStore.models, req)
    const category = req.slot === 'translate' ? 'llm' : 'audio'
    if (!(await guardModelReady(ready, category))) return false
  }
  return true
}

// ── 提交 ────────────────────────────────────────────────────────
async function submitGenerate() {
  if (!(await preflight())) return
  if (!props.fileId) return
  isLoading.value = true
  error.value = null

  try {
    const spec = SUBTITLE_META.buildSubmit!(params.value)
    const body: Record<string, unknown> = { file_id: props.fileId, ...spec.payload }

    const response = await apiFetch(spec.apiPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Subtitle generation failed')
    }

    const result = await response.json()
    const fileName = filesStore.currentFile?.originalName ?? undefined
    const label = t(spec.labelKey)
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'subtitle/generate',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label,
      fileName,
    })
    toast.show(`${t('video.subtitle.start')} ${label}`, { type: 'info', icon: 'bi-badge-cc-fill' })
    emit('submit', result.task_id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    isLoading.value = false
  }
}

const isDisabled = computed(() =>
  isLoading.value || !props.fileId
)

// ── Agent panel registration ──────────────────────────────────────────────────
// NOTE: SubtitlePanel does NOT support multi-select (m16) — hardcoded false.
const agentSchema = {
  panelId: 'video.subtitle',
  fields: [
    { name: 'language', type: 'enum' as const,
      options: () => languages.value.map(l => l.value) },
    { name: 'whisper_model', type: 'enum' as const,
      options: () => modelSizesWithBadge.value.map(m => m.value) },
    { name: 'vocal_separation', type: 'bool' as const },
    { name: 'output_format', type: 'enum' as const,
      options: () => outputFormats.value.map(f => f.value) },
  ],
  actions: [],
  execute: { requiresConfirm: true, label: 'panel.subtitle.execute' },
}

useAgentPanelHost('video.subtitle', {
  agentSchema,
  isMultiSelect: () => false,  // subtitle panel does not support multi-select
  getCurrentValues: () => ({
    language: params.value.source_language ?? '',
    whisper_model: params.value.model_size ?? '',
    vocal_separation: Boolean(params.value.vocal_separation),
    output_format: params.value.output_format ?? '',
  }),
  setField: (field, value) => {
    switch (field) {
      case 'language':
        params.value = { ...params.value, source_language: value as string }
        return value
      case 'whisper_model':
        params.value = { ...params.value, model_size: value as string }
        return value
      case 'vocal_separation': {
        const b = !!value
        params.value = { ...params.value, vocal_separation: b }
        return b
      }
      case 'output_format':
        params.value = { ...params.value, output_format: value as string }
        return value
      default:
        throw new Error(`Unknown field: ${field}`)
    }
  },
  openField: (_field) => {
    // no-op
  },
  execute: async () => {
    await submitGenerate()
    return {}
  },
})

defineExpose({ submitGenerate, isLoading, isDisabled })

onMounted(() => { loadLanguages(); modelStore.ensureLoaded() })
</script>

<template>
  <div class="function-settings">
    <div v-if="error" class="info-box info-box--error">
      <i class="bi bi-exclamation-circle"></i>
      <span>{{ error }}</span>
    </div>

    <SubtitleParams
      v-model:params="params"
      :language-options="languages"
      context="tool"
    />
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
