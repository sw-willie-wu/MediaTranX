<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useResizableLayout } from '@/composables/useResizableLayout'
import { apiFetch } from '@/composables/useApi'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'

const { themeMode, setTheme } = useTheme()
const { resetLayout } = useResizableLayout()

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

onMounted(() => {
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      settings.value = { ...settings.value, ...JSON.parse(saved) }
    } catch { /* ignore */ }
  }
  settings.value.theme = themeMode.value
  window.electron?.setAutoClean(settings.value.autoCleanTemp)
  loadDirConfig()
})

watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
})

watch(() => settings.value.autoCleanTemp, (val) => {
  window.electron?.setAutoClean(val)
})

watch(settings, () => {
  localStorage.setItem('app-settings', JSON.stringify(settings.value))
}, { deep: true })

// ── 目錄設定 ──────────────────────────────────────────────────

const modelsDir = ref('')
const effectiveModelsDir = ref('')
const tempDir = ref('')
const effectiveTempDir = ref('')
const dirSaved = ref(false)

async function loadDirConfig() {
  try {
    const res = await apiFetch('/setup/config')
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
  await apiFetch('/setup/config', {
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
  if (result) { modelsDir.value = result; await saveDirConfig() }
}

async function selectTempDir() {
  if (!window.electron?.selectFolder) return
  const result = await window.electron.selectFolder()
  if (result) { tempDir.value = result; await saveDirConfig() }
}

function restartApp() {
  ;(window as any).electron?.restart()
}
</script>

<template>
  <h6 class="section-title">外觀選項</h6>

  <div class="setting-item">
    <label class="section-subtitle">主題</label>
    <AppSelect v-model="settings.theme" :options="themes" size="sm" />
  </div>

  <div class="setting-item">
    <label class="section-subtitle">語言</label>
    <AppSelect v-model="settings.language" :options="languages" size="sm" />
  </div>

  <div class="setting-item">
    <AppToggle v-model="settings.showSetupWizard">啟動時提示安裝AI模組</AppToggle>
  </div>

  <h6 class="section-title mt">佈局</h6>

  <div class="setting-item">
    <button class="btn-secondary" @click="resetLayout()">
      <i class="bi bi-layout-three-columns"></i> 重設面板寬度
    </button>
  </div>

  <h6 class="section-title mt">檔案路徑</h6>

  <div class="setting-item">
    <label class="section-subtitle">暫存資料夾</label>
    <button class="btn-secondary path-btn" @click="selectTempDir">
      <span class="path-text">{{ tempDir || effectiveTempDir }}</span>
      <i class="bi bi-folder2-open"></i>
    </button>
  </div>

  <div class="setting-item">
    <label class="section-subtitle">AI 模型存放目錄</label>
    <button class="btn-secondary path-btn" @click="selectModelsDir">
      <span class="path-text">{{ modelsDir || effectiveModelsDir }}</span>
      <i class="bi bi-folder2-open"></i>
    </button>
    <p v-if="dirSaved" class="setting-hint setting-hint-warn">
      <i class="bi bi-exclamation-triangle-fill"></i> 重新啟動後生效
    </p>
  </div>

  <div class="setting-item">
    <AppToggle v-model="settings.autoCleanTemp">關閉時自動清理暫存檔</AppToggle>
  </div>

  <h6 class="section-title mt">重新啟動</h6>

  <div class="setting-item">
    <button class="btn-secondary" @click="restartApp()">
      <i class="bi bi-arrow-counterclockwise"></i> 重新啟動應用程式
    </button>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.path-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  .path-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }
  i { flex-shrink: 0; }
}

.setting-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0.15rem 0 0 0;
  &.setting-hint-warn { color: var(--color-warning); }
}
</style>
