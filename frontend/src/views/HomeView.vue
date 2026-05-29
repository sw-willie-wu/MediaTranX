<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useFilesStore } from '@/stores/files'
import { detectMediaType, getToolPath } from '@/utils/mediaType'
import { usePasteUpload } from '@/composables/usePasteUpload'

const router = useRouter()
const filesStore = useFilesStore()
const { t } = useI18n()
const isDragging = ref(false)

// 工具類別
const toolsDef = [
  { id: 'image', nameKey: 'home.image', icon: 'bi-image-fill', color: '#10b981', path: '/image' },
  { id: 'audio', nameKey: 'home.audio', icon: 'bi-music-note-beamed', color: '#f59e0b', path: '/audio' },
  { id: 'video', nameKey: 'home.video', icon: 'bi-film', color: '#ef4444', path: '/video' },
  { id: 'document', nameKey: 'home.document', icon: 'bi-file-earmark-text-fill', color: '#6366f1', path: '/document' },
]

const tools = computed(() => toolsDef.map(tool => ({ ...tool, name: t(tool.nameKey) })))

function goToTool(path: string) {
  router.push(path)
}

function handleDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function handleDragLeave() {
  isDragging.value = false
}

function routeFile(file: File, srcDir?: string) {
  const fileType = detectMediaType(file)
  if (fileType) {
    filesStore.pendingFile = file
    filesStore.pendingSourceDir = srcDir
    router.push(getToolPath(fileType))
  } else {
    alert(t('home.unknown_file_type'))
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false

  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  const file = files[0]
  const srcDir = window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
  routeFile(file, srcDir)
}

// 首頁貼上:比照拖曳,取第一個檔偵測型別並導頁。
usePasteUpload((files) => {
  if (files.length > 0) routeFile(files[0])
})
</script>

<template>
  <div class="home-page">
    <div class="home-content">
      <!-- 快速功能區 -->
      <div class="quick-tools">
        <h2 class="section-title">{{ $t('home.select_tool') }}</h2>
        <div class="tools-grid">
          <button
            v-for="tool in tools"
            :key="tool.id"
            class="tool-card"
            @click="goToTool(tool.path)"
            :style="{ '--tool-color': tool.color }"
          >
            <div class="tool-icon">
              <i :class="['bi', tool.icon]"></i>
            </div>
            <span class="tool-name">{{ tool.name }}</span>
          </button>
        </div>
      </div>

      <!-- 拖曳區域 -->
      <div class="drop-section">
        <div
          class="drop-zone"
          :class="{ dragging: isDragging }"
          @dragover="handleDragOver"
          @dragleave="handleDragLeave"
          @drop="handleDrop"
        >
          <div class="drop-content">
            <i class="bi bi-cloud-arrow-up-fill drop-icon"></i>
            <p class="drop-text">{{ $t('home.drop_text') }}</p>
            <p class="drop-hint">{{ $t('home.drop_hint') }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.home-page {
  min-height: calc(100vh - 40px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.home-content {
  width: 100%;
  max-width: 700px;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-title {
  color: var(--text-primary);
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 1rem;
  text-align: center;
  animation: fadeInUp 0.35s ease both;
}

// 快速工具區
.quick-tools {
  padding: 1.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 12px;
  border: 1px solid var(--panel-border);
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.tool-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem 1rem;
  background: var(--input-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  animation: fadeInUp 0.35s ease both;
  &:nth-child(1) { animation-delay: 0.06s; }
  &:nth-child(2) { animation-delay: 0.12s; }
  &:nth-child(3) { animation-delay: 0.18s; }
  &:nth-child(4) { animation-delay: 0.24s; }

  &:hover {
    background: var(--panel-bg-hover);
    border-color: var(--tool-color);
    transform: translateY(-2px);

    .tool-icon {
      background: var(--tool-color);
      color: white;

      i {
        color: white;
      }
    }
  }

  &:active {
    transform: translateY(0);
  }
}

.tool-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--panel-bg);
  border-radius: 12px;
  transition: all 0.15s ease;

  i {
    font-size: 1.75rem;
    color: var(--tool-color);
    transition: color 0.15s ease;
  }
}

.tool-name {
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-weight: 500;
}

// 拖曳區域
.drop-section {
  flex: 1;
}

.drop-zone {
  min-height: 200px;
  padding: 3rem 2rem;
  background: var(--input-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 2px dashed var(--drop-zone-border);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  animation: fadeInUp 0.35s ease 0.3s both;

  &:hover {
    border-color: var(--drop-zone-border-hover);
    background: var(--panel-bg);
  }

  &.dragging {
    border-color: var(--color-accent);
    background: var(--drag-over-bg);

    .drop-icon {
      color: var(--color-accent);
      transform: scale(1.1);
    }
  }
}

.drop-content {
  text-align: center;
}

.drop-icon {
  font-size: 3.5rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
  transition: all 0.15s ease;
}

.drop-text {
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.drop-hint {
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
