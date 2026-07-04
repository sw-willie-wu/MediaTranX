<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useResizableLayout } from '@/composables/useResizableLayout'
import { apiFetch } from '@/composables/useApi'
import { LOCALE_OPTIONS, saveLocalePreference, getSavedPreference, type SupportedLocale } from '@/i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import { useUpdateStore } from '@/stores/update'

const { locale, t } = useI18n()
const { themeMode, setTheme } = useTheme()
const { resetLayout } = useResizableLayout()

const settings = ref({
  theme: 'system' as ThemeMode,
  language: getSavedPreference(),
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
  loadDirConfig()
  loadTempStats()
})

watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
})

watch(() => settings.value.language, (val) => {
  saveLocalePreference(val as SupportedLocale)
  locale.value = val
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
  window.electron?.restart()
}

// ── Software update ──────────────────────────────────────────────────────────
const update = useUpdateStore()
const FREQ_ORDER: UpdateFrequency[] = ['startup', 'weekly', 'monthly', 'manual']
const FREQ_OPTIONS = computed(() =>
  FREQ_ORDER.map(v => ({
    value: v,
    label: t(`settings.general.update.freq.${v}`),
    desc: t(`settings.general.update.freq.${v}_desc`),
  })),
)
const CHECK_ERR_KEYS = ['network', 'rate_limit', 'no_asset', 'generic']

// Status line under the check button. Empty while idle/checking (the button
// itself shows the checking state).
const updateStatusText = computed(() => {
  if (update.status === 'up-to-date') {
    return t('settings.general.update.up_to_date', { version: update.latest })
  }
  if (update.status === 'error') {
    const key = CHECK_ERR_KEYS.includes(update.lastError ?? '') ? update.lastError : 'generic'
    return t(`settings.general.update.err.${key}`)
  }
  return ''
})


// ── 暫存狀態 ──────────────────────────────────────────────────

const tempStats = ref<{ total_bytes: number; upload_bytes: number; output_bytes: number } | null>(null)
const clearing = ref(false)

async function loadTempStats() {
  try {
    const res = await apiFetch('/files/stats')
    if (res.ok) tempStats.value = await res.json()
  } catch (e) {
    console.error('loadTempStats failed', e)
  }
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const { confirm: showConfirm } = useConfirm()
const toast = useToast()

async function clearTemp() {
  const ok = await showConfirm({
    message: t('settings.general.confirm_clear_temp'),
    type: 'danger',
    confirmLabel: t('settings.general.clear_temp'),
  })
  if (!ok) return
  clearing.value = true
  try {
    const res = await apiFetch('/files/cleanup', { method: 'POST' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const { useResultsStore } = await import('@/stores/results')
    useResultsStore().resetLocal()
    await loadTempStats()
  } catch (e) {
    console.error('clearTemp failed', e)
    toast.show(t('toast.clear_temp_failed'), { type: 'error', icon: 'bi-x-circle' })
    await loadTempStats()
  } finally {
    clearing.value = false
  }
}

// ── Agent panel host (settings.general) ──────────────────────────────────────

useAgentPanelHost('settings.general', {
  agentSchema: {
    panelId: 'settings.general',
    fields: [
      {
        name: 'theme',
        type: 'enum',
        options: () => ['system', 'dark', 'light'],
      },
      {
        name: 'language',
        type: 'enum',
        options: () => LOCALE_OPTIONS.map(o => o.value),
      },
    ],
    actions: [],
    execute: null,
  },
  getCurrentValues: () => ({
    theme: settings.value.theme,
    language: settings.value.language,
  }),
  setField: (field: string, value: unknown) => {
    if (field === 'theme') {
      settings.value.theme = value as ThemeMode
      return settings.value.theme
    }
    if (field === 'language') {
      settings.value.language = value as SupportedLocale
      return settings.value.language
    }
    throw new Error(`Unknown field: ${field}`)
  },
  openField: (_field: string) => { /* dropdowns open on interaction */ },
  execute: () => { throw new Error('agent.error.no_execute_on_settings') },
  isMultiSelect: () => false,
})
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

  <div class="setting-item temp-stats-row">
    <div class="temp-stats-info">
      <span class="section-subtitle">{{ $t('settings.general.temp_usage') }}</span>
      <span class="temp-stats-value">{{ tempStats ? formatBytes(tempStats.total_bytes) : '—' }}</span>
    </div>
    <button
      class="btn-secondary"
      :disabled="clearing || !tempStats || tempStats.total_bytes === 0"
      @click="clearTemp"
    >
      <i class="bi bi-trash"></i>
      {{ clearing ? $t('settings.general.clearing') : $t('settings.general.clear_temp') }}
    </button>
  </div>

  <!-- Software update -->
  <h6 class="section-title mt">{{ $t('settings.general.update.title') }}</h6>
  <div class="update-section">
    <label class="update-auto-label">{{ $t('settings.general.update.auto_label') }}</label>
    <div class="freq-radio-group">
      <label v-for="opt in FREQ_OPTIONS" :key="opt.value" class="freq-radio-label">
        <input
          type="radio"
          name="update-freq"
          :value="opt.value"
          :checked="update.frequency === opt.value"
          @change="update.setFrequency(opt.value)"
        />
        <span class="freq-radio-text">
          <span class="freq-radio-title">{{ opt.label }}</span>
          <span class="freq-radio-desc">{{ opt.desc }}</span>
        </span>
      </label>
    </div>
    <div v-if="update.frequency === 'manual'" class="update-row">
      <button
        class="btn-secondary"
        :disabled="update.status === 'checking' || update.downloading"
        @click="update.checkManually()"
      >
        <i class="bi bi-arrow-repeat"></i>
        {{ update.status === 'checking' ? $t('settings.general.update.checking') : $t('settings.general.update.check_btn') }}
      </button>
      <span v-if="updateStatusText" class="update-status" :class="{ error: update.status === 'error' }">
        {{ updateStatusText }}
      </span>
      <span v-if="update.channel === 'dev'" class="dev-channel-tag">{{ t('settings.general.update.channel_dev') }}</span>
    </div>
    <div v-if="update.downloading" class="update-progress">
      <div class="update-bar">
        <div class="update-fill" :style="{ width: update.downloadPercent + '%' }"></div>
      </div>
      <span class="update-detail">
        {{ $t('settings.general.update.downloading', { percent: update.downloadPercent }) }}
      </span>
    </div>
    <div v-else-if="update.pendingInstaller" class="update-row">
      <button class="btn-primary" @click="update.installNow()">
        <i class="bi bi-box-arrow-down"></i> {{ $t('settings.general.update.install_now') }}
      </button>
    </div>
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

.update-section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-top: 0.5rem;
}

.update-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.update-auto-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* 頻率選項：仿智慧助手確認策略的垂直 radio 列表（標題+說明） */
.freq-radio-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.freq-radio-label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-secondary);

  input[type='radio'] {
    accent-color: var(--color-primary);
    margin-top: 0.15rem; // 對齊多行文字的第一行
    flex-shrink: 0;
  }
}

.freq-radio-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
}

.freq-radio-title {
  color: var(--text-primary);
}

.freq-radio-desc {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.update-status {
  font-size: 0.8rem;
  color: var(--text-muted);

  &.error { color: var(--color-danger); }
}

.dev-channel-tag {
  font-size: 0.75rem;
  color: var(--text-secondary);
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  padding: 1px 6px;
  margin-left: 8px;
}

.update-progress {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.update-bar {
  height: 4px;
  background: var(--input-bg);
  border-radius: 2px;
  overflow: hidden;
}

.update-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.update-detail {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.temp-stats-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  .temp-stats-info {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }
  .temp-stats-value {
    font-size: 0.85rem;
    color: var(--text-primary);
    font-weight: 500;
  }
}
</style>
