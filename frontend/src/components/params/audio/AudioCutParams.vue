<script setup lang="ts">
/**
 * audio.cut 參數元件（統一參數元件 spec §5；批 3 Task 3.2）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * UI 沿舊 components/audio/panels/AudioCutPanel.vue：兩個 HH:MM:SS 文字欄＋selectionDuration
 * 顯示（衍生自本地文字 ref，不需 commit 才更新——沿舊 panel 即時反應使用者輸入的行為）。
 *
 * 與 video.cut 的關鍵差異：params.start_time/end_time **本身就是 HH:MM:SS 字串**（後端
 * AudioCutRequest 合約），不像 video.cut 是秒數 number；因此顯示字串 = params 值本身，
 * 不需要 secondsToTime 轉換來「顯示」——timeToSeconds/secondsToTime 只用在三處：
 * (1) commitField 正規化使用者輸入（例如打 "90" → 存回 "00:01:30"，確保送後端的字串
 *     永遠是合法 HH:MM:SS，舊 panel 沒有這層正規化、直接把原始文字送後端）；
 * (2) 出向比例換算（watch params → ratio，需 fileInfo.duration）；
 * (3) 入向比例換算（host notify('trimRange', ratio) → HH:MM:SS）。
 *
 * host notify('trimRange', …) 首次實際使用（批 0 建的機制，見 ToolParamHost.vue notify 段）：
 * AudioView 波形拖曳 → cutHostRef.notify('trimRange', ratioRange) → 本元件 defineExpose 的
 * notify() 接手，換算 HH:MM:SS 寫回 params（經 emit('update:params') 讓 host 收斂狀態，本元件
 * 不直接持有 truth）。
 *
 * 防迴圈：_skipOutbound 旗標＋等一個 nextTick 才解除——notify() 寫入後，host 把新 params
 * 經 props 回灌本元件時，出向 ratio-emit watcher（watch props.params）會被這個 tick 內的
 * echo 觸發；旗標壓下這次 echo，避免「入向剛執行完就立刻反射出向」的多餘/易誤解的重複事件
 * （沿舊 AudioCutPanel._skipSync 語意，但收進元件內、用 nextTick 讓壓制窗口涵蓋 host 回灌的
 * 那一次 props 變化，比舊版「同步設回 false」更貼合實際想防的範圍）。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { timeToSeconds, secondsToTime } from './cut.meta'

type TrimRatio = { start: number; end: number }

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{
  'update:params': [Record<string, unknown>]
  'update:trimRange': [TrimRatio]
}>()

/** 假設 params 為淺層 primitive；鍵集合＋逐鍵 Object.is，用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

const startText = ref(String(props.params.start_time ?? '00:00:00'))
const endText = ref(String(props.params.end_time ?? ''))
let lastEmitted: Record<string, unknown> | null = null

// ─── 顯示字串響應式衍生（one-shot lastEmitted pattern，沿 CutParams.vue） ───────────
watch(
  () => props.params,
  (p) => {
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    startText.value = String(p.start_time ?? '00:00:00')
    endText.value = String(p.end_time ?? '')
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitField(name: 'start_time' | 'end_time', text: string) {
  const normalized = secondsToTime(timeToSeconds(text))
  commit({ ...props.params, [name]: normalized })
  if (name === 'start_time') startText.value = normalized
  else endText.value = normalized
}

// ─── selectionDuration：即時衍生自本地文字（未 commit 也反映，沿舊 panel 行為） ──────
const selectionDuration = computed(() => {
  const start = timeToSeconds(startText.value)
  const end = timeToSeconds(endText.value)
  const diff = Math.max(0, end - start)
  const m = Math.floor(diff / 60)
  const s = Math.floor(diff % 60)
  return `${m}:${String(s).padStart(2, '0')}`
})

// ─── 出向：params 變 → 換算比例（需 duration）→ emit update:trimRange ────────────────
const fileDuration = computed<number | undefined>(() => {
  const d = props.fileInfo?.duration
  return typeof d === 'number' && d > 0 ? d : undefined
})

let _skipOutbound = false

watch(
  () => props.params,
  (p) => {
    if (_skipOutbound) return
    const dur = fileDuration.value
    if (dur === undefined) return
    const s = timeToSeconds(String(p.start_time ?? '00:00:00'))
    const e = timeToSeconds(String(p.end_time ?? ''))
    if (!(e > s)) return
    const startRatio = Math.max(0, Math.min(1, s / dur))
    const endRatio = Math.max(0, Math.min(1, e / dur))
    emit('update:trimRange', { start: startRatio, end: endRatio })
  },
  { deep: true, immediate: true },
)

// ─── 入向：host notify('trimRange', ratio) → HH:MM:SS 寫回 params ──────────────────
async function notify(channel: string, payload: unknown): Promise<void> {
  if (channel !== 'trimRange') return
  const range = payload as TrimRatio | null
  const dur = fileDuration.value
  if (!range || dur === undefined) return
  _skipOutbound = true
  const newStart = secondsToTime(range.start * dur)
  const newEnd = secondsToTime(range.end * dur)
  startText.value = newStart
  endText.value = newEnd
  commit({ ...props.params, start_time: newStart, end_time: newEnd })
  await nextTick()
  _skipOutbound = false
}

defineExpose({ notify })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>{{ $t('audio.cut.title') }}</h6>
    <p class="form-hint">{{ $t('audio.cut.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.cut.start_time') }}</label>
      <input
        v-model="startText"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @change="commitField('start_time', startText)"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.cut.end_time') }}</label>
      <input
        v-model="endText"
        type="text"
        class="form-input"
        placeholder="00:00:00"
        @change="commitField('end_time', endText)"
      />
      <small class="form-hint">
        {{ $t('audio.cut.selection_duration') }} {{ selectionDuration }}
      </small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
