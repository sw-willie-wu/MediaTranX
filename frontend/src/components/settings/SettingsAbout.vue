<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppIcon from '@/assets/icon.svg'

const { t } = useI18n()

function restartApp() {
  ;(window as any).electron?.restart()
}
</script>

<template>
  <div class="about-header">
    <div class="about-logo">
      <img :src="AppIcon" alt="MediaTranX Logo" />
    </div>
    <div class="about-title-group">
      <h4 class="about-name">MediaTranX</h4>
      <p class="about-version">{{ $t('settings.about.version') }}</p>
    </div>
  </div>

  <p class="about-desc">
    {{ $t('settings.about.description') }}
  </p>

  <h6 class="section-title mt">{{ $t('settings.about.support') }}</h6>
  <div class="about-links">
    <a href="https://github.com/sw-willie-wu/MediaTranX" target="_blank" class="btn-secondary about-link-btn"><i class="bi bi-github"></i> {{ $t('settings.about.github') }}</a>
    <button class="btn-secondary about-link-btn"><i class="bi bi-chat-dots"></i> {{ $t('settings.about.feedback') }}</button>
    <button class="btn-secondary about-link-btn"><i class="bi bi-globe"></i> {{ $t('settings.about.website') }}</button>
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

.about-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--panel-border);
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>
