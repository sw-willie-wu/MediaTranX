<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirm } from '@/composables/useConfirm'
import { apiFetch } from '@/composables/useApi'
import AppIcon from '@/assets/icon.svg'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import { useVideoDownloadStore } from '@/stores/videoDownload'
import { useUpdateStore } from '@/stores/update'

const { t } = useI18n()
const { confirm } = useConfirm()
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const electron = (window as any).electron

// ── Software update ──────────────────────────────────────────────────────────
const update = useUpdateStore()
const FREQ_OPTIONS: UpdateFrequency[] = ['startup', 'weekly', 'monthly', 'never']
const CHECK_ERR_KEYS = ['network', 'rate_limit', 'no_asset', 'generic']

// Status line under the check button. Empty while idle/checking (the button
// itself shows the checking state).
const updateStatusText = computed(() => {
  if (update.status === 'up-to-date') {
    return t('settings.about.update.up_to_date', { version: update.latest })
  }
  if (update.status === 'error') {
    const key = CHECK_ERR_KEYS.includes(update.lastError ?? '') ? update.lastError : 'generic'
    return t(`settings.about.update.err.${key}`)
  }
  return ''
})

function onFreqChange(e: Event) {
  update.setFrequency((e.target as HTMLSelectElement).value as UpdateFrequency)
}

// yt-dlp 元件只在使用者同意影片下載條款後顯示（它是影片下載專用工具）
const vdStore = useVideoDownloadStore()
const vdAgreed = computed(() => vdStore.settings.agreed)

const appVersion = electron?.appVersion ?? 'dev'

// Component versions from backend
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const envInfo = ref<Record<string, any>>({})
const envLoading = ref(true)

// Reinstall state
const reinstalling = ref(false)
const reinstallDone = ref(false)
const reinstallError = ref('')
const reinstallDetail = ref('')
const reinstallPercent = ref(0)

const components = computed(() => envInfo.value.components || {})

const llamaDisplay = computed(() => {
  const llama = components.value.llama
  if (!llama) return '—'
  if (typeof llama === 'object') {
    const variant = llama.variant ? ` (${llama.variant.toUpperCase()})` : ''
    return `${llama.tag}${variant}`
  }
  return llama
})

const pytorchDisplay = computed(() => {
  const pt = components.value.pytorch
  if (!pt) return '—'
  if (typeof pt === 'object') {
    const variant = pt.variant ? ` (${pt.variant})` : ''
    return `${pt.tag}${variant}`
  }
  return pt
})

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toolTag(tool: any): string {
  if (!tool) return '—'
  return typeof tool === 'object' ? tool.tag || '—' : tool
}

async function loadEnvInfo() {
  try {
    const res = await apiFetch('/setup/status')
    if (res.ok) envInfo.value = await res.json()
  } catch (_) {}
  envLoading.value = false
}

async function reinstallEnv() {
  const ok = await confirm({
    title: t('settings.ai.reinstall_title', '重新安裝環境'),
    message: t('settings.ai.reinstall_confirm', '將重新安裝環境並重新下載工具，完成後需要重新啟動。確定嗎？'),
    type: 'warning',
  })
  if (!ok) return

  reinstalling.value = true
  reinstallDone.value = false
  reinstallError.value = ''
  electron?.reinstallAiEnv()
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function handleReinstallProgress(data: any) {
  reinstallPercent.value = data.percent || 0
  reinstallDetail.value = data.detail || ''
  if (data.stage === 'done') {
    reinstalling.value = false
    reinstallDone.value = true
    loadEnvInfo()  // refresh versions
  } else if (data.stage === 'error') {
    reinstalling.value = false
    reinstallError.value = data.detail || 'Unknown error'
  }
}

function restartApp() {
  electron?.restart()
}

onMounted(() => {
  loadEnvInfo()
  if (!vdStore.loaded) vdStore.load()
  electron?.onReinstallProgress(handleReinstallProgress)
})

useAgentPanelHost('settings.about', {
  agentSchema: {
    panelId: 'settings.about',
    fields: [],
    actions: [],
    execute: null,
  },
  getCurrentValues: () => ({}),
  setField: (_field: string, _value: unknown) => {
    throw new Error('agent.error.no_execute_on_settings')
  },
  openField: (_field: string) => {},
  execute: () => { throw new Error('agent.error.no_execute_on_settings') },
  isMultiSelect: () => false,
})
</script>

<template>
  <div class="about-header">
    <div class="about-logo">
      <img :src="AppIcon" alt="MediaTranX Logo" />
    </div>
    <div class="about-title-group">
      <h4 class="about-name">MediaTranX</h4>
      <p class="about-version">{{ $t('settings.about.version', { version: appVersion }) }}</p>
    </div>
  </div>

  <p class="about-desc">
    {{ $t('settings.about.description') }}
  </p>

  <!-- Software update -->
  <h6 class="section-title mt">{{ $t('settings.about.update.title') }}</h6>
  <div class="update-section">
    <div class="update-row">
      <label class="update-auto-label">{{ $t('settings.about.update.auto_label') }}</label>
      <select class="update-freq-select" :value="update.frequency" @change="onFreqChange">
        <option v-for="f in FREQ_OPTIONS" :key="f" :value="f">
          {{ $t(`settings.about.update.freq.${f}`) }}
        </option>
      </select>
    </div>
    <div class="update-row">
      <button
        class="btn-secondary"
        :disabled="update.status === 'checking' || update.downloading"
        @click="update.checkManually()"
      >
        <i class="bi bi-arrow-repeat"></i>
        {{ update.status === 'checking' ? $t('settings.about.update.checking') : $t('settings.about.update.check_btn') }}
      </button>
      <span v-if="updateStatusText" class="update-status" :class="{ error: update.status === 'error' }">
        {{ updateStatusText }}
      </span>
      <span v-if="update.channel === 'dev'" class="dev-channel-tag">{{ t('settings.about.update.channel_dev') }}</span>
    </div>
    <div v-if="update.downloading" class="reinstall-progress">
      <div class="reinstall-bar">
        <div class="reinstall-fill" :style="{ width: update.downloadPercent + '%' }"></div>
      </div>
      <span class="reinstall-detail">
        {{ $t('settings.about.update.downloading', { percent: update.downloadPercent }) }}
      </span>
    </div>
    <div v-else-if="update.pendingInstaller" class="update-row">
      <button class="btn-primary" @click="update.installNow()">
        <i class="bi bi-box-arrow-down"></i> {{ $t('settings.about.update.install_now') }}
      </button>
    </div>
  </div>

  <h6 class="section-title mt">{{ $t('settings.about.support') }}</h6>
  <div class="about-links">
    <a href="https://github.com/sw-willie-wu/MediaTranX" target="_blank" class="btn-secondary about-link-btn"><i class="bi bi-github"></i> {{ $t('settings.about.github') }}</a>
    <button class="btn-secondary about-link-btn"><i class="bi bi-chat-dots"></i> {{ $t('settings.about.feedback') }}</button>
    <button class="btn-secondary about-link-btn"><i class="bi bi-globe"></i> {{ $t('settings.about.website') }}</button>
  </div>

  <h6 class="section-title mt">{{ $t('settings.about.components', '元件資訊') }}</h6>
  <div class="component-list" v-if="!envLoading && components">
    <!-- Binary tools (always shown) -->
    <div class="component-row" v-if="components.ffmpeg">
      <span class="component-label">FFmpeg</span>
      <span class="component-value">{{ toolTag(components.ffmpeg) }}</span>
    </div>
    <div class="component-row" v-if="components.ytdlp && vdAgreed">
      <span class="component-label">yt-dlp</span>
      <span class="component-value">{{ toolTag(components.ytdlp) }}</span>
    </div>
    <div class="component-row" v-if="components.soundfonts">
      <span class="component-label">Soundfonts</span>
      <span class="component-value">MusyngKite GM</span>
    </div>
    <div class="component-row" v-if="components.llama">
      <span class="component-label">llama-server</span>
      <span class="component-value">{{ llamaDisplay }}</span>
    </div>
    <div class="component-row" v-if="components.pytorch">
      <span class="component-label">PyTorch</span>
      <span class="component-value">{{ pytorchDisplay }}</span>
    </div>

  </div>
  <!-- Reinstall -->
  <div class="reinstall-row">
    <template v-if="reinstalling">
      <div class="reinstall-progress">
        <div class="reinstall-bar">
          <div class="reinstall-fill" :style="{ width: reinstallPercent + '%' }"></div>
        </div>
        <span class="reinstall-detail">{{ reinstallDetail }}</span>
      </div>
    </template>
    <template v-else-if="reinstallDone">
      <button class="btn-primary" @click="restartApp">
        <i class="bi bi-arrow-clockwise"></i> {{ $t('settings.ai.restart_now', '立即重新啟動') }}
      </button>
    </template>
    <template v-else-if="reinstallError">
      <p class="reinstall-error"><i class="bi bi-exclamation-triangle"></i> {{ reinstallError }}</p>
      <button class="btn-secondary" @click="reinstallEnv">
        <i class="bi bi-arrow-repeat"></i> {{ $t('settings.ai.retry', '重試') }}
      </button>
    </template>
    <template v-else>
      <button class="btn-secondary" @click="reinstallEnv">
        <i class="bi bi-arrow-repeat"></i> {{ $t('settings.ai.reinstall_button', '重新安裝環境') }}
      </button>
    </template>
  </div>

  <h6 class="section-title mt">{{ $t('settings.about.credits') }}</h6>
  <p class="credits-text">
    {{ $t('settings.about.credits_intro') }}<br/>
    {{ $t('settings.about.credits_list') }}
  </p>

  <div class="about-footer">
    <p>{{ $t('settings.about.copyright') }}</p>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.about-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}

.about-logo img {
  width: 64px;
  height: 64px;
  object-fit: contain;
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
  text-decoration: none;
}

.credits-text {
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.6;
}

.component-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}

.component-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.4rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  font-size: 0.8rem;
}

.component-label { color: var(--text-secondary); }
.component-value { color: var(--text-primary); font-weight: 500; font-family: monospace; }

.reinstall-row { margin-top: 0.75rem; margin-bottom: 0.5rem; }

.reinstall-progress {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.reinstall-bar {
  height: 4px;
  background: var(--input-bg);
  border-radius: 2px;
  overflow: hidden;
}

.reinstall-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.reinstall-detail {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.reinstall-error {
  font-size: 0.8rem;
  color: var(--color-danger);
  margin-bottom: 0.5rem;
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

.update-freq-select {
  background: var(--input-bg);
  color: var(--text-primary);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
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

.about-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--panel-border);
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>
