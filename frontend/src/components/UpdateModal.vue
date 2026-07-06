<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUpdateStore } from '@/stores/update'

const update = useUpdateStore()
const { t } = useI18n()

// Inline error (toasts render behind this modal's backdrop, so show failures here).
const errorText = computed(() => {
  if (!update.lastError) return ''
  return update.lastError === 'launch'
    ? t('settings.general.update.install_failed')
    : t('settings.general.update.download_failed')
})

function onOverlayClick(e: MouseEvent) {
  // Don't allow dismiss-by-backdrop mid-download (download is non-cancellable).
  if (update.downloading) return
  if ((e.target as HTMLElement).classList.contains('update-overlay')) update.dismissModal()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="update-fade">
      <div
        v-if="update.modalVisible"
        class="update-overlay"
        @click="onOverlayClick"
      >
        <div class="update-dialog">
          <div class="update-icon">
            <i class="bi bi-arrow-up-circle-fill" />
          </div>
          <p class="update-message">
            {{ t('settings.general.update.found', { version: update.latest }) }}
          </p>

          <!-- Downloading: progress bar replaces the buttons -->
          <div v-if="update.downloading" class="update-progress">
            <div class="update-bar">
              <div class="update-fill" :style="{ width: update.downloadPercent + '%' }"></div>
            </div>
            <span class="update-detail">
              {{ t('settings.general.update.downloading', { percent: update.downloadPercent }) }}
            </span>
          </div>

          <!-- Inline error (download/install failure while modal is open) so the
               user still sees it — a toast would render behind the backdrop. -->
          <p v-if="errorText && !update.downloading" class="update-error">
            <i class="bi bi-exclamation-triangle"></i> {{ errorText }}
          </p>

          <!-- Choice: cancel / download only / download & install (retry after error) -->
          <div v-if="!update.downloading" class="update-actions">
            <button class="update-btn cancel" @click="update.dismissModal()">
              {{ t('settings.general.update.cancel') }}
            </button>
            <button class="update-btn secondary" @click="update.download('only')">
              {{ t('settings.general.update.download_only') }}
            </button>
            <button class="update-btn primary" @click="update.download('install')">
              {{ t('settings.general.update.download_install') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.update-overlay {
  position: fixed;
  inset: 0;
  z-index: 20000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(15px);
  -webkit-backdrop-filter: blur(15px);
}

.update-dialog {
  background: rgba(30, 30, 50, 0.35);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem 2rem;
  min-width: 340px;
  max-width: 460px;
  text-align: center;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
}

.update-icon {
  margin-bottom: 0.75rem;

  i {
    font-size: 2rem;
    color: var(--color-primary);
  }
}

.update-message {
  color: var(--text-primary);
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 1.25rem;
}

.update-error {
  color: var(--color-danger);
  font-size: 0.85rem;
  margin-bottom: 0.9rem;
}

.update-actions {
  display: flex;
  gap: 0.6rem;
  justify-content: center;
  flex-wrap: wrap;
}

.update-btn {
  padding: 0.5rem 1.1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;

  &.cancel {
    background: var(--input-bg);
    color: var(--text-secondary);
    border: 1px solid var(--panel-border);

    &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
  }

  &.secondary {
    background: var(--input-bg);
    color: var(--text-primary);
    border: 1px solid var(--panel-border);

    &:hover { background: var(--panel-bg-hover); }
  }

  &.primary {
    background: var(--color-primary);
    color: white;

    &:hover { background: var(--color-primary-hover); }
  }
}

/* Progress bar — mirrors the reinstall bar in SettingsAbout (scoped there, so copied). */
.update-progress {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
}

.update-bar {
  width: 100%;
  height: 6px;
  background: var(--input-bg);
  border-radius: 3px;
  overflow: hidden;
}

.update-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 3px;
  transition: width 0.2s ease;
}

.update-detail {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.update-fade-enter-active,
.update-fade-leave-active {
  transition: opacity 0.15s ease;
}

.update-fade-enter-from,
.update-fade-leave-to {
  opacity: 0;
}
</style>
