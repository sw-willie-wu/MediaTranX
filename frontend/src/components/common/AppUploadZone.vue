<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

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

function handleDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  isDragOver.value = false
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
