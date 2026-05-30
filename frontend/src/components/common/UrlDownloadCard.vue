<script setup lang="ts">
import { computed } from 'vue'
import { useUrlDownload } from '@/composables/useUrlDownload'
import { useVideoDownloadStore } from '@/stores/videoDownload'

const { visible, loading, probe, error, selectedFormatId, confirm, cancel } = useUrlDownload()
const store = useVideoDownloadStore()

const askMode = computed(() => store.settings.quality_mode === 'ask')

function fmtDuration(s: number): string {
  if (!s || s <= 0) return ''
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<template>
  <div v-if="visible" class="url-download-card" role="dialog" aria-modal="true">
    <div class="udc-backdrop" @click="cancel" />
    <div class="udc-panel">
      <!-- loading -->
      <div v-if="loading" class="udc-loading">
        <i class="bi bi-arrow-repeat udc-spin" />
        <span>{{ $t('video_download.checking') }}</span>
      </div>

      <!-- error -->
      <div v-else-if="error" class="udc-error">
        <i class="bi bi-exclamation-triangle" />
        <p>{{ $t('video_download.reason.' + error) }}</p>
        <button class="udc-btn udc-btn-secondary" @click="cancel">{{ $t('common.close') }}</button>
      </div>

      <!-- downloadable -->
      <div v-else-if="probe" class="udc-info">
        <img v-if="probe.thumbnail" :src="probe.thumbnail" class="udc-thumb" alt="" />
        <div class="udc-meta">
          <h6 class="udc-title">{{ probe.title }}</h6>
          <p class="udc-sub">
            <span v-if="probe.uploader">{{ probe.uploader }}</span>
            <span v-if="fmtDuration(probe.duration)"> · {{ fmtDuration(probe.duration) }}</span>
          </p>
        </div>

        <label v-if="askMode" class="udc-quality">
          {{ $t('video_download.quality') }}
          <select v-model="selectedFormatId" class="udc-select">
            <option v-for="f in probe.formats" :key="f.format_id" :value="f.format_id">
              {{ f.height ? f.height + 'p' : f.note }} ({{ f.ext }})
            </option>
          </select>
        </label>

        <div class="udc-actions">
          <button class="udc-btn udc-btn-secondary" @click="cancel">{{ $t('common.cancel') }}</button>
          <button class="udc-btn udc-btn-primary udc-download-btn" @click="confirm">
            <i class="bi bi-download" /> {{ $t('video_download.download') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.url-download-card {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.udc-backdrop {
  position: absolute;
  inset: 0;
  // Use project's modal-backdrop var (rgba(0,0,0,0.5) dark / 0.4 light)
  background: var(--modal-backdrop);
}

.udc-panel {
  position: relative;
  min-width: 320px;
  max-width: 440px;
  padding: 20px;
  border-radius: 12px;
  // --modal-bg is the project's panel/dialog background variable
  background: var(--modal-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  // mirror AppConfirmDialog shadow (rgba is not a hex code)
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
}

.udc-loading,
.udc-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
}

.udc-spin {
  animation: udc-rotate 1s linear infinite;
}

@keyframes udc-rotate {
  to { transform: rotate(360deg); }
}

.udc-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.udc-thumb {
  width: 100%;
  border-radius: 8px;
  object-fit: cover;
}

.udc-title {
  margin: 0;
  color: var(--text-primary);
}

.udc-sub {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.udc-quality {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--text-secondary);
}

.udc-select {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.85rem;
  padding: 0.35rem 0.5rem;
}

.udc-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.udc-btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &.udc-btn-secondary {
    background: var(--input-bg);
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);

    &:hover {
      background: var(--panel-bg-hover);
      color: var(--text-primary);
    }
  }

  &.udc-btn-primary {
    background: var(--color-primary);
    color: white;

    &:hover {
      background: var(--color-primary-hover);
    }
  }
}
</style>
