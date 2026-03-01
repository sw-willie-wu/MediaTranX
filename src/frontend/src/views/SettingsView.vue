<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import { useSettingsStore } from '@/stores/settings'
import { useTaskStore } from '@/stores/tasks'
import AppSelect from '@/components/common/AppSelect.vue'
import AppModelList from '@/components/common/AppModelList.vue'
import AppIcon from '@/assets/icon.svg'

const { themeMode, setTheme } = useTheme()
const settingsStore = useSettingsStore()
const taskStore = useTaskStore()

// 當前選中的區塊
const activeSection = ref<'general' | 'system' | 'models' | 'about'>('general')

const sections = [
  { id: 'general' as const, icon: 'bi-sliders', label: '一般' },
  { id: 'system' as const, icon: 'bi-cpu', label: '系統資訊' },
  { id: 'models' as const, icon: 'bi-boxes', label: 'AI 模組管理' },
  { id: 'about' as const, icon: 'bi-info-circle', label: '關於' },
]

// 一般設定
const settings = ref({
  theme: 'system' as ThemeMode,
  language: 'zh-TW',
  autoCleanTemp: true,
  showSetupWizard: true,
})

const themes = [
  { value: 'system', label: '跟隨系統' },
  { value: 'dark', label: '深色' },
  { value: 'light', label: '淺色' },
]

const languages = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
]

// 載入設定
onMounted(() => {
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      settings.value = { ...settings.value, ...parsed }
    } catch {
      // ignore
    }
  }
  // 同步主題
  settings.value.theme = themeMode.value

  // 載入 AI 環境狀態（不依賴 tab 切換）
  loadAiEnvStatus()
  loadDirConfig()
})

// 即時套用主題
watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
})

// 自動儲存一般設定
watch(settings, () => {
  saveSettings()
}, { deep: true })

function saveSettings() {
  localStorage.setItem('app-settings', JSON.stringify(settings.value))
}

// ── AI 推理環境（Torch）────────────────────────────────────────────────────────
const aiEnvLoading = ref(true)
const aiEnvReady = ref(false)
const llamaReady = ref(false)
const aiTorchIndex = ref('cpu')
const aiDriverVersion = ref<string | null>(null)
const aiInstallTaskId = ref<string | null>(null)
const aiInstalling = ref(false)
const aiInstalled = ref(false)

const aiInstallTask = computed(() => {
  if (!aiInstallTaskId.value) return null
  return taskStore.tasks.get(aiInstallTaskId.value) ?? null
})

const AI_CACHE_KEY = 'ai-module-cache'

function readAiCache() {
  try {
    const s = localStorage.getItem(AI_CACHE_KEY)
    return s ? JSON.parse(s) : null
  } catch { return null }
}

function writeAiCache(data: { aiEnvReady: boolean; llamaReady: boolean; torchIndex: string; driverVersion: string | null }) {
  localStorage.setItem(AI_CACHE_KEY, JSON.stringify(data))
}

async function loadAiEnvStatus() {
  // 先從快取同步填入，不需要 loading 狀態
  const cache = readAiCache()
  if (cache) {
    aiEnvReady.value = cache.aiEnvReady
    llamaReady.value = cache.llamaReady
    aiTorchIndex.value = cache.torchIndex ?? 'cpu'
    aiDriverVersion.value = cache.driverVersion ?? null
    aiEnvLoading.value = false
  }

  // 背景向後端確認最新狀態並更新快取
  try {
    const res = await fetch('/api/setup/status')
    if (!res.ok) return
    const data = await res.json()
    aiEnvReady.value = data.ai_env_ready
    llamaReady.value = data.llama_ready ?? false
    aiTorchIndex.value = data.torch_index ?? 'cpu'
    aiDriverVersion.value = data.device?.driver_version ?? null
    aiEnvLoading.value = false
    writeAiCache({
      aiEnvReady: data.ai_env_ready,
      llamaReady: data.llama_ready ?? false,
      torchIndex: data.torch_index ?? 'cpu',
      driverVersion: data.device?.driver_version ?? null,
    })
  } catch (e) {
    console.error('Failed to load AI env status', e)
    if (!cache) aiEnvLoading.value = false
  }
}

async function installAiEnv() {
  aiInstalling.value = true
  try {
    const res = await fetch('/api/setup/initialize', { method: 'POST' })
    if (!res.ok) { aiInstalling.value = false; return }
    const { task_id } = await res.json()
    aiInstallTaskId.value = task_id
    taskStore.addTask({
      taskId: task_id,
      taskType: 'ai.setup',
      status: 'pending',
      progress: 0,
      message: '準備安裝...',
      result: null,
      error: null,
      label: '安裝 AI 推理環境',
      createdAt: new Date(),
      updatedAt: new Date(),
    })
  } catch {
    aiInstalling.value = false
  }
}

watch(
  () => aiInstallTask.value?.status,
  (status) => {
    if (status === 'completed' || status === 'failed') {
      aiInstallTaskId.value = null
      aiInstalling.value = false
      if (status === 'completed') {
        aiInstalled.value = true
        aiEnvReady.value = true
        llamaReady.value = true
        writeAiCache({ aiEnvReady: true, llamaReady: true, torchIndex: aiTorchIndex.value, driverVersion: aiDriverVersion.value })
      }
    }
  },
)

const coreModules = computed(() => {
  const tag = aiTorchIndex.value === 'cpu' ? 'CPU' : aiTorchIndex.value.toUpperCase()
  return [
    { key: 'torch',      icon: 'bi-lightning-charge', name: 'PyTorch',           tag,   desc: '深度學習推理框架',     ready: aiEnvReady.value },
    { key: 'whisper',    icon: 'bi-mic',              name: 'faster-whisper',    tag: '', desc: '語音辨識引擎',        ready: aiEnvReady.value },
    { key: 'llama',      icon: 'bi-translate',        name: 'llama-cpp-python',  tag,   desc: '翻譯推理引擎（GGUF）', ready: llamaReady.value },
    { key: 'hf',         icon: 'bi-cloud-download',   name: 'huggingface-hub',   tag: '', desc: 'AI 模型下載管理',     ready: aiEnvReady.value },
  ]
})

// 切到系統資訊 / AI 模組管理 tab 時自動載入
watch(activeSection, (val) => {
  if (val === 'system' || val === 'models') loadAiEnvStatus()
  if (val === 'system' && !settingsStore.deviceInfo) settingsStore.loadDeviceInfo()
})

// ── 模型管理 ──────────────────────────────────────────────────────────────────

interface ToolItem {
  id: string
  label: string
  description: string
  installed: boolean
  size_mb: number
}

interface ModelItem {
  id: string
  label: string
  category: string
  downloaded: boolean
  size_mb: number
}

interface ModelsStatus {
  tools: ToolItem[]
  models: ModelItem[]
}

const modelStatus = ref<ModelsStatus | null>(null)
const modelStatusLoading = ref(false)
// itemId → taskId
const downloadingTaskId = ref<Record<string, string>>({})

async function loadModelStatus() {
  modelStatusLoading.value = true
  try {
    const res = await fetch('/api/setup/models')
    if (res.ok) {
      modelStatus.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load model status', e)
  } finally {
    modelStatusLoading.value = false
  }
}

async function downloadItem(id: string) {
  const res = await fetch('/api/setup/models/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!res.ok) {
    console.error('Download request failed:', res.statusText)
    return
  }
  const { task_id } = await res.json()
  downloadingTaskId.value[id] = task_id
  taskStore.addTask({
    taskId: task_id,
    taskType: 'setup.download',
    status: 'pending',
    progress: 0,
    message: `下載 ${id}`,
    result: null,
    error: null,
    label: `下載 ${id}`,
    createdAt: new Date(),
    updatedAt: new Date(),
  })
}

async function removeItem(id: string) {
  const res = await fetch('/api/setup/models/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (res.ok) await loadModelStatus()
}

// 監聽任務完成 → 刷新狀態
watch(
  () => taskStore.allTasks.map((t) => t.status),
  () => {
    for (const [itemId, taskId] of Object.entries(downloadingTaskId.value)) {
      const task = taskStore.tasks.get(taskId)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        delete downloadingTaskId.value[itemId]
        loadModelStatus()
      }
    }
  },
)

// 切到模型管理 tab 時重新載入（每次都刷新，確保狀態最新）
watch(activeSection, (val) => {
  if (val === 'models') {
    loadModelStatus()
  }
})

function restartApp() {
  ;(window as any).electron?.restart()
}

// 目錄設定（後端 config.json 管理，不存 localStorage）
const modelsDir = ref('')
const effectiveModelsDir = ref('')
const tempDir = ref('')
const effectiveTempDir = ref('')
const dirSaved = ref(false)

async function loadDirConfig() {
  try {
    const res = await fetch('/api/setup/config')
    if (res.ok) {
      const data = await res.json()
      modelsDir.value = data.models_dir ?? ''
      effectiveModelsDir.value = data.effective_models_dir ?? ''
      tempDir.value = data.temp_dir ?? ''
      effectiveTempDir.value = data.effective_temp_dir ?? ''
    }
  } catch (e) {
    console.error('Failed to load dir config', e)
  }
}

async function saveDirConfig() {
  dirSaved.value = false
  await fetch('/api/setup/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ models_dir: modelsDir.value, temp_dir: tempDir.value }),
  })
  await loadDirConfig()
  dirSaved.value = true
}

async function selectModelsDir() {
  if (!window.electron?.selectFolder) return
  const result = await window.electron.selectFolder()
  if (result) {
    modelsDir.value = result
    await saveDirConfig()
  }
}

async function selectTempDir() {
  if (!window.electron?.selectFolder) return
  const result = await window.electron.selectFolder()
  if (result) {
    tempDir.value = result
    await saveDirConfig()
  }
}

function formatVram(bytes: number | null): string {
  if (!bytes) return ''
  const gb = bytes / (1024 * 1024 * 1024)
  return `${gb.toFixed(1)} GB`
}

function formatRam(bytes: number | null): string {
  if (!bytes) return 'N/A'
  const gb = bytes / (1024 * 1024 * 1024)
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 * 1024)).toFixed(0)} MB`
}
</script>

<template>
  <div class="settings-layout">
    <!-- 左側 sidebar -->
    <aside class="settings-sidebar">
      <div class="sidebar-list">
        <button
          v-for="s in sections"
          :key="s.id"
          class="sidebar-item"
          :class="{ active: activeSection === s.id }"
          @click="activeSection = s.id"
        >
          <i :class="['bi', s.icon]"></i>
          <span>{{ s.label }}</span>
        </button>
      </div>
    </aside>

    <!-- 右側 content -->
    <main class="settings-content">
      <!-- 一般 -->
      <div v-if="activeSection === 'general'" class="section-content">
        <h6 class="section-title">外觀選項</h6>

        <div class="setting-item">
          <label class="section-subtitle">主題</label>
          <AppSelect v-model="settings.theme" :options="themes" size="sm" />
        </div>

        <div class="setting-item">
          <label class="section-subtitle">語言</label>
          <AppSelect v-model="settings.language" :options="languages" size="sm" />
        </div>

        <div class="setting-item toggle-item" @click="settings.showSetupWizard = !settings.showSetupWizard">
          <span>啟動時提示安裝AI模組</span>
          <span class="toggle" :class="{ on: settings.showSetupWizard }"><span class="toggle-thumb"></span></span>
        </div>

        <h6 class="section-title mt">檔案路徑</h6>

        <div class="setting-item">
          <label class="section-subtitle">暫存資料夾</label>
          <div class="path-input">
            <input
              type="text"
              :value="tempDir || effectiveTempDir"
              class="form-control"
              readonly
            />
            <button class="browse-btn" @click="selectTempDir">
              <i class="bi bi-folder2-open"></i>
            </button>
          </div>
        </div>

        <div class="setting-item">
          <label class="section-subtitle">AI 模型存放目錄</label>
          <div class="path-input">
            <input
              type="text"
              :value="modelsDir || effectiveModelsDir"
              class="form-control"
              readonly
            />
            <button class="browse-btn" @click="selectModelsDir">
              <i class="bi bi-folder2-open"></i>
            </button>
          </div>
          <p v-if="dirSaved" class="setting-hint setting-hint-warn">
            <i class="bi bi-exclamation-triangle-fill"></i> 重新啟動後生效
          </p>
        </div>

        <div class="setting-item toggle-item" @click="settings.autoCleanTemp = !settings.autoCleanTemp">
          <span>關閉時自動清理暫存檔</span>
          <span class="toggle" :class="{ on: settings.autoCleanTemp }"><span class="toggle-thumb"></span></span>
        </div>

        <h6 class="section-title mt">重新啟動</h6>

        <div class="setting-item">
          <button class="restart-app-btn" @click="restartApp()">
            <i class="bi bi-arrow-counterclockwise"></i> 重新啟動應用程式
          </button>
        </div>
      </div>

      <!-- 系統資訊 -->
      <div v-if="activeSection === 'system'" class="section-content">
        <h6 class="section-title">系統資訊</h6>

        <div v-if="settingsStore.isLoading" class="gpu-detecting">
          <div class="spinner"></div>
          <span>偵測硬體中...</span>
        </div>

        <template v-else-if="settingsStore.deviceInfo">
          <div class="sys-card">
            <i class="bi bi-window"></i>
            <span class="sys-name">作業系統</span>
            <span class="sys-detail">{{ settingsStore.deviceInfo.os_name }}</span>
          </div>

          <div class="sys-card">
            <i class="bi bi-cpu"></i>
            <span class="sys-name">處理器</span>
            <span class="sys-detail">
              {{ settingsStore.deviceInfo.cpu_name
              }}<template v-if="settingsStore.deviceInfo.cpu_count"
              > ({{ settingsStore.deviceInfo.cpu_count }} 執行緒)</template>
            </span>
          </div>

          <div class="sys-card">
            <i class="bi bi-memory"></i>
            <span class="sys-name">記憶體</span>
            <span class="sys-detail">{{ formatRam(settingsStore.deviceInfo.ram_total) }}</span>
          </div>

          <div class="sys-card">
            <i class="bi bi-gpu-card"></i>
            <span class="sys-name">顯示卡</span>
            <span v-if="settingsStore.deviceInfo.has_nvidia_gpu" class="sys-detail">
              {{ settingsStore.deviceInfo.device_name
              }}<template v-if="settingsStore.deviceInfo.memory_total"
              > · {{ formatVram(settingsStore.deviceInfo.memory_total) }}</template
              ><template v-if="settingsStore.deviceInfo.driver_version"
              > · 驅動 {{ settingsStore.deviceInfo.driver_version }}</template>
            </span>
            <span v-else class="sys-detail sys-muted">未偵測到 GPU</span>
          </div>
        </template>
      </div>

      <!-- AI 模組管理 -->
      <div v-if="activeSection === 'models'" class="section-content">

        <!-- 核心模組 -->
        <h6 class="section-title">核心模組</h6>

        <!-- 四個模組狀態列 -->
        <div class="module-list">
          <div class="module-item" v-for="mod in coreModules" :key="mod.key">
            <div class="module-info">
              <span class="module-label">{{ mod.desc }}</span>
              <span class="module-sub">{{ mod.name }}<template v-if="mod.tag"> ({{ mod.tag.toLowerCase() }})</template></span>
            </div>
            <span v-if="aiEnvLoading" class="module-badge badge-loading">
              <i class="bi bi-three-dots"></i>
            </span>
            <span v-else class="module-badge" :class="mod.ready ? 'badge-ok' : 'badge-off'">
              <i class="bi" :class="mod.ready ? 'bi-check-circle-fill' : 'bi-x-circle-fill'"></i>
              {{ mod.ready ? '已安裝' : '未安裝' }}
            </span>
          </div>
        </div>

        <!-- 安裝進行中 -->
        <div v-if="!aiEnvLoading && aiInstallTask" class="ai-env-card ai-env-installing">
          <div class="ai-env-body">
            <span class="ai-env-name">{{ aiInstallTask.message }}</span>
            <div class="cuda-progress-row">
              <div class="download-progress cuda-progress-bar">
                <div
                  class="progress-bar"
                  :style="{ width: `${(aiInstallTask.progress * 100).toFixed(0)}%` }"
                ></div>
              </div>
              <span class="progress-label">{{ (aiInstallTask.progress * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- 安裝完成，需重啟 -->
        <div v-else-if="!aiEnvLoading && aiInstalled" class="ai-env-card ai-env-ok">
          <i class="bi bi-check-circle-fill"></i>
          <div class="ai-env-body">
            <span class="ai-env-name">安裝完成</span>
            <span class="ai-env-hint">請重新啟動應用程式以套用</span>
            <button class="cuda-restart-btn" @click="restartApp()">
              <i class="bi bi-arrow-counterclockwise"></i> 立即重啟
            </button>
          </div>
        </div>

        <!-- 有模組未啟用 → 顯示安裝/重裝按鈕 -->
        <div v-else-if="!aiEnvLoading && (!aiEnvReady || !llamaReady)" class="ai-env-card ai-env-warn">
          <i class="bi bi-exclamation-triangle-fill"></i>
          <div class="ai-env-body">
            <span class="ai-env-name">核心模組未完整安裝</span>
            <span class="ai-env-hint">
              將安裝 <strong>Torch {{ aiTorchIndex.toUpperCase() }}</strong> + llama-cpp-python
              <template v-if="aiDriverVersion">（驅動 {{ aiDriverVersion }}）</template>
              <template v-else>（CPU 模式）</template>
            </span>
            <button
              class="cuda-download-btn"
              :disabled="aiInstalling"
              @click="installAiEnv"
            >
              <i class="bi bi-download"></i>
              安裝核心模組
            </button>
          </div>
        </div>

        <!-- 模型與工具下載 -->
        <h6 class="section-title mt">模型與工具</h6>

        <div v-if="modelStatusLoading" class="models-loading">
          <div class="spinner"></div>
          <span>載入中...</span>
        </div>

        <template v-else-if="modelStatus">
          <!-- 超解析工具 -->
          <label class="section-subtitle">超解析工具</label>
          <AppModelList
            :items="modelStatus.tools.map(t => ({ ...t, ready: t.installed }))"
            :downloadingTaskId="downloadingTaskId"
            @download="downloadItem"
            @remove="removeItem"
          />

          <!-- 語音識別 -->
          <label class="section-subtitle">語音識別</label>
          <AppModelList
            :items="modelStatus.models
              .filter(m => m.category === 'stt')
              .map(m => ({ ...m, ready: m.downloaded }))"
            :downloadingTaskId="downloadingTaskId"
            @download="downloadItem"
            @remove="removeItem"
          />

          <!-- 翻譯模型 -->
          <label class="section-subtitle">翻譯模型</label>
          <AppModelList
            :items="modelStatus.models
              .filter(m => m.category === 'translate')
              .map(m => ({ ...m, ready: m.downloaded }))"
            :downloadingTaskId="downloadingTaskId"
            @download="downloadItem"
            @remove="removeItem"
          />

          <button class="refresh-btn" @click="loadModelStatus">
            <i class="bi bi-arrow-clockwise"></i> 重新整理
          </button>
        </template>
      </div>

      <!-- 關於 -->
      <div v-if="activeSection === 'about'" class="section-content">
        <div class="about-header">
          <div class="about-logo">
            <img :src="AppIcon" alt="MediaTranX Logo" />
          </div>
          <div class="about-title-group">
            <h4 class="about-name">MediaTranX</h4>
            <p class="about-version">版本 1.0.0 (Production Build)</p>
          </div>
        </div>
        <p class="about-desc">
          本地 AI 驅動的多媒體處理工具，支援影片字幕提取、翻譯、音訊處理、圖片處理等功能。所有 AI 模型均在本機運行，無需上傳資料至雲端，保護您的隱私。
        </p>

        <h6 class="section-title mt">支援與連結</h6>
        <div class="about-links">
          <button class="about-link-btn">
            <i class="bi bi-github"></i> GitHub
          </button>
          <button class="about-link-btn">
            <i class="bi bi-chat-dots"></i> 意見回饋
          </button>
          <button class="about-link-btn">
            <i class="bi bi-globe"></i> 官方網站
          </button>
        </div>

        <h6 class="section-title mt">技術致謝</h6>
        <p class="credits-text">
          MediaTranX 建立在眾多卓越的開源技術之上：<br/>
          Vue 3, Vite, Electron, FFmpeg, OpenAI Whisper, Real-ESRGAN, TranslateGemma, Llama-cpp-python 等。
        </p>

        <div class="about-footer">
          <p>© 2026 MediaTranX Project. All rights reserved.</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.settings-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 1rem;
  padding: 1rem;
}

// 左側 sidebar
.settings-sidebar {
  width: 180px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  padding-top: 0.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.sidebar-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sidebar-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.7rem 1rem;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  i {
    font-size: 1.1rem;
    width: 22px;
  }

  span {
    font-size: 0.9rem;
  }

  &:hover {
    color: var(--text-primary);
    background: var(--panel-bg);
  }

  &.active {
    color: var(--text-primary);
    background: var(--panel-bg);
  }
}

// 右側 content
.settings-content {
  flex: 1;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.section-content {
  max-width: 560px;
  margin: 0 auto;
}

.section-title {
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 0.75rem;

  &.mt {
    margin-top: 2.5rem;
  }
}

.section-subtitle {
  display: block;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
}

.setting-item {
  margin-bottom: 1rem;

  &:last-child {
    margin-bottom: 0;
  }
}

.setting-desc {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin: 0.25rem 0 0 0;
}

.form-control {
  width: 100%;
  padding: 0.375rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;

  &::placeholder {
    color: var(--text-muted);
  }

  &:focus {
    outline: none;
    border-color: var(--input-border-focus);
    background: var(--input-bg-focus);
  }
}

.path-input {
  display: flex;
  gap: 0.5rem;

  .form-control {
    flex: 1;
  }
}

.setting-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0.15rem 0 0 0;

  &.setting-hint-warn {
    color: #f59e0b;
  }
}

.restart-app-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.375rem 0.875rem;
  background: var(--panel-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
    border-color: var(--input-border-focus);
  }
}

.browse-btn {
  padding: 0.375rem 0.75rem;
  background: var(--panel-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}

.toggle-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.375rem 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    border-color: var(--input-border-focus);
  }

  > span:first-child {
    color: var(--text-secondary);
    font-size: 0.875rem;
  }
}

.toggle {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--input-border);
  border-radius: 10px;
  flex-shrink: 0;
  transition: background 0.2s ease;

  .toggle-thumb {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 14px;
    height: 14px;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s ease;
  }

  &.on {
    background: var(--color-primary);

    .toggle-thumb {
      transform: translateX(16px);
    }
  }
}

.gpu-detecting {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--input-bg);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--panel-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 系統資訊卡片（單排 key-value）
.sys-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.375rem 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  margin-bottom: 1rem;

  > i {
    font-size: 0.95rem;
    color: var(--text-secondary);
    flex-shrink: 0;
    width: 18px;
    text-align: center;
  }
}

.sys-name {
  font-size: 0.875rem;
  color: var(--text-muted);
  flex-shrink: 0;
  width: 72px;
}

.sys-detail {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.sys-muted {
    color: var(--text-muted);
  }
}

.cuda-download-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: linear-gradient(135deg, var(--color-info) 0%, var(--color-primary) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.875rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.2s ease;
  width: fit-content;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3);
    color: white;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.cuda-restart-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.25rem;
  padding: 0.4rem 0.875rem;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 8px;
  color: #10b981;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  width: fit-content;

  &:hover {
    background: rgba(16, 185, 129, 0.2);
  }
}

.cuda-progress-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.cuda-progress-bar {
  width: 200px;
}

// 核心模組列表
.module-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.module-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
}

.module-info {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  flex: 1;
  min-width: 0;
}

.module-label {
  font-size: 0.875rem;
  color: var(--text-primary);
  font-weight: 500;
}

.module-sub {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.module-badge {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  font-weight: 500;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  flex-shrink: 0;

  &.badge-ok {
    background: rgba(16, 185, 129, 0.12);
    color: #10b981;
  }
  &.badge-off {
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
  }
  &.badge-loading {
    background: transparent;
    color: var(--text-muted);
  }

  i { font-size: 0.72rem; }
}

// AI 推理環境
.ai-env-card {
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid;
  margin-top: 0.75rem;

  > i {
    font-size: 1.25rem;
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  &.ai-env-ok {
    background: rgba(16, 185, 129, 0.08);
    border-color: rgba(16, 185, 129, 0.25);
    > i { color: #10b981; }
  }

  &.ai-env-warn {
    background: rgba(245, 158, 11, 0.08);
    border-color: rgba(245, 158, 11, 0.25);
    > i { color: #f59e0b; }
  }

  &.ai-env-installing {
    background: var(--input-bg);
    border-color: var(--input-border);
  }
}

.ai-env-body {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
}

.ai-env-name {
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 500;
}

.ai-env-hint {
  color: var(--text-muted);
  font-size: 0.75rem;

  strong {
    color: var(--text-secondary);
  }
}

// 模型管理

.models-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1rem;
  padding: 0.4rem 0.875rem;
  background: transparent;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}

// 關於
.about-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}

.about-logo {
  flex-shrink: 0;
  
  img {
    width: 64px;
    height: 64px;
    object-fit: contain;
  }
}

.about-title-group {
  display: flex;
  flex-direction: column;
}

.about-name {
  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.about-version {
  color: var(--text-muted);
  font-size: 0.875rem;
  margin: 0;
}

.about-desc {
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
  max-width: 560px;
  margin-bottom: 2rem;
}

.about-links {
  display: flex;
  gap: 0.75rem;
}

.about-link-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
    border-color: var(--input-border-focus);
  }
}


.credits-text {
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.6;
}

.about-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--panel-border);
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>
