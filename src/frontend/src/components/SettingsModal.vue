<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import AppSelect from '@/components/common/AppSelect.vue'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { themeMode, setTheme } = useTheme()

// 設定選項
const settings = ref({
  theme: 'system' as ThemeMode,
  language: 'zh-TW',
  outputDir: '',
  tempDir: '',
  autoCleanTemp: true,
  hardwareAccel: true,
})

const themes = [
  { value: 'system', label: '跟隨系統' },
  { value: 'dark', label: '深色' },
  { value: 'light', label: '淺色' },
]

const languages = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en', label: 'English' },
]

// 載入設定
onMounted(() => {
  const saved = localStorage.getItem('app-settings')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      settings.value = { ...settings.value, ...parsed }
    } catch (e) {
      // ignore
    }
  }
  // 同步主題設定
  settings.value.theme = themeMode.value
})

// 即時套用主題
watch(() => settings.value.theme, (newTheme) => {
  setTheme(newTheme)
})

async function selectOutputDir() {
  if (window.electron?.selectFolder) {
    const result = await window.electron.selectFolder()
    if (result) {
      settings.value.outputDir = result
    }
  }
}

async function selectTempDir() {
  if (window.electron?.selectFolder) {
    const result = await window.electron.selectFolder()
    if (result) {
      settings.value.tempDir = result
    }
  }
}

function saveSettings() {
  localStorage.setItem('app-settings', JSON.stringify(settings.value))
  emit('close')
}

function handleBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-backdrop" @click="handleBackdropClick">
        <div class="modal-container">
          <!-- Header -->
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-gear-fill me-2"></i>設定
            </h5>
            <button class="close-btn" @click="emit('close')">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>

          <!-- Body -->
          <div class="modal-body">
            <!-- 外觀 -->
            <div class="settings-section">
              <h6 class="section-title">外觀</h6>

              <div class="setting-item">
                <label>主題</label>
                <AppSelect v-model="settings.theme" :options="themes" />
              </div>

              <div class="setting-item">
                <label>語言</label>
                <AppSelect v-model="settings.language" :options="languages" />
              </div>
            </div>

            <!-- 路徑 -->
            <div class="settings-section">
              <h6 class="section-title">檔案路徑</h6>

              <div class="setting-item">
                <label>預設輸出資料夾</label>
                <div class="path-input">
                  <input
                    type="text"
                    v-model="settings.outputDir"
                    class="form-control"
                    placeholder="使用原檔案所在資料夾"
                    readonly
                  />
                  <button class="browse-btn" @click="selectOutputDir">
                    <i class="bi bi-folder2-open"></i>
                  </button>
                </div>
              </div>

              <div class="setting-item">
                <label>暫存資料夾</label>
                <div class="path-input">
                  <input
                    type="text"
                    v-model="settings.tempDir"
                    class="form-control"
                    placeholder="使用系統預設"
                    readonly
                  />
                  <button class="browse-btn" @click="selectTempDir">
                    <i class="bi bi-folder2-open"></i>
                  </button>
                </div>
              </div>

              <div class="setting-item checkbox-item">
                <label class="checkbox-label">
                  <input type="checkbox" v-model="settings.autoCleanTemp" />
                  <span>關閉時自動清理暫存檔</span>
                </label>
              </div>
            </div>

            <!-- 效能 -->
            <div class="settings-section">
              <h6 class="section-title">效能</h6>

              <div class="setting-item checkbox-item">
                <label class="checkbox-label">
                  <input type="checkbox" v-model="settings.hardwareAccel" />
                  <span>啟用硬體加速（GPU）</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="modal-footer">
            <button class="btn-cancel" @click="emit('close')">取消</button>
            <button class="btn-save" @click="saveSettings">儲存設定</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-container {
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  background: rgba(30, 30, 30, 0.85);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);

  [data-theme="light"] & {
    background: rgba(240, 240, 240, 0.88);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--panel-border);
}

.modal-title {
  color: var(--text-primary);
  font-size: 1.1rem;
  font-weight: 500;
  margin: 0;
  display: flex;
  align-items: center;
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg);
    color: var(--text-primary);
  }
}

.modal-body {
  flex: 1;
  padding: 1.25rem;
  overflow-y: auto;
}

.settings-section {
  margin-bottom: 1.5rem;

  &:last-child {
    margin-bottom: 0;
  }
}

.section-title {
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.75rem;
}

.setting-item {
  margin-bottom: 1rem;

  &:last-child {
    margin-bottom: 0;
  }

  > label {
    display: block;
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }
}

.form-control {
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 8px;
  color: #e0e0e0;
  font-size: 0.9rem;

  &::placeholder {
    color: rgba(255, 255, 255, 0.4);
  }

  [data-theme="light"] & {
    background: rgba(0, 0, 0, 0.05);
    border-color: rgba(0, 0, 0, 0.12);
    color: #1a1a2e;

    &::placeholder {
      color: rgba(0, 0, 0, 0.4);
    }
  }

  &:focus {
    outline: none;
    border-color: var(--input-border-focus);
    background: var(--input-bg-focus);
  }
}

.path-input {
  display: flex;
  gap: 0.5rem;

  .form-control {
    flex: 1;
  }
}

.browse-btn {
  padding: 0.5rem 0.75rem;
  background: var(--panel-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }
}

.checkbox-item {
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
    cursor: pointer;

    input[type="checkbox"] {
      width: 18px;
      height: 18px;
      accent-color: var(--color-accent);
    }
  }
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--panel-border);
}

.btn-cancel,
.btn-save {
  padding: 0.5rem 1.25rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--panel-border-hover);
  color: var(--text-secondary);

  &:hover {
    background: var(--panel-bg);
    color: var(--text-primary);
  }
}

.btn-save {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  border: none;
  color: white;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }
}

// 動畫
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;

  .modal-container {
    transition: transform 0.2s ease, opacity 0.2s ease;
  }
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;

  .modal-container {
    transform: scale(0.95);
    opacity: 0;
  }
}
</style>
