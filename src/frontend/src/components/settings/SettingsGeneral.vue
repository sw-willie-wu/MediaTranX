<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { apiFetch } from '@/composables/useApi'
import AppSelect from '@/components/common/AppSelect.vue'

const { themeMode, setTheme } = useTheme()

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
  loadDirConfig()
})

watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
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

  <div class="setting-item toggle-item" @click="settings.showSetupWizard = !settings.showSetupWizard">
    <span>啟動時提示安裝AI模組</span>
    <span class="toggle" :class="{ on: settings.showSetupWizard }"><span class="toggle-thumb"></span></span>
  </div>

  <h6 class="section-title mt">檔案路徑</h6>

  <div class="setting-item">
    <label class="section-subtitle">暫存資料夾</label>
    <div class="path-input">
      <input type="text" :value="tempDir || effectiveTempDir" class="form-control" readonly />
      <button class="browse-btn" @click="selectTempDir"><i class="bi bi-folder2-open"></i></button>
    </div>
  </div>

  <div class="setting-item">
    <label class="section-subtitle">AI 模型存放目錄</label>
    <div class="path-input">
      <input type="text" :value="modelsDir || effectiveModelsDir" class="form-control" readonly />
      <button class="browse-btn" @click="selectModelsDir"><i class="bi bi-folder2-open"></i></button>
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
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.form-control {
  width: 100%;
  padding: 0.375rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;

  &::placeholder { color: var(--text-muted); }

  &:focus {
    outline: none;
    border-color: var(--input-border-focus);
    background: var(--input-bg-focus);
  }
}

.path-input {
  display: flex;
  gap: 0.5rem;
  .form-control { flex: 1; }
}

.setting-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0.15rem 0 0 0;
  &.setting-hint-warn { color: #f59e0b; }
}

.browse-btn {
  padding: 0.375rem 0.75rem;
  background: var(--panel-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
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

  &:hover { background: var(--panel-bg-hover); border-color: var(--input-border-focus); }

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
    .toggle-thumb { transform: translateX(16px); }
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
  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); border-color: var(--input-border-focus); }
}
</style>
