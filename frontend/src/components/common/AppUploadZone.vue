<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { expandDropItems, hasDirectoryItem } from '@/utils/dropEntries'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  icon?: string
  label?: string
  hint?: string
  accept?: string
  multiple?: boolean
}>(), {
  icon: 'bi-cloud-arrow-up-fill',
  accept: '*',
  multiple: false,
})

const effectiveLabel = computed(() => props.label ?? t('common.drop_files'))
const effectiveHint = computed(() => props.hint ?? t('common.drop_hint'))

const emit = defineEmits<{
  (e: 'file', file: File, sourceDir: string | undefined): void
  (e: 'files', files: File[]): void
  (e: 'folder-files', files: File[], truncated: boolean): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragOver = ref(false)

function handleClick() {
  fileInputRef.value?.click()
}

function extractSourceDir(file: File): string | undefined {
  return window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
}

function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    if (props.multiple && input.files.length > 1) {
      emit('files', Array.from(input.files))
    } else {
      const file = input.files[0]
      emit('file', file, extractSourceDir(file))
    }
    input.value = ''
  }
}

async function handleDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  isDragOver.value = false
  // Folder-aware path: expand directory items here (this handler stops
  // propagation, so ToolLayout's drop handler never sees empty-state drops).
  const items = e.dataTransfer?.items
  if (items && items.length > 0 && hasDirectoryItem(items)) {
    const { files, truncated } = await expandDropItems(items)
    emit('folder-files', files, truncated)
    return
  }
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    if (props.multiple && files.length > 1) {
      emit('files', Array.from(files))
    } else {
      const file = files[0]
      emit('file', file, extractSourceDir(file))
    }
  }
}
</script>

<template>
  <div
    class="upload-zone"
    :class="{ 'is-dragover': isDragOver }"
    @dragover.prevent="isDragOver = true"
    @dragleave="isDragOver = false"
    @drop="handleDrop"
    @click="handleClick"
  >
    <input ref="fileInputRef" type="file" :accept="accept" :multiple="multiple" hidden @change="handleFileInput" />
    <i :class="['bi', icon]"></i>
    <p>{{ effectiveLabel }}</p>
    <p class="hint">{{ effectiveHint }}</p>
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

.upload-zone:hover,
.upload-zone.is-dragover {
  border-color: var(--drop-zone-border-hover);
  background: var(--input-bg);
}

.upload-zone.is-dragover {
  transform: scale(1.01);
  box-shadow: 0 0 24px rgba(124, 111, 173, 0.15);
}

.upload-zone.is-dragover i {
  animation: upload-pulse 1s ease-in-out infinite;
}

@keyframes upload-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.12); opacity: 0.8; }
}

.upload-zone i {
  font-size: 3rem;
  margin-bottom: 1rem;
  transition: transform 0.2s ease;
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
