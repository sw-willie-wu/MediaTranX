<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useVideoDownloadStore, type QualityMode } from '@/stores/videoDownload'
import AppToggle from '@/components/common/AppToggle.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'

const { t, tm, rt } = useI18n()
const store = useVideoDownloadStore()

onMounted(() => { if (!store.loaded) store.load() })

// terms_points is an array message; tm() returns the raw list, rt() resolves each
// entry to a display string (handles plain or compiled messages).
const termsPoints = computed<string[]>(() =>
  (tm('video_download.terms_points') as unknown[]).map((p) => rt(p as never)),
)

const agreed = computed(() => store.settings.agreed)
const enabled = computed(() => store.settings.enabled)
const qualityMode = computed(() => store.settings.quality_mode)
const maxHeight = computed(() => store.settings.max_height)

const modeOptions = computed<SelectOption[]>(() => [
  { value: 'auto', label: t('video_download.quality_auto') },
  { value: 'cap', label: t('video_download.quality_cap') },
  { value: 'ask', label: t('video_download.quality_ask') },
])

const HEIGHTS = [2160, 1440, 1080, 720, 480]
const heightOptions = computed<SelectOption[]>(() =>
  HEIGHTS.map((h) => ({ value: h, label: `${h}p` })),
)

async function onAgree(v: boolean) {
  // Un-agreeing also disables (server enforces too).
  await store.update(v ? { agreed: true } : { agreed: false, enabled: false })
}
async function onEnable(v: boolean) { await store.update({ enabled: v }) }
async function onMode(v: QualityMode) { await store.update({ quality_mode: v }) }
async function onMaxHeight(v: number) { await store.update({ max_height: v }) }
</script>

<template>
  <h6 class="section-title">{{ $t('video_download.terms_title') }}</h6>
  <p class="vd-terms">{{ $t('video_download.terms_intro') }}</p>
  <ul class="vd-terms-list">
    <li v-for="(point, i) in termsPoints" :key="i">{{ point }}</li>
  </ul>

  <div class="setting-item">
    <AppToggle
      data-test="vd-agree"
      :model-value="agreed"
      @update:model-value="onAgree"
    >{{ $t('video_download.agree') }}</AppToggle>
  </div>

  <div class="setting-item">
    <AppToggle
      data-test="vd-enable"
      :model-value="enabled"
      :disabled="!agreed"
      @update:model-value="onEnable"
    >{{ $t('video_download.enable') }}</AppToggle>
    <p v-if="enabled" data-test="vd-usage-hint" class="vd-hint">{{ $t('video_download.usage_hint') }}</p>
  </div>

  <div class="setting-item">
    <label class="section-subtitle">{{ $t('video_download.quality_mode') }}</label>
    <AppSelect
      data-test="vd-mode"
      :model-value="qualityMode"
      :options="modeOptions"
      :disabled="!enabled"
      size="sm"
      @update:model-value="onMode"
    />
  </div>

  <div v-if="qualityMode === 'cap'" class="setting-item">
    <label class="section-subtitle">{{ $t('video_download.max_height') }}</label>
    <AppSelect
      data-test="vd-maxheight"
      :model-value="maxHeight"
      :options="heightOptions"
      :disabled="!enabled"
      size="sm"
      @update:model-value="onMaxHeight"
    />
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.vd-terms {
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
}
.vd-terms-list {
  margin: 0 0 8px;
  padding-left: 1.25rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.6;

  li {
    margin-bottom: 4px;
  }
}
.vd-hint {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
}
</style>
