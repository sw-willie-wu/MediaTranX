// preload.cjs
const { contextBridge, ipcRenderer, webUtils } = require('electron');

// 檔案路徑快取（用於 webUtils.getPathForFile）
const filePathCache = new Map();

function cacheFilePaths(files) {
  if (!files) return;
  for (const file of files) {
    try {
      const path = webUtils.getPathForFile(file);
      if (path) {
        const key = `${file.name}|${file.size}|${file.lastModified}`;
        filePathCache.set(key, path);
      }
    } catch (e) {
      // ignore
    }
  }
}

window.addEventListener('DOMContentLoaded', () => {
  // 攔截拖放事件，在 preload context 中提取檔案路徑
  document.addEventListener('drop', (e) => {
    cacheFilePaths(e.dataTransfer?.files);
  }, true);

  // 攔截 file input 變更
  document.addEventListener('change', (e) => {
    const target = e.target;
    if (target && target.type === 'file') {
      cacheFilePaths(target.files);
    }
  }, true);
});

contextBridge.exposeInMainWorld('electron', {
  minimize: () => ipcRenderer.send('minimize-window'),
  maximize: () => ipcRenderer.send('maximize-window'),
  close: () => ipcRenderer.send('close-window'),
  isMaximized: async () => await ipcRenderer.invoke('check-maximized'),
  onMaximizeChange: (callback) => ipcRenderer.on('window-maximized', (_event, value) => callback(value)),
  selectFolder: async () => await ipcRenderer.invoke('select-folder'),
  saveFileDialog: async (options) => await ipcRenderer.invoke('save-file-dialog', options),
  getFileSourceDir: (name, size, lastModified) => {
    const key = `${name}|${size}|${lastModified}`;
    const filePath = filePathCache.get(key);
    if (filePath) {
      const normalized = filePath.replace(/\\/g, '/');
      const lastSlash = normalized.lastIndexOf('/');
      if (lastSlash >= 0) return normalized.substring(0, lastSlash);
    }
    return null;
  },
});
