<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  icon?: string
  label?: string
  hint?: string
  accept?: string
}>(), {
  icon: 'bi-cloud-arrow-up-fill',
  label: '拖曳檔案到這裡',
  hint: '或點擊選擇檔案',
  accept: '*',
})

const emit = defineEmits<{
  (e: 'file', file: File, sourceDir: string | undefined): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleClick() {
  fileInputRef.value?.click()
}

function extractSourceDir(file: File): string | undefined {
  return window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
}

function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    const file = input.files[0]
    emit('file', file, extractSourceDir(file))
    input.value = ''
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    const file = files[0]
    emit('file', file, extractSourceDir(file))
  }
}
</script>

<template>
  <div
    class="upload-zone"
    @dragover.prevent
    @drop="handleDrop"
    @click="handleClick"
  >
    <input ref="fileInputRef" type="file" :accept="accept" hidden @change="handleFileInput" />
    <i :class="['bi', icon]"></i>
    <p>{{ label }}</p>
    <p class="hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border: 2px dashed var(--drop-zone-border);
  border-radius: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-zone:hover {
  border-color: var(--drop-zone-border-hover);
  background: var(--input-bg);
}

.upload-zone i {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.upload-zone p {
  margin: 0;
  font-size: 1rem;
}

.upload-zone .hint {
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
</style>
