import { ref } from 'vue'

/** 工具頁當前檔名（由各 View 設定，Titlebar 讀取） */
const activeFileName = ref('')

export function useTitlebar() {
  function setFileName(name: string) {
    activeFileName.value = name
  }

  function clearFileName() {
    activeFileName.value = ''
  }

  return {
    activeFileName,
    setFileName,
    clearFileName,
  }
}
