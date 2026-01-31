<template>
  <div class="panel">
    <!-- 有檔案時顯示預覽 -->
    <div v-if="previewUrl" class="preview d-flex justify-content-center align-items-center">
      <img v-if="isImage" :src="previewUrl" class="img-fluid rounded" />
      <audio v-else-if="isAudio" :src="previewUrl" controls class="w-100 mt-2" />
      <video v-else-if="isVideo" :src="previewUrl" controls class="w-100 rounded" />
      <div v-else class="file-icon">
        <i class="bi bi-file-earmark display-1"></i>
        <p class="mt-2">{{ currentFile?.originalName }}</p>
      </div>
    </div>

    <!-- 無檔案時顯示空狀態 -->
    <div v-else class="empty-state d-flex justify-content-center align-items-center">
      <i class="bi bi-image display-1 text-muted"></i>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useFilesStore } from '@/stores/files'

const filesStore = useFilesStore()

const currentFile = computed(() => filesStore.currentFile)
const previewUrl = computed(() => currentFile.value?.previewUrl || null)
const mimeType = computed(() => currentFile.value?.mimeType || '')

const isImage = computed(() => mimeType.value.startsWith('image/'))
const isAudio = computed(() => mimeType.value.startsWith('audio/'))
const isVideo = computed(() => mimeType.value.startsWith('video/'))
</script>

<style scoped>
.panel {
  width: 100%;
  height: 100%;
}

.preview {
  height: 100%;
}

.preview img {
  max-height: 65vh;
  max-width: 100%;
  object-fit: contain;
}

.preview video {
  max-height: 65vh;
  max-width: 100%;
}

.preview audio {
  max-width: 400px;
}

.file-icon {
  text-align: center;
  color: rgba(255, 255, 255, 0.6);
}

.empty-state {
  height: 100%;
  color: rgba(255, 255, 255, 0.3);
}
</style>
