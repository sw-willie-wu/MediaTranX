<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MarkdownRenderer from '@/components/common/MarkdownRenderer.vue'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  text: string
  format?: 'md' | 'txt'
  filename?: string | null
  title?: string
}>(), {
  format: 'txt',
  filename: null,
  title: '',
})

const emit = defineEmits<{
  close: []
}>()

const displayTitle = computed(() => props.title || t('common.text_preview'))

async function copyText() {
  await navigator.clipboard.writeText(props.text)
}
</script>

<script lang="ts">
import { computed } from 'vue'
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div class="modal-overlay" @click.self="emit('close')">
        <div class="modal-panel">
          <div class="modal-header">
            <div class="modal-title">
              <i class="bi bi-file-text me-2"></i>
              <span>{{ displayTitle }}</span>
              <span v-if="filename" class="modal-filename">{{ filename }}</span>
            </div>
            <div class="modal-actions">
              <button class="action-btn" :title="t('common.copy_all')" @click="copyText">
                <i class="bi bi-clipboard"></i>
                <span>{{ t('common.copy') }}</span>
              </button>
              <button class="close-btn" @click="emit('close')">
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
          </div>

          <div class="modal-body">
            <MarkdownRenderer :text="text" :format="format" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
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

.modal-panel {
  display: flex;
  flex-direction: column;
  width: min(860px, 100%);
  max-height: calc(100vh - 4rem);
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--panel-border);
  flex-shrink: 0;
  gap: 1rem;
}

.modal-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 0;
}

.modal-filename {
  font-size: 0.78rem;
  font-weight: 400;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-actions {
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
  transition: all 0.15s ease;
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
  transition: all 0.15s ease;
  &:hover { background: var(--color-danger-bg); border-color: var(--color-danger); color: var(--color-danger); }
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 1.75rem;
  font-size: 0.9rem;
  line-height: 1.7;
  color: var(--text-primary);

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: var(--panel-bg-hover); border-radius: 3px; }
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
  .modal-panel { transition: transform 0.2s ease; }
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
  .modal-panel { transform: scale(0.97) translateY(8px); }
}
</style>
