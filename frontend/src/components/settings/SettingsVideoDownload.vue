<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useVideoDownloadStore, type QualityMode } from '@/stores/videoDownload'

const store = useVideoDownloadStore()

onMounted(() => { if (!store.loaded) store.load() })

const agreed = computed(() => store.settings.agreed)
const enabled = computed(() => store.settings.enabled)
const qualityMode = computed(() => store.settings.quality_mode)

const HEIGHTS = [2160, 1440, 1080, 720, 480]

async function onAgree(v: boolean) {
  // Un-agreeing also disables (server enforces too).
  await store.update(v ? { agreed: true } : { agreed: false, enabled: false })
}
async function onEnable(v: boolean) { await store.update({ enabled: v }) }
async function onMode(v: string) { await store.update({ quality_mode: v as QualityMode }) }
async function onMaxHeight(v: string) { await store.update({ max_height: Number(v) }) }
</script>

<template>
  <h6 class="section-title">{{ $t('video_download.terms_title') }}</h6>
  <p class="vd-terms">{{ $t('video_download.terms_body') }}</p>

  <div class="setting-item">
    <label>
      <input
        type="checkbox"
        data-test="vd-agree"
        :checked="agreed"
        @change="onAgree(($event.target as HTMLInputElement).checked)"
      />
      {{ $t('video_download.agree') }}
    </label>
  </div>

  <div class="setting-item">
    <label>
      <input
        type="checkbox"
        data-test="vd-enable"
        :checked="enabled"
        :disabled="!agreed"
        @change="onEnable(($event.target as HTMLInputElement).checked)"
      />
      {{ $t('video_download.enable') }}
    </label>
  </div>

  <div class="setting-item">
    <label>{{ $t('video_download.quality_mode') }}</label>
    <select
      data-test="vd-mode"
      :value="qualityMode"
      :disabled="!enabled"
      @change="onMode(($event.target as HTMLSelectElement).value)"
    >
      <option value="auto">{{ $t('video_download.quality_auto') }}</option>
      <option value="cap">{{ $t('video_download.quality_cap') }}</option>
      <option value="ask">{{ $t('video_download.quality_ask') }}</option>
    </select>
  </div>

  <div v-if="qualityMode === 'cap'" class="setting-item">
    <label>{{ $t('video_download.max_height') }}</label>
    <select
      data-test="vd-maxheight"
      :value="store.settings.max_height"
      :disabled="!enabled"
      @change="onMaxHeight(($event.target as HTMLSelectElement).value)"
    >
      <option v-for="h in HEIGHTS" :key="h" :value="h">{{ h }}p</option>
    </select>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.vd-terms {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
}
</style>
