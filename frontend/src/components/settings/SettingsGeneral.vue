<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useResizableLayout } from '@/composables/useResizableLayout'
import { apiFetch } from '@/composables/useApi'
import { LOCALE_OPTIONS, resolveLocale, saveLocalePreference, getSavedPreference } from '@/i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'

const { locale, t } = useI18n()
const { themeMode, setTheme } = useTheme()
const { resetLayout } = useResizableLayout()

const settings = ref({
  theme: 'system' as ThemeMode,
  language: getSavedPreference(),
  autoCleanTemp: true,
  showSetupWizard: true,
})

const themes = computed(() => [
  { value: 'system', label: t('settings.general.system_theme') },
  { value: 'dark', label: t('settings.general.dark_theme') },
  { value: 'light', label: t('settings.general.light_theme') },
])

const languages = LOCALE_OPTIONS

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

watch(() => settings.value.language, (val) => {
  saveLocalePreference(val as any)
  locale.value = val
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
  <h6 class="section-title">{{ $t('settings.general.appearance') }}</h6>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('settings.general.theme') }}</label>
    <AppSelect v-model="settings.theme" :options="themes" size="sm" />
  </div>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('settings.general.language') }}</label>
    <AppSelect v-model="settings.language" :options="languages" size="sm" />
  </div>

  <div class="setting-item">
    <AppToggle v-model="settings.showSetupWizard">{{ $t('settings.general.show_setup_wizard') }}</AppToggle>
  </div>

  <h6 class="section-title mt">{{ $t('settings.general.layout') }}</h6>

  <div class="setting-item">
    <button class="btn-secondary" @click="resetLayout()">
      <i class="bi bi-layout-three-columns"></i> {{ $t('settings.general.reset_layout') }}
    </button>
  </div>

  <h6 class="section-title mt">{{ $t('settings.general.file_paths') }}</h6>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('settings.general.temp_folder') }}</label>
    <button class="btn-secondary path-btn" @click="selectTempDir">
      <span class="path-text">{{ tempDir || effectiveTempDir }}</span>
      <i class="bi bi-folder2-open"></i>
    </button>
  </div>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('settings.general.models_dir') }}</label>
    <button class="btn-secondary path-btn" @click="selectModelsDir">
      <span class="path-text">{{ modelsDir || effectiveModelsDir }}</span>
      <i class="bi bi-folder2-open"></i>
    </button>
    <p v-if="dirSaved" class="setting-hint setting-hint-warn">
      <i class="bi bi-exclamation-triangle-fill"></i> {{ $t('settings.general.restart_required') }}
    </p>
  </div>

  <div class="setting-item">
    <AppToggle v-model="settings.autoCleanTemp">{{ $t('settings.general.auto_clean_temp') }}</AppToggle>
  </div>

  <h6 class="section-title mt">{{ $t('settings.general.restart_section') }}</h6>

  <div class="setting-item">
    <button class="btn-secondary" @click="restartApp()">
      <i class="bi bi-arrow-counterclockwise"></i> {{ $t('settings.general.restart_app') }}
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
