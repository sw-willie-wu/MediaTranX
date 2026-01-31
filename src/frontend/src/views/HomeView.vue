<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useFilesStore } from '@/stores/files'

const router = useRouter()
const filesStore = useFilesStore()
const isDragging = ref(false)

// 工具類別
const tools = [
  { id: 'video', name: '影片', icon: 'bi-film', color: '#ef4444', path: '/video' },
  { id: 'audio', name: '音訊', icon: 'bi-music-note-beamed', color: '#f59e0b', path: '/audio' },
  { id: 'image', name: '圖片', icon: 'bi-image-fill', color: '#10b981', path: '/image' },
  { id: 'document', name: '文件', icon: 'bi-file-earmark-text-fill', color: '#6366f1', path: '/document' },
]

// 檔案類型對應
const fileTypeMap: Record<string, string> = {
  // 影片
  'video/mp4': 'video',
  'video/webm': 'video',
  'video/avi': 'video',
  'video/quicktime': 'video',
  'video/x-msvideo': 'video',
  'video/x-matroska': 'video',
  // 音訊
  'audio/mpeg': 'audio',
  'audio/mp3': 'audio',
  'audio/wav': 'audio',
  'audio/ogg': 'audio',
  'audio/flac': 'audio',
  'audio/aac': 'audio',
  'audio/x-m4a': 'audio',
  // 圖片
  'image/jpeg': 'image',
  'image/png': 'image',
  'image/gif': 'image',
  'image/webp': 'image',
  'image/bmp': 'image',
  'image/tiff': 'image',
  // 文件
  'application/pdf': 'document',
  'application/msword': 'document',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
}

// 根據副檔名判斷類型
function getTypeByExtension(filename: string): string | null {
  const ext = filename.split('.').pop()?.toLowerCase()
  const extMap: Record<string, string> = {
    // 影片
    mp4: 'video', mkv: 'video', avi: 'video', mov: 'video', webm: 'video', wmv: 'video', flv: 'video',
    // 音訊
    mp3: 'audio', wav: 'audio', flac: 'audio', aac: 'audio', ogg: 'audio', m4a: 'audio', wma: 'audio',
    // 圖片
    jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', webp: 'image', bmp: 'image', tiff: 'image', ico: 'image',
    // 文件
    pdf: 'document', doc: 'document', docx: 'document', txt: 'document',
  }
  return ext ? extMap[ext] || null : null
}

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

function handleDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false

  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  const file = files[0]
  let fileType = fileTypeMap[file.type]

  // 如果 MIME type 無法判斷，用副檔名
  if (!fileType) {
    fileType = getTypeByExtension(file.name) || 'unknown'
  }

  // 導航到對應工具頁面，透過 store 傳遞檔案
  if (fileType && fileType !== 'unknown') {
    // 透過 preload 快取取得來源目錄
    const srcDir = window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
    filesStore.pendingFile = file
    filesStore.pendingSourceDir = srcDir
    router.push(`/${fileType}`)
  } else {
    alert('無法識別此檔案類型')
  }
}
</script>

<template>
  <div class="home-page">
    <div class="home-content">
      <!-- 快速功能區 -->
      <div class="quick-tools">
        <h2 class="section-title">選擇工具</h2>
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
            <p class="drop-text">將檔案拖曳至此</p>
            <p class="drop-hint">自動識別檔案類型並進入對應工具</p>
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

.section-title {
  color: var(--text-primary);
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 1rem;
  text-align: center;
}

// 快速工具區
.quick-tools {
  padding: 1.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 16px;
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
  transition: all 0.2s ease;

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
  border-radius: 14px;
  transition: all 0.2s ease;

  i {
    font-size: 1.75rem;
    color: var(--tool-color);
    transition: color 0.2s ease;
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
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--drop-zone-border-hover);
    background: var(--panel-bg);
  }

  &.dragging {
    border-color: var(--color-accent);
    background: rgba(96, 165, 250, 0.1);

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
  transition: all 0.2s ease;
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
