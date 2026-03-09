<script setup lang="ts">
import { ref, computed } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppMediaInfoBar from '@/components/common/AppMediaInfoBar.vue'
import { useToast } from '@/composables/useToast'

const toast = useToast()

// 子功能列表
const subFunctions = [
  { id: 'transcode', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'cut', name: '剪輯', icon: 'bi-scissors', comingSoon: true },
  { id: 'volume', name: '音量調整', icon: 'bi-volume-up-fill', comingSoon: true },
  { id: 'normalize', name: '音量正規化', icon: 'bi-soundwave', comingSoon: true },
  { id: 'merge', name: '合併', icon: 'bi-union', comingSoon: true },
]

const currentFunction = ref('transcode')

// View 專屬狀態
const resultPreview = ref<string | null>(null)
const isProcessing = ref(false)
const hasFile = ref(false)
const currentFileName = ref('')

const hasResult = computed(() => !!resultPreview.value)

// 轉檔設定
const outputFormat = ref('mp3')
const bitrate = ref('192k')
const sampleRate = ref('')

const formats = [
  { value: 'mp3', label: 'MP3' },
  { value: 'aac', label: 'AAC' },
  { value: 'flac', label: 'FLAC (無損)' },
  { value: 'wav', label: 'WAV' },
  { value: 'ogg', label: 'OGG' },
  { value: 'm4a', label: 'M4A' },
]

const bitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

const sampleRates = [
  { value: '', label: '保持原始' },
  { value: '44100', label: '44.1 kHz' },
  { value: '48000', label: '48 kHz' },
]

function selectFunction(id: string) {
  currentFunction.value = id
}

function executeProcess() {
  // TODO: 接後端 API
  toast.show('此功能尚未實作', { type: 'info', icon: 'bi-info-circle' })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getAudioInfoItems(file: File) {
  const ext = file.name.split('.').pop()?.toUpperCase() ?? '—'
  return [
    { icon: 'bi-file-earmark-music', label: ext },
    { icon: 'bi-hdd', label: formatSize(file.size) },
  ]
}

function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  currentFileName.value = file.name
  resultPreview.value = null
}
</script>

<template>
  <ToolLayout
    title="音訊工具"
    accept-type="audio"
    upload-icon="bi-music-note-beamed"
    upload-label="拖曳音訊檔案到這裡"
    upload-accept="audio/*"
    hide-preview-tabs
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="!hasFile || isProcessing"
    :execute-loading="isProcessing"
    execute-label="執行轉檔"
    @select-function="selectFunction"
    @execute="executeProcess"
    @file="handleFile"
  >
    <!-- 預覽區域 -->
    <template #preview="{ file, previewUrl }">
      <div class="preview-display">
        <div class="audio-preview">
          <div class="audio-icon">
            <i class="bi bi-music-note-beamed"></i>
          </div>
          <div class="audio-info">
            <p class="filename">{{ file.name }}</p>
            <audio
              :src="previewUrl"
              controls
              class="audio-player"
            ></audio>
          </div>
        </div>
        <AppMediaInfoBar :items="getAudioInfoItems(file)" />
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <!-- 轉檔設定 -->
        <div v-if="currentFunction === 'transcode'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-arrow-repeat me-2"></i>轉檔設定
          </h6>

          <div class="form-group">
            <label>輸出格式</label>
            <AppSelect v-model="outputFormat" :options="formats" />
          </div>

          <div class="form-group">
            <label>位元率</label>
            <AppSelect v-model="bitrate" :options="bitrates" />
          </div>

          <div class="form-group">
            <label>取樣率</label>
            <AppSelect v-model="sampleRate" :options="sampleRates" />
          </div>
        </div>

        <!-- 其他功能 -->
        <div v-if="currentFunction === 'cut'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>剪輯設定</h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'volume'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-volume-up-fill me-2"></i>音量調整</h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'normalize'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-soundwave me-2"></i>音量正規化</h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'merge'" class="function-settings">
          <h6 class="settings-title"><i class="bi bi-union me-2"></i>合併音訊</h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.audio-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
  padding: 2rem;
  background: var(--input-bg);
  border-radius: 16px;
  min-width: 400px;
}

.audio-icon {
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-warning) 0%, #d97706 100%);
  border-radius: 20px;

  i {
    font-size: 3rem;
    color: white;
  }
}

.audio-info {
  text-align: center;
  width: 100%;
}

.filename {
  color: var(--text-primary);
  font-size: 1rem;
  margin-bottom: 1rem;
  word-break: break-all;
}

.audio-player {
  width: 100%;
  max-width: 350px;
}

.settings-form { color: var(--text-primary); }

.function-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-title {
  display: flex;
  align-items: center;
  font-size: 1rem;
  font-weight: 500;
  margin: 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  label { font-size: 0.85rem; color: var(--text-secondary); }
}

.text-muted { color: var(--text-muted); }
</style>
