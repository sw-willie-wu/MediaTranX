<script setup lang="ts">
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'

const props = defineProps<{
  text: string
  format: 'md' | 'txt'
  filename: string | null
}>()

const emit = defineEmits<{
  close: []
}>()

async function copyText() {
  await navigator.clipboard.writeText(props.text)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div class="ocr-modal-overlay" @click.self="emit('close')">
        <div class="ocr-modal">
          <div class="ocr-modal-header">
            <div class="ocr-modal-title">
              <i class="bi bi-file-text me-2"></i>
              <span>OCR 辨識結果</span>
              <span v-if="filename" class="ocr-modal-filename">{{ filename }}</span>
            </div>
            <div class="ocr-modal-actions">
              <button class="action-btn" title="複製全文" @click="copyText">
                <i class="bi bi-clipboard"></i>
                <span>複製</span>
              </button>
              <button class="close-btn" @click="emit('close')">
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
          </div>

          <div class="ocr-modal-body">
            <MarkdownRenderer :text="text" :format="format" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ocr-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.ocr-modal {
  display: flex;
  flex-direction: column;
  width: min(860px, 100%);
  max-height: calc(100vh - 4rem);
  background: rgba(31, 28, 44, 0.85);
  border: 1px solid var(--panel-border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
}

[data-theme="light"] .ocr-modal {
  background: #f4f4f8;
}

.ocr-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--panel-border);
  flex-shrink: 0;
  gap: 1rem;
}

.ocr-modal-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 0;
}

.ocr-modal-filename {
  font-size: 0.78rem;
  font-weight: 400;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ocr-modal-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  background: transparent;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  background: transparent;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
  &:hover { background: rgba(220,53,69,0.15); border-color: rgba(220,53,69,0.4); color: #f87171; }
}

.ocr-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 1.75rem;
  font-size: 0.9rem;
  line-height: 1.7;
  color: var(--text-primary);

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 3px; }
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
  .ocr-modal { transition: transform 0.2s ease; }
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
  .ocr-modal { transform: scale(0.97) translateY(8px); }
}
</style>
