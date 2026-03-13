<script setup lang="ts">
import { ref, computed } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AudioPreview from '@/components/audio/AudioPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import AudioTranscodePanel  from '@/components/audio/panels/AudioTranscodePanel.vue'
import AudioCutPanel        from '@/components/audio/panels/AudioCutPanel.vue'
import AudioVolumePanel     from '@/components/audio/panels/AudioVolumePanel.vue'
import AudioTranscribePanel from '@/components/audio/panels/AudioTranscribePanel.vue'
import { useAudioWorkspace } from '@/composables/useAudioWorkspace'

const {
  hasFile, fileId, isUploading, currentFileName, hasResult, audioInfo,
  handleFile, handleRemoveFile, handlePanelSubmit, handleDownload,
} = useAudioWorkspace()

// Panel refs
const transcodePanelRef  = ref<InstanceType<typeof AudioTranscodePanel>  | null>(null)
const cutPanelRef        = ref<InstanceType<typeof AudioCutPanel>        | null>(null)
const volumePanelRef     = ref<InstanceType<typeof AudioVolumePanel>     | null>(null)
const transcribePanelRef = ref<InstanceType<typeof AudioTranscribePanel> | null>(null)

const subFunctions = [
  { id: 'transcode',  name: '轉檔',     icon: 'bi-arrow-repeat' },
  { id: 'cut',        name: '剪輯',     icon: 'bi-scissors' },
  { id: 'volume',     name: '音量調整', icon: 'bi-volume-up-fill' },
  { id: 'transcribe', name: '逐字稿',   icon: 'bi-mic-fill' },
]

const currentFunction = ref('transcode')

const executeDisabled = computed(() => {
  if (currentFunction.value === 'transcode')  return transcodePanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'cut')        return cutPanelRef.value?.isDisabled        ?? !hasFile.value
  if (currentFunction.value === 'volume')     return volumePanelRef.value?.isDisabled     ?? !hasFile.value
  if (currentFunction.value === 'transcribe') return transcribePanelRef.value?.isDisabled ?? !hasFile.value
  return !hasFile.value
})

const executeLoading = computed(() => {
  if (currentFunction.value === 'transcode')  return transcodePanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'cut')        return cutPanelRef.value?.isLoading        ?? false
  if (currentFunction.value === 'volume')     return volumePanelRef.value?.isLoading     ?? false
  if (currentFunction.value === 'transcribe') return transcribePanelRef.value?.isLoading ?? false
  return false
})

function handleExecute() {
  switch (currentFunction.value) {
    case 'transcode':  transcodePanelRef.value?.execute();  break
    case 'cut':        cutPanelRef.value?.execute();        break
    case 'volume':     volumePanelRef.value?.execute();     break
    case 'transcribe': transcribePanelRef.value?.execute(); break
  }
}

function formatDuration(s: number): string {
  const h   = Math.floor(s / 3600)
  const m   = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  return `${m}:${sec.toString().padStart(2, '0')}`
}
function formatSize(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}
function formatBitrate(bps: number): string {
  if (bps < 1000) return `${bps} bps`
  if (bps < 1_000_000) return `${(bps / 1000).toFixed(0)} Kbps`
  return `${(bps / 1_000_000).toFixed(1)} Mbps`
}

const audioInfoItems = computed<InfoItem[]>(() => {
  if (audioInfo.value) {
    const a = audioInfo.value
    return [
      { icon: 'bi-clock',             label: formatDuration(a.duration) },
      { icon: 'bi-music-note-beamed', label: a.codec.toUpperCase() },
      { icon: 'bi-soundwave',         label: `${(a.sample_rate / 1000).toFixed(1)} kHz` },
      { icon: 'bi-reception-4',       label: a.channels === 1 ? 'Mono' : 'Stereo' },
      { icon: 'bi-speedometer2',      label: formatBitrate(a.bitrate) },
      { icon: 'bi-hdd',               label: formatSize(a.file_size) },
    ]
  }
  return []
})

function onDownload() {
  const fmtMap: Record<string, [string, string]> = {
    transcode:  [transcodePanelRef.value ? '' : 'mp3', '_transcoded'],
    cut:        ['', '_cut'],
    volume:     ['', '_adjusted'],
    transcribe: ['', '_transcript'],
  }
  const [fmt, suffix] = fmtMap[currentFunction.value] ?? ['', '_output']
  handleDownload(fmt || undefined, suffix)
}
</script>

<template>
  <ToolLayout
    title="音訊工具"
    accept-type="audio"
    upload-icon="bi-music-note-beamed"
    upload-label="拖曳音訊到這裡"
    upload-hint="支援 MP3、WAV、FLAC、AAC 等格式"
    upload-accept="audio/*"
    hide-preview-tabs
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="handleFile"
    @remove-file="handleRemoveFile"
    @download="onDownload"
  >
    <template #preview="{ file, previewUrl }">
      <AudioPreview
        :preview-url="previewUrl"
        :file="file"
      />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="audioInfo || isUploading"
        :items="audioInfoItems"
        :loading="isUploading && !audioInfo"
        loading-text="讀取音訊資訊..."
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <AudioTranscodePanel
          v-if="currentFunction === 'transcode'"
          ref="transcodePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioCutPanel
          v-else-if="currentFunction === 'cut'"
          ref="cutPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :duration="audioInfo?.duration"
          @submit="handlePanelSubmit"
        />

        <AudioVolumePanel
          v-else-if="currentFunction === 'volume'"
          ref="volumePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <AudioTranscribePanel
          v-else-if="currentFunction === 'transcribe'"
          ref="transcribePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }
</style>
