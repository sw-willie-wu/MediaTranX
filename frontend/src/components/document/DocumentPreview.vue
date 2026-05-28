<script setup lang="ts">
defineProps<{
  file: File | null
  isUploading: boolean
}>()
</script>

<template>
  <div class="preview-display">
    <div class="document-preview">
      <i class="bi bi-file-earmark-text-fill"></i>
      <p class="filename">{{ file?.name }}</p>
      <p v-if="isUploading" class="upload-hint">上傳中...</p>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.document-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem;
  background: var(--input-bg);
  border-radius: 16px;

  i {
    font-size: 4rem;
    color: var(--color-info);
  }

  .filename {
    color: var(--text-primary);
    font-size: 1rem;
  }

  .upload-hint {
    color: var(--text-muted);
    font-size: 0.85rem;
  }
}
</style>
