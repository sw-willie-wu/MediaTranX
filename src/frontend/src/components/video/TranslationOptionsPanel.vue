<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useSettingsStore } from '@/stores/settings'
import { useToast } from '@/composables/useToast'
import { apiFetch } from '@/composables/useApi'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'

const taskStore = useTaskStore()
const settings = useSettingsStore()
const toast = useToast()

interface TranslateModelItem {
  key: string
  label: string
  desc: string
  sizeMb: number
  downloaded: boolean
}

const enableTranslation = ref(false)
const selectedTranslateModel = ref('translategemma:4b:Q4_K_M')
const translateEnvAvailable = ref<boolean | null>(null)
const translateModelsFromApi = ref<TranslateModelItem[]>([])
const isInstalling = ref(false)

const translateModelOptions = computed(() =>
  translateModelsFromApi.value.map(m => ({
    value: m.key,
    label: m.label,
    desc: m.desc,
    badge: m.downloaded ? 'ok' as const : 'err' as const,
  }))
)

const targetLanguage = ref('zh-TW')
const keepNames = ref(true)
const translateStyle = ref('colloquial')
const glossaryText = ref('')

const translateLanguages = ref<{ code: string; name: string }[]>([
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'zh-CN', name: '簡體中文' },
  { code: 'en', name: '英文' },
  { code: 'ja', name: '日文' },
  { code: 'ko', name: '韓文' },
])

const translateStyles = ref<{ value: string; label: string }[]>([])

async function loadTranslateStyles() {
  try {
    const res = await apiFetch('/setup/translate-styles')
    if (res.ok) translateStyles.value = await res.json()
  } catch {}
}

const targetLanguageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

const STORAGE_KEY = 'translate-preferences'

function savePreferences() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ translateModel: selectedTranslateModel.value }))
}

function loadPreferences(): string | null {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try {
    const parsed = JSON.parse(saved)
    if (parsed.translateModel) return parsed.translateModel
    if (parsed.modelType && parsed.modelSize && parsed.quantization) {
      return `${parsed.modelType}:${parsed.modelSize}:${parsed.quantization}`
    }
  } catch {}
  return null
}

async function autoRecommend() {
  await settings.loadDeviceInfo()
  const totalBytes = settings.deviceInfo?.memory_total
  if (!totalBytes) return
  const usableMb = totalBytes / (1024 * 1024) - 1500
  const sorted = [...translateModelsFromApi.value].sort((a, b) => b.sizeMb - a.sizeMb)
  const best = sorted.find(m => m.sizeMb <= usableMb)
  if (best) selectedTranslateModel.value = best.key
}

function parseGlossary(): Record<string, string> | undefined {
  const text = glossaryText.value.trim()
  if (!text) return undefined
  const dict: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const sep = trimmed.includes('→') ? '→' : '='
    const parts = trimmed.split(sep)
    if (parts.length >= 2) {
      const src = parts[0].trim()
      const tgt = parts.slice(1).join(sep).trim()
      if (src && tgt) dict[src] = tgt
    }
  }
  return Object.keys(dict).length > 0 ? dict : undefined
}

async function loadTranslateModels() {
  try {
    const [statusRes, modelsRes] = await Promise.all([
      apiFetch('/setup/status'),
      apiFetch('/setup/models'),
    ])
    if (statusRes.ok) {
      const s = await statusRes.json()
      translateEnvAvailable.value = s.ai_env_ready ?? null
    }
    if (!modelsRes.ok) return
    const data = await modelsRes.json()
    translateModelsFromApi.value = (data.models as any[])
      .filter((m: any) => m.category === 'translate')
      .sort((a: any, b: any) => a.size_mb - b.size_mb)
      .map((m: any) => {
        const dashIdx = m.variant.indexOf('-')
        const size = m.variant.slice(0, dashIdx)
        const quant = m.variant.slice(dashIdx + 1)
        const sizeGb = (m.size_mb / 1024).toFixed(1)
        const desc = m.description ? `${sizeGb} GB · ${m.description}` : `${sizeGb} GB`
        return { key: `${m.family}:${size}:${quant}`, label: m.label, desc, sizeMb: m.size_mb, downloaded: m.downloaded }
      })
  } catch {}
}

async function installTranslate() {
  isInstalling.value = true
  try {
    const response = await apiFetch('/setup/initialize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '安裝失敗')
    }
    const result = await response.json()
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'setup/initialize',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '安裝 AI 推理環境',
    })
    toast.show('開始安裝 AI 推理環境，請稍候...', { type: 'info', icon: 'bi-download' })

    const checkDone = setInterval(async () => {
      const task = taskStore.tasks.get(result.task_id)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        clearInterval(checkDone)
        isInstalling.value = false
        if (task.status === 'completed') {
          toast.show('AI 推理環境安裝完成', { type: 'success' })
          await loadTranslateModels()
        }
      }
    }, 2000)
  } catch {
    isInstalling.value = false
  }
}

async function loadTranslateLanguages(retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await apiFetch('/video/translategemma/languages')
      if (response.ok) { translateLanguages.value = await response.json(); return }
    } catch {}
    if (i < retries - 1) await new Promise(r => setTimeout(r, 1000))
  }
}

watch(enableTranslation, (val) => { if (val) loadTranslateLanguages() })
watch(selectedTranslateModel, savePreferences)

onMounted(async () => {
  await Promise.all([loadTranslateModels(), loadTranslateStyles()])
  settings.loadDeviceInfo()
  const saved = loadPreferences()
  if (saved && translateModelsFromApi.value.some(m => m.key === saved)) {
    selectedTranslateModel.value = saved
  } else {
    await autoRecommend()
  }
})

defineExpose({
  enableTranslation,
  targetLanguage,
  selectedTranslateModel,
  keepNames,
  translateStyle,
  parseGlossary,
})
</script>

<template>
  <div class="form-group">
    <AppToggle v-model="enableTranslation">翻譯字幕</AppToggle>

    <div v-if="enableTranslation" class="sub-params">
      <!-- 未安裝 -->
      <div v-if="translateEnvAvailable === false" class="install-prompt">
        <p class="form-hint">翻譯功能需要 AI 推理環境，首次使用前請先安裝</p>
        <button class="btn-primary" :disabled="isInstalling" @click="installTranslate">
          <span v-if="isInstalling" class="spinner-border spinner-border-sm"></span>
          <i v-else class="bi bi-download"></i>
          {{ isInstalling ? '安裝中...' : '安裝 AI 推理環境' }}
        </button>
      </div>

      <!-- 已安裝 -->
      <template v-else>
        <div class="form-group">
          <label class="sub-label">目標語言</label>
          <AppSelect v-model="targetLanguage" :options="targetLanguageOptions" size="sm" />
        </div>

        <div class="form-group">
          <label class="sub-label">翻譯模型</label>
          <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" size="sm" />
        </div>

        <div class="form-group">
          <label class="sub-label">翻譯風格</label>
          <AppSelect v-model="translateStyle" :options="translateStyles" size="sm" />
        </div>

        <div class="option-row">
          <AppToggle v-model="keepNames">保留人名和專有名詞原文</AppToggle>
          <span class="form-hint">如：角色名、地名、作品名等不翻譯</span>
        </div>

        <div class="form-group">
          <label class="sub-label">專有名詞字典</label>
          <textarea
            v-model="glossaryText"
            class="form-input glossary-input"
            rows="3"
            placeholder="每行一筆，格式：原文 → 譯文&#10;例如：&#10;アノン → Anon&#10;MyGO → MyGO"
          ></textarea>
          <small class="form-hint">指定特定詞彙的翻譯方式</small>
        </div>
      </template>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.install-prompt {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.option-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.glossary-input {
  resize: vertical;
  font-family: monospace;
  line-height: 1.6;
}
</style>
