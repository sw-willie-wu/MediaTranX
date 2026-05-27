<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

const props = defineProps<{
  disabled: boolean
  isRunning: boolean
}>()

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'cancel'): void
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const MAX_CHARS = 2000

/**
 * Auto-grow the textarea between 1 line (initial) and MAX_HEIGHT_PX
 * (caps growth so very long input doesn't push the rest of the panel
 * out of view). Beyond the cap the textarea becomes scrollable.
 */
const MAX_HEIGHT_PX = 140
function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'  // collapse so scrollHeight reflects new content size
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`
}

// Recompute on every text change (covers paste, programmatic clear).
watch(text, () => { nextTick(autoResize) })

function submit() {
  const trimmed = text.value.trim()
  if (!trimmed || props.disabled) return
  emit('send', trimmed)
  text.value = ''
  // text watch fires nextTick autoResize which collapses back to 1 row.
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-input-area">
    <textarea
      ref="textareaRef"
      v-model="text"
      class="chat-textarea"
      :placeholder="$t('agent.bubble.placeholder')"
      :disabled="isRunning"
      :maxlength="MAX_CHARS"
      rows="1"
      @keydown="handleKeydown"
    ></textarea>
    <button
      v-if="isRunning"
      class="btn-cancel-run"
      :title="$t('common.cancel')"
      @click="emit('cancel')"
    >
      <i class="bi bi-stop-circle"></i>
    </button>
    <button
      v-else
      class="btn-send"
      :disabled="!text.trim()"
      :title="$t('agent.bubble.placeholder')"
      @click="submit"
    >
      <i class="bi bi-send"></i>
    </button>
  </div>
</template>

<style lang="scss" scoped>
.chat-input-area {
  display: flex;
  flex-direction: row;
  align-items: flex-end; /* button stays on the BOTTOM row when textarea auto-grows */
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border-top: 1px solid var(--panel-border);
  flex-shrink: 0;
}

.chat-textarea {
  flex: 1;
  min-width: 0; /* allow shrinking inside flex row */
  /* Initial single-row height. autoResize() grows it up to MAX_HEIGHT_PX
     (140px in script) on input, beyond which the textarea scrolls. */
  height: 36px;
  min-height: 36px;
  padding: 0.45rem 0.6rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.84rem;
  font-family: inherit;
  line-height: 1.3;
  resize: none;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
  overflow-y: auto; /* scroll once auto-resize caps at MAX_HEIGHT_PX */

  &::placeholder { color: var(--text-muted); }
  &:focus { border-color: var(--input-border-focus); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

/* Send / cancel: one row tall (matches the textarea's initial row
   height); align-items: flex-end on the row keeps them pinned to the
   bottom when the textarea auto-grows above. */
.btn-send,
.btn-cancel-run {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}

.btn-send {
  border: none;
  background: var(--color-primary);
  color: white;

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
    transform: scale(1.04);
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
}

.btn-cancel-run {
  border: 1px solid rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
  color: var(--color-danger);

  &:hover { background: rgba(239, 68, 68, 0.15); }
}
</style>
