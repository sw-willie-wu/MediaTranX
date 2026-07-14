<script setup lang="ts">
/**
 * video.transcode 參數元件（統一參數元件 spec §5；批 1 Task 1.2）。
 * 契約與核心 pattern 同 CutParams.vue（one-shot lastEmitted＋commit 即正規化＋shallowEqual 淺層註記）；
 * UI 沿舊 components/video/panels/VideoTranscodePanel.vue 視覺與控件。
 *
 * 兩個關閉項（Task 1.1 過渡期 finding）：
 * 1. pipeline context：output_format 選單過濾掉 AUDIO_FORMATS（音訊格式只在工具頁由
 *    buildSubmit 分流出現，pipeline 節點沒有這層分流、選了也送不到對的 endpoint）。
 * 2. resolution 不再是文字框：預設清單 + custom 兩個 number 輸入，custom 寬高 commit
 *    時組"WxH"字串寫回 params.resolution（響應式衍生：resolution 非空且不在預設清單
 *    → custom 模式；外部寫回預設清單值 → custom 模式退出）。
 *
 * 欄位可見性優先用 META.schema[].visibleWhen（單一事實來源）；preset/audio_codec 兩欄
 * meta 本身不足以排除音訊分支（buildSubmit 對音訊分支只送 audio_format/audio_bitrate,
 * preset/audio_codec 會被靜默丟棄)——故額外用 isPureVideoFormat 收斂,避免 UI 顯示了
 * 使用者以為有效、實際上送不出去的欄位（spec 決策，詳見批 1 Task 1.2 brief）。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { META as TRANSCODE_META, AUDIO_FORMATS } from './transcode.meta'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

/** 無聲動圖格式：video_codec/audio_codec/crf 皆不適用（沿 transcode.meta.ts 私有 ANIM_FORMATS 語意複寫,
 *  meta 未 export——UI 分支判斷與 meta.visibleWhen 是兩件事,見檔頭註解） */
const ANIM_FORMATS = new Set(['gif', 'apng'])

/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

function fieldVisible(name: string): boolean {
  const f = TRANSCODE_META.schema.find((x) => x.name === name)
  return f?.visibleWhen ? f.visibleWhen(props.params) : true
}

const outputFormat = computed(() => String(props.params.output_format ?? 'mp4'))
const isAudioFormat = computed(() => AUDIO_FORMATS.has(outputFormat.value))
const isAnimFormat = computed(() => ANIM_FORMATS.has(outputFormat.value))
const isPureVideoFormat = computed(() => !isAudioFormat.value && !isAnimFormat.value)

const videoCodecVisible = computed(() => fieldVisible('video_codec'))
const crfVisible = computed(() => fieldVisible('crf'))
const presetVisible = computed(() => fieldVisible('preset') && isPureVideoFormat.value)
const audioCodecVisible = computed(() => fieldVisible('audio_codec') && isPureVideoFormat.value)
const scaleAlgorithmVisible = computed(() => fieldVisible('scale_algorithm'))
const fpsVisible = computed(() => fieldVisible('fps'))
const audioBitrateVisible = computed(() => fieldVisible('audio_bitrate'))
const hasAdvancedFields = computed(
  () =>
    videoCodecVisible.value ||
    crfVisible.value ||
    presetVisible.value ||
    audioCodecVisible.value ||
    scaleAlgorithmVisible.value ||
    fpsVisible.value ||
    audioBitrateVisible.value,
)

// ── 選項清單 ──────────────────────────────────────────────────────────────
const allFormats = computed(() => [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'avi', label: 'AVI' },
  { value: 'mov', label: 'MOV' },
  { value: 'gif', label: 'GIF' },
  { value: 'apng', label: 'APNG' },
  { value: 'mp3', label: t('video.transcode.mp3') },
  { value: 'aac', label: t('video.transcode.aac') },
  { value: 'wav', label: t('video.transcode.wav') },
  { value: 'flac', label: t('video.transcode.flac') },
])
const formats = computed(() =>
  props.context === 'pipeline'
    ? allFormats.value.filter((f) => !AUDIO_FORMATS.has(f.value))
    : allFormats.value,
)

const videoCodecs = computed(() => [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265/HEVC' },
  { value: 'vp9', label: 'VP9' },
  { value: 'av1', label: 'AV1' },
  { value: 'copy', label: t('video.transcode.copy_codec') },
])

const resolutions = computed(() => [
  { value: '', label: t('video.transcode.keep_original') },
  { value: '3840x2160', label: '4K (3840x2160)' },
  { value: '2560x1440', label: '2K (2560x1440)' },
  { value: '1920x1080', label: '1080p (1920x1080)' },
  { value: '1280x720', label: '720p (1280x720)' },
  { value: '854x480', label: '480p (854x480)' },
  { value: '640x360', label: '360p (640x360)' },
  { value: 'custom', label: t('video.transcode.custom') },
])

const scaleAlgorithms = computed(() => [
  { value: 'bicubic', label: t('video.transcode.bicubic') },
  { value: 'lanczos', label: t('video.transcode.lanczos') },
  { value: 'spline', label: t('video.transcode.spline') },
  { value: 'bilinear', label: t('video.transcode.bilinear') },
  { value: 'neighbor', label: t('video.transcode.nearest') },
])

const audioCodecs = computed(() => [
  { value: 'aac', label: 'AAC' },
  { value: 'mp3', label: 'MP3' },
  { value: 'opus', label: 'Opus' },
  { value: 'flac', label: 'FLAC' },
  { value: 'copy', label: t('video.transcode.copy_codec') },
])

const presets = [
  { value: 'ultrafast', label: 'Ultrafast' },
  { value: 'fast', label: 'Fast' },
  { value: 'medium', label: 'Medium' },
  { value: 'slow', label: 'Slow' },
  { value: 'veryslow', label: 'Veryslow' },
]

const fpsOptions = [
  { value: '8', label: '8 fps' },
  { value: '10', label: '10 fps' },
  { value: '12', label: '12 fps' },
  { value: '15', label: '15 fps' },
  { value: '20', label: '20 fps' },
  { value: '24', label: '24 fps' },
]

const audioBitrates = [
  { value: '128k', label: '128 kbps' },
  { value: '192k', label: '192 kbps' },
  { value: '256k', label: '256 kbps' },
  { value: '320k', label: '320 kbps' },
]

// ── resolution 響應式衍生：custom 模式判斷＋寬高解析（one-shot pattern） ──────────
/** resolution AppSelect 的預設清單值（非此清單、非空 → custom 模式）；衍生自 resolutions
 *  選項清單（排除 'custom'）——Task 1.2 review finding：避免與 resolutions 清單各自維護、走鐘 */
const RESOLUTION_PRESETS = computed(
  () => new Set(resolutions.value.filter((r) => r.value !== 'custom').map((r) => r.value)),
)
function deriveResolutionMode(r: string): string {
  return RESOLUTION_PRESETS.value.has(r) ? r : 'custom'
}
function parseCustomSize(r: string): [number, number] | null {
  const m = /^(\d+)x(\d+)$/.exec(r)
  return m ? [Number(m[1]), Number(m[2])] : null
}

const initialResolution = String(props.params.resolution ?? '')
const resolutionMode = ref(deriveResolutionMode(initialResolution))
const initialCustomSize = parseCustomSize(initialResolution)
const customWidth = ref(initialCustomSize ? initialCustomSize[0] : 1920)
const customHeight = ref(initialCustomSize ? initialCustomSize[1] : 1080)

let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    const r = String(p.resolution ?? '')
    resolutionMode.value = deriveResolutionMode(r)
    const size = parseCustomSize(r)
    if (size) {
      customWidth.value = size[0]
      customHeight.value = size[1]
    }
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

function onFormatChange(v: string) {
  commitPatch({ output_format: v })
}

function onResolutionModeChange(mode: string) {
  resolutionMode.value = mode
  if (mode === 'custom') {
    commitPatch({ resolution: `${customWidth.value}x${customHeight.value}` })
  } else {
    commitPatch({ resolution: mode })
  }
}

function onCustomSizeChange() {
  commitPatch({ resolution: `${customWidth.value}x${customHeight.value}` })
}
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('video.transcode.title') }}</h6>
    <p class="form-hint">{{ $t('video.transcode.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect :modelValue="outputFormat" :options="formats" @update:modelValue="onFormatChange" />
    </div>

    <template v-if="!isAudioFormat">
      <div class="form-group">
        <label>{{ $t('video.transcode.resolution') }}</label>
        <AppSelect :modelValue="resolutionMode" :options="resolutions" @update:modelValue="onResolutionModeChange" />
      </div>

      <div v-if="resolutionMode === 'custom'" class="form-group size-inputs">
        <div class="size-input-group">
          <label>{{ $t('common.width') }}</label>
          <input v-model.number="customWidth" type="number" class="form-input" min="1" @change="onCustomSizeChange" />
        </div>
        <span class="size-separator">x</span>
        <div class="size-input-group">
          <label>{{ $t('common.height') }}</label>
          <input v-model.number="customHeight" type="number" class="form-input" min="1" @change="onCustomSizeChange" />
        </div>
      </div>
    </template>

    <SettingsCollapsible v-if="hasAdvancedFields" storage-key="video_transcode_advanced">
      <div v-if="videoCodecVisible" class="form-group">
        <label>{{ $t('video.transcode.video_codec') }}</label>
        <AppSelect
          :modelValue="String(params.video_codec ?? 'h264')"
          :options="videoCodecs"
          @update:modelValue="(v) => commitPatch({ video_codec: v })"
        />
      </div>

      <div v-if="crfVisible" class="form-group">
        <label>{{ $t('video.transcode.crf') }} {{ Number(params.crf ?? 23) }}</label>
        <AppRange
          :modelValue="Number(params.crf ?? 23)"
          :min="0"
          :max="51"
          @update:modelValue="(v) => commitPatch({ crf: v })"
        />
        <small class="form-hint">{{ $t('video.transcode.crf_hint') }}</small>
      </div>

      <div v-if="presetVisible" class="form-group">
        <label>{{ $t('video.transcode.preset') }}</label>
        <AppSelect
          :modelValue="String(params.preset ?? 'medium')"
          :options="presets"
          @update:modelValue="(v) => commitPatch({ preset: v })"
        />
      </div>

      <div v-if="scaleAlgorithmVisible" class="form-group">
        <label>{{ $t('video.transcode.scale_algorithm') }}</label>
        <AppSelect
          :modelValue="String(params.scale_algorithm ?? 'bicubic')"
          :options="scaleAlgorithms"
          @update:modelValue="(v) => commitPatch({ scale_algorithm: v })"
        />
      </div>

      <div v-if="audioCodecVisible" class="form-group">
        <label>{{ $t('video.transcode.audio_codec') }}</label>
        <AppSelect
          :modelValue="String(params.audio_codec ?? 'aac')"
          :options="audioCodecs"
          @update:modelValue="(v) => commitPatch({ audio_codec: v })"
        />
      </div>

      <div v-if="fpsVisible" class="form-group">
        <label>{{ $t('video.transcode.fps') }}</label>
        <AppSelect
          :modelValue="String(params.fps ?? '12')"
          :options="fpsOptions"
          @update:modelValue="(v) => commitPatch({ fps: Number(v) })"
        />
        <small class="form-hint">{{ $t('video.transcode.fps_hint') }}</small>
      </div>

      <div v-if="audioBitrateVisible" class="form-group">
        <label>{{ $t('video.transcode.bitrate') }}</label>
        <AppSelect
          :modelValue="String(params.audio_bitrate ?? '192k')"
          :options="audioBitrates"
          @update:modelValue="(v) => commitPatch({ audio_bitrate: v })"
        />
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
