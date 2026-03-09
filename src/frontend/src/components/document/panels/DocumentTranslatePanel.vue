<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { apiFetch, getApiBase } from '@/composables/useApi'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const taskStore = useTaskStore()
const toast = useToast()

const sourceLanguage = ref('en')
const targetLanguage = ref('zh-TW')
const translateModelSize = ref('4b')
const translateLanguages = ref<{ code: string; name: string }[]>([])
const translateStatus = ref<{
  available: boolean
  model_size: string
  model_downloaded: boolean
} | null>(null)

const isSubmitting = ref(false)
const isInstalling = ref(false)
const error = ref<string | null>(null)

const translateModelSizes = [
  { value: '4b', label: '4B (~2.5 GB)', desc: '推薦' },
  { value: '12b', label: '12B (~7.3 GB)', desc: '較佳品質' },
  { value: '27b', label: '27B (~16.5 GB)', desc: '最佳品質' },
]

const languageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

async function loadTranslateLanguages() {
  try {
    const response = await apiFetch('/document/translategemma/languages')
    if (response.ok) {
      translateLanguages.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load translate languages:', e)
  }
}

async function loadTranslateStatus() {
  try {
    const response = await fetch(`${getApiBase()}/document/translategemma/status?model_size=${translateModelSize.value}`)
    if (response.ok) {
      translateStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load translate status:', e)
  }
}

watch(translateModelSize, () => loadTranslateStatus())

async function installTranslate() {
  isInstalling.value = true
  error.value = null

  try {
    const response = await apiFetch('/setup/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feature: 'translategemma' }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '安裝失敗')
    }

    const result = await response.json()

    if (!result.task_id) {
      toast.show('翻譯功能已就緒', { type: 'success' })
      await loadTranslateStatus()
      return
    }

    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'setup/install',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '安裝翻譯功能',
    })
    toast.show('開始安裝翻譯功能，請稍候...', { type: 'info', icon: 'bi-download' })

    const checkDone = setInterval(async () => {
      const task = taskStore.tasks.get(result.task_id)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        clearInterval(checkDone)
        isInstalling.value = false
        if (task.status === 'completed') {
          toast.show('翻譯功能安裝完成', { type: 'success' })
          await loadTranslateStatus()
        } else {
          error.value = '安裝失敗，請查看任務列表'
        }
      }
    }, 2000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '安裝失敗'
    isInstalling.value = false
  }
}

async function execute() {
  if (!props.fileId) return

  isSubmitting.value = true
  error.value = null

  try {
    const response = await apiFetch('/document/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: props.fileId,
        source_language: sourceLanguage.value,
        target_language: targetLanguage.value,
        model_size: translateModelSize.value,
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '翻譯提交失敗')
    }

    const result = await response.json()
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'document/translate',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '文件翻譯',
      fileName: props.currentFileName,
    })
    toast.show('開始文件翻譯', { type: 'info', icon: 'bi-translate' })
    emit('submit', result.task_id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '發生錯誤'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  loadTranslateLanguages()
  loadTranslateStatus()
})

defineExpose({ execute })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-translate me-2"></i>翻譯
    </h6>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 未安裝：顯示安裝按鈕 -->
    <div v-if="translateStatus && !translateStatus.available" class="install-prompt">
      <p class="install-hint">翻譯功能需要額外元件，首次使用前請先安裝</p>
      <button
        class="install-btn"
        :disabled="isInstalling"
        @click="installTranslate"
      >
        <span v-if="isInstalling" class="spinner-border spinner-border-sm me-2"></span>
        <i v-else class="bi bi-download me-1"></i>
        {{ isInstalling ? '安裝中...' : '安裝翻譯功能' }}
      </button>
    </div>

    <!-- 已安裝：顯示設定 -->
    <template v-else-if="!translateStatus || translateStatus.available">
      <div class="form-group">
        <label>來源語言</label>
        <AppSelect v-model="sourceLanguage" :options="languageOptions" size="sm" />
      </div>

      <div class="form-group">
        <label>目標語言</label>
        <AppSelect v-model="targetLanguage" :options="languageOptions" size="sm" />
      </div>

      <div class="form-group">
        <label>翻譯模型</label>
        <AppSelect v-model="translateModelSize" :options="translateModelSizes" size="sm" />
        <div v-if="translateStatus" class="model-status">
          <span class="status-item">
            <i
              class="bi"
              :class="translateStatus.model_downloaded ? 'bi-check-circle-fill status-ok' : 'bi-exclamation-circle-fill status-warn'"
            ></i>
            {{ translateStatus.model_downloaded ? '模型已掛載' : '首次使用自動下載模型' }}
          </span>
        </div>
      </div>

      <button
        class="execute-btn"
        :disabled="isSubmitting || !fileId"
        @click="execute"
      >
        <span v-if="isSubmitting" class="spinner-border spinner-border-sm me-2"></span>
        開始翻譯
      </button>
    </template>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.error-msg {
  padding: 0.75rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 0.85rem;
}

.model-status {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--input-bg);
  border-radius: 6px;
  font-size: 0.8rem;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--text-secondary);
  i { font-size: 0.75rem; }
}

.status-ok { color: #10b981 !important; }
.status-warn { color: #f59e0b !important; }

.install-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  text-align: center;
}

.install-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0;
}

.install-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 0.6rem 1rem;
  background: linear-gradient(135deg, var(--color-info) 0%, var(--color-primary) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3);
  }

  &:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }
}

.execute-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 0.5rem;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}
</style>
