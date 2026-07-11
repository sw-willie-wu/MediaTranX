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
  restart: () => ipcRenderer.send('restart-app'),
  selectFolder: async () => await ipcRenderer.invoke('select-folder'),
  pickFolderFiles: async () => await ipcRenderer.invoke('pick-folder-files'),
  saveFileDialog: async (options) => await ipcRenderer.invoke('save-file-dialog', options),
  downloadToPath: async (url, destPath, srcPath) => await ipcRenderer.invoke('download-to-path', { url, destPath, srcPath }),
  fileExists: async (filePath) => await ipcRenderer.invoke('file-exists', filePath),
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
  appVersion: (() => {
    const versionArg = process.argv.find(arg => arg.startsWith('--app-version='));
    return versionArg ? versionArg.split('=')[1] : null;
  })(),
  backendPort: (() => {
    const portArg = process.argv.find(arg => arg.startsWith('--backend-port='));
    return portArg ? portArg.split('=')[1] : null;
  })(),
  getApiConfig: async () => await ipcRenderer.invoke('get-api-config'),
  readLocalFile: async (filePath) => await ipcRenderer.invoke('read-local-file', filePath),
  writeLocalFile: async (filePath, data) => await ipcRenderer.invoke('write-local-file', filePath, data),
  showItemInFolder: (filePath) => ipcRenderer.send('show-item-in-folder', filePath),
  openPath: (filePath) => ipcRenderer.invoke('open-path', filePath),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  savePreference: (key, value) => ipcRenderer.send('save-preference', key, value),
  reinstallAiEnv: () => ipcRenderer.send('reinstall-ai-env'),
  onReinstallProgress: (cb) => ipcRenderer.on('reinstall-progress', (_, data) => cb(data)),

  // ── Software update ──────────────────────────────────────────────────────
  checkForUpdates: async () => await ipcRenderer.invoke('update:check'),
  downloadUpdate: async () => await ipcRenderer.invoke('update:download'),
  runInstaller: async () => await ipcRenderer.invoke('update:run-installer'),
  getUpdatePrefs: async () => await ipcRenderer.invoke('update:get-prefs'),
  setUpdateFrequency: (freq) => ipcRenderer.send('update:set-frequency', freq),
  onUpdateDownloadProgress: (cb) => ipcRenderer.on('update:download-progress', (_, p) => cb(p)),
  onUpdateAvailable: (cb) => ipcRenderer.on('update:available', (_, r) => cb(r)),
});
