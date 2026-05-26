<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  disabled: boolean
  isRunning: boolean
}>()

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'cancel'): void
}>()

const text = ref('')
const MAX_CHARS = 2000

function submit() {
  const trimmed = text.value.trim()
  if (!trimmed || props.disabled) return
  emit('send', trimmed)
  text.value = ''
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
    <div class="textarea-wrap">
      <textarea
        v-model="text"
        class="chat-textarea"
        :placeholder="$t('agent.bubble.placeholder')"
        :disabled="isRunning"
        :maxlength="MAX_CHARS"
        rows="2"
        @keydown="handleKeydown"
      ></textarea>
      <span class="char-counter" :class="{ warn: text.length > MAX_CHARS * 0.85 }">
        {{ text.length }}/{{ MAX_CHARS }}
      </span>
    </div>
    <div class="chat-input-controls">
      <button
        v-if="isRunning"
        class="btn-cancel-run"
        @click="emit('cancel')"
      >
        <i class="bi bi-stop-circle"></i>
        {{ $t('common.cancel') }}
      </button>
      <button
        v-else
        class="btn-send"
        :disabled="!text.trim()"
        @click="submit"
      >
        <i class="bi bi-send"></i>
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chat-input-area {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border-top: 1px solid var(--panel-border);
  flex-shrink: 0;
}

.textarea-wrap {
  position: relative;
}

.chat-textarea {
  width: 100%;
  min-height: 52px;
  max-height: 100px;
  padding: 0.5rem 2.5rem 0.5rem 0.6rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.84rem;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;

  &::placeholder { color: var(--text-muted); }
  &:focus { border-color: var(--input-border-focus); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.char-counter {
  position: absolute;
  bottom: 4px;
  right: 6px;
  font-size: 0.65rem;
  color: var(--text-muted);
  pointer-events: none;

  &.warn { color: var(--color-warning); }
}

.chat-input-controls {
  display: flex;
  justify-content: flex-end;
}

.btn-send {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: var(--color-primary);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  transition: background 0.15s, transform 0.1s;

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
    transform: scale(1.05);
  }
  &:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
}

.btn-cancel-run {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.75rem;
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  color: var(--color-danger);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: rgba(239, 68, 68, 0.15); }
}
</style>
