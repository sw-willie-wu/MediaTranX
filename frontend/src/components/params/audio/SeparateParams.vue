<script setup lang="ts">
/**
 * audio.separate 參數元件（統一參數元件 spec §5；批 3 Task 3.3）。
 * UI 沿舊 components/audio/panels/AudioSeparatePanel.vue：6 個 stem toggle + output_format
 * + generate_midi，全頂層（舊 panel 無 advanced 區）。
 *
 * model_name 不做 UI（設計定案，見 separate.meta.ts 檔頭）——advanced 欄位僅供 pipeline
 * 節點表單/agent 靜態選項用；工具頁沿舊 panel 無 picker（唯一 variant 'htdemucs_6s'，
 * 之後若模型倉庫新增 variant 需另補 picker，非本案範圍）。
 *
 * stems 響應式衍生：params.stems undefined → 6 toggle 全顯示為 on（=後端 None=全部）；
 * 一旦任何 toggle 被使用者點擊，一律寫回**完整陣列**（即使結果仍是全選的 6 項），不再寫回
 * undefined——undefined 只是初始語意，設計定案見 task brief（一旦互動過即改用顯式陣列）。
 */
import { computed } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

function commitPatch(patch: Record<string, unknown>) {
  emit('update:params', { ...props.params, ...patch })
}

const STEM_NAMES = ['vocals', 'drums', 'bass', 'guitar', 'piano', 'other'] as const

function isStemSelected(name: string): boolean {
  const stems = props.params.stems
  if (stems === undefined) return true
  return Array.isArray(stems) && (stems as unknown[]).includes(name)
}

function toggleStem(name: string, value: boolean) {
  const next = STEM_NAMES.filter((n) => (n === name ? value : isStemSelected(n)))
  commitPatch({ stems: [...next] })
}

const outputFormats: SelectOption[] = [
  { value: 'wav', label: 'WAV' },
  { value: 'flac', label: 'FLAC' },
  { value: 'mp3', label: 'MP3' },
]
const outputFormat = computed(() => String(props.params.output_format ?? 'wav'))
const generateMidi = computed(() => props.params.generate_midi === true)
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-music-note-list me-2"></i>{{ $t('audio.separate.title') }}</h6>
    <p class="form-hint">{{ $t('audio.separate.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.separate.stems') }}</label>
      <div class="stem-toggles">
        <AppToggle
          v-for="name in STEM_NAMES"
          :key="name"
          :model-value="isStemSelected(name)"
          @update:model-value="(v) => toggleStem(name, v)"
        >
          {{ $t(`audio.separate.stem_${name}`) }}
        </AppToggle>
      </div>
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :model-value="outputFormat"
        :options="outputFormats"
        @update:model-value="(v) => commitPatch({ output_format: v })"
      />
    </div>

    <div class="form-group">
      <AppToggle :model-value="generateMidi" @update:model-value="(v) => commitPatch({ generate_midi: v })">
        {{ $t('audio.separate.generate_midi_desc') }}
      </AppToggle>
    </div>
  </div>
</template>

<style lang="scss" scoped>
@use '@/styles/tool-panels-shared';

.stem-toggles {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
