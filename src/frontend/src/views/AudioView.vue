<script setup lang="ts">
import { ref, computed } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AppSelect from '@/components/common/AppSelect.vue'

// 子功能列表
const subFunctions = [
  { id: 'transcode', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'cut', name: '剪輯', icon: 'bi-scissors' },
  { id: 'volume', name: '音量調整', icon: 'bi-volume-up-fill' },
  { id: 'normalize', name: '音量正規化', icon: 'bi-soundwave' },
  { id: 'merge', name: '合併', icon: 'bi-union' },
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

function handleExport() {
  console.log('Export audio')
}

function executeProcess() {
  isProcessing.value = true
  setTimeout(() => {
    isProcessing.value = false
    resultPreview.value = 'done'
  }, 2000)
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
    @select-function="selectFunction"
    @export="handleExport"
    @file="handleFile"
  >
    <!-- 預覽區域 -->
    <template #preview="{ file, previewUrl, mode }">
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

          <button
            class="execute-btn"
            :disabled="!hasFile || isProcessing"
            @click="executeProcess"
          >
            <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            {{ isProcessing ? '處理中...' : '執行轉檔' }}
          </button>
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
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.text-muted { color: var(--text-muted); }
</style>
