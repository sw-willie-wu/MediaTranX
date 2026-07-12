<script setup lang="ts">
/**
 * video.cut 參數元件（統一參數元件 spec §5）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * 核心 pattern（之後 25 個元件沿用）：顯示字串＝響應式衍生＋本地編輯不打斷——
 * watch(props.params) 時對「上次自己 emit 的值」做 value-diff：
 *   相同（自身 emit 回流）→ 不重推顯示字串（使用者輸入中不被打斷）
 *   不同（外部寫入：agent setField/setParams/seed/開 recipe）→ 重推顯示字串
 */
import { computed, ref, watch } from 'vue'
import { parseTimeToSeconds, secondsToTime } from './cut.meta'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

/** 假設 params 為淺層 primitive；含 array/object 值的元件需自行深比較或接受多餘重推（安全方向）。 */
/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

const startText = ref(secondsToTime(props.params.start_time as number | undefined))
const endText = ref(secondsToTime(props.params.end_time as number | undefined))
const streamCopy = computed(() => Boolean(props.params.stream_copy))
let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    startText.value = secondsToTime(p.start_time as number | undefined)
    endText.value = secondsToTime(p.end_time as number | undefined)
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitField(name: 'start_time' | 'end_time', text: string) {
  const parsed = parseTimeToSeconds(text)
  commit({ ...props.params, [name]: parsed })
  // commit 後把顯示字串正規化（例如使用者打 '90' → 顯示 '00:01:30'）
  if (name === 'start_time') {
    startText.value = secondsToTime(parsed)
  } else {
    endText.value = secondsToTime(parsed)
  }
}

function onStreamCopyChange(v: boolean) {
  commit({ ...props.params, stream_copy: v })
}
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>{{ $t('video.cut.title') }}</h6>
    <p class="form-hint">{{ $t('video.cut.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.cut.start_time') }}</label>
      <input
        v-model="startText"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @change="commitField('start_time', startText)"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('video.cut.end_time') }}</label>
      <input
        v-model="endText"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @change="commitField('end_time', endText)"
      />
    </div>

    <SettingsCollapsible storage-key="video_cut_advanced">
      <div class="form-group">
        <AppToggle
          :modelValue="streamCopy"
          @update:modelValue="onStreamCopyChange"
        >{{ $t('video.cut.fast_mode') }}</AppToggle>
        <small class="form-hint">{{ $t('video.cut.fast_mode_hint') }}</small>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
