<script setup lang="ts">
/**
 * document.split 參數元件（統一參數元件 spec §5；批 4 Task 4.5 Part A——最小標準遷移）。
 * UI 沿舊 components/document/panels/DocumentSplitPanel.vue：單一 pages 文字欄。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 *
 * 單一文字欄，one-shot lastEmitted pattern 沿 CutParams.vue/DownloadParams.vue 慣例
 * （commit 於 @change，非每次 keystroke，使用者輸入中不被外部回流打斷）。
 */
import { ref, watch } from 'vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流）。 */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

const pagesText = ref(String(props.params.pages ?? ''))
let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    pagesText.value = String(p.pages ?? '')
  },
  { deep: true },
)

function commitPages() {
  const next = { ...props.params, pages: pagesText.value }
  lastEmitted = next
  emit('update:params', next)
}
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-layout-split me-2"></i>{{ $t('document.split.title') }}</h6>
    <p class="form-hint">{{ $t('document.split.description') }}</p>

    <div class="form-group">
      <label>{{ $t('document.split.page_range') }}</label>
      <input
        v-model="pagesText"
        class="form-input"
        type="text"
        :placeholder="$t('document.split.range_example')"
        @change="commitPages"
      />
      <small class="form-hint">{{ $t('document.split.range_hint', { example: '1-3,5,8-10' }) }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
