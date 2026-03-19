<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  currentFileExt: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const router = useRouter()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()

// ── 模型 ──────────────────────────────────────────────────────────────────

const selectedModel = ref('qwen3vl:4b')
const available = ref<boolean | null>(null)

const modelOptions = computed(() => {
  const seen = new Map<string, { value: string; label: string; desc: string; downloaded: boolean }>()
  for (const m of modelStore.byCategory('vlm')) {
    const [size] = m.variant.split(':')
    const key = `${m.family}:${size}`
    if (!seen.has(key)) {
      const labelNoQuant = m.label.split(' ').slice(0, -1).join(' ')
      const descBase = (m.description ?? '').split(' · ')[0]
      const sizeGb = (m.size_mb / 1024).toFixed(1)
      seen.set(key, { value: key, label: labelNoQuant, desc: `~${sizeGb} GB — ${descBase}`, downloaded: m.downloaded })
    } else if (m.downloaded) {
      seen.get(key)!.downloaded = true
    }
  }
  return [...seen.values()].map(opt => ({
    ...opt,
    badge: opt.downloaded ? 'ok' as const : 'err' as const,
  }))
})

// ── 輸出選項 ──────────────────────────────────────────────────────────────

const outputFormat = ref<'md' | 'txt'>('md')
const outputPath = ref('')

const outputFormats = [
  { value: 'md',  label: 'Markdown (.md)' },
  { value: 'txt', label: '純文字 (.txt)' },
]

const isPdfOrImage = computed(() => {
  const ext = props.currentFileExt.toLowerCase()
  return ext === 'pdf' || ['png','jpg','jpeg','webp','bmp','tiff','tif'].includes(ext)
})

const defaultOutputName = computed(() => {
  const stem = props.currentFileName.replace(/\.[^.]+$/, '') || 'output'
  return `${stem}_ocr.${outputFormat.value}`
})

const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  return defaultOutputName.value
})

async function selectOutputFile() {
  if ((window as any).electron?.saveFileDialog) {
    const filter = outputFormat.value === 'md'
      ? { name: 'Markdown', extensions: ['md'] }
      : { name: '純文字', extensions: ['txt'] }
    const result = await (window as any).electron.saveFileDialog({
      title: '選擇輸出位置',
      defaultPath: defaultOutputName.value,
      filters: [filter],
    })
    if (result) outputPath.value = result
  }
}

watch(() => props.fileId, () => { outputPath.value = '' })
watch(outputFormat,       () => { outputPath.value = '' })

// ── 狀態載入 ──────────────────────────────────────────────────────────────

async function checkAvailable() {
  try {
    const [family, size] = selectedModel.value.split(':')
    const res = await apiFetch(`/document/ocr/status?model_id=${family}&size=${size}`)
    if (!res.ok) return
    const data = await res.json()
    available.value = data.available
  } catch {}
}

onMounted(() => { modelStore.ensureLoaded(); checkAvailable() })
watch(selectedModel, checkAvailable)

// ── 執行 ──────────────────────────────────────────────────────────────────

const isDisabled = computed(() =>
  !props.fileId || isProcessing.value || available.value === false || !isPdfOrImage.value
)
const isLoading = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const [family, size] = selectedModel.value.split(':')

  const body: Record<string, any> = {
    file_id: props.fileId,
    model_id: family,
    size,
    format: outputFormat.value,
  }

  if (outputPath.value) {
    const path = outputPath.value.replace(/\\/g, '/')
    const last = path.lastIndexOf('/')
    if (last > 0) {
      body.output_dir      = path.substring(0, last)
      body.output_filename = path.substring(last + 1)
    } else {
      body.output_filename = path
    }
  }

  const taskId = await submitTask('/document/ocr', body, 'OCR 文字辨識', 'document.ocr', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, outputFormat })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-type me-2"></i>文字辨識設定</h6>
    <p class="form-hint">使用 AI 辨識 PDF 或圖片中的文字，輸出為可編輯格式。</p>

    <div v-if="available === false" class="info-box info-box--warn">
      <i class="bi bi-exclamation-triangle"></i>
      <div class="info-box-body">
        <span>llama-server 未找到，請前往設定頁面安裝 AI 核心</span>
        <button class="info-box-action" @click="router.push('/setup')">前往設定</button>
      </div>
    </div>

    <div v-if="!isPdfOrImage && props.fileId" class="info-box info-box--warn">
      <i class="bi bi-info-circle"></i>
      <span>OCR 僅支援 PDF 及圖片格式</span>
    </div>

    <div class="form-group">
      <label>辨識模型</label>
      <AppSelect v-model="selectedModel" :options="modelOptions" size="sm" />
    </div>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" size="sm" />
    </div>

    <div class="form-group">
      <label>輸出檔案</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-select-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

