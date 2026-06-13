// electron/main.js
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const { join, dirname } = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const os = require('os');
const net = require('net');
const { detectGPU, updatePyprojectSources, runUvSync, downloadFFmpeg, downloadYtDlp, downloadLlamaServer, downloadLlamaCudart } = require('./setup.js');
const { resolve } = require('path');

// 載入 .env 檔（簡易 parser，不依賴 dotenv）
function loadEnvFile(filePath, baseDir) {
  if (!fs.existsSync(filePath)) return {};
  const env = {};
  const lines = fs.readFileSync(filePath, 'utf-8').split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx < 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let val = trimmed.slice(eqIdx + 1).trim();
    // 移除引號
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    // 路徑類 key：相對路徑 → 絕對路徑
    const isPathKey = /PATH|DATA|VENV|BIN|MODELS|TEMP|DIR/i.test(key);
    if (isPathKey && val && !resolve(val).startsWith(val)) {
      val = resolve(baseDir, val);
    }
    env[key] = val;
  }
  return env;
}

// 子進程
let pythonProcess = null;
let viteProcess = null;

// 後端 API port (動態偵測)
let BACKEND_PORT = 8001;

const FRONTEND_DEV_PORT = 8000;

// 自動尋找可用 Port
function findFreePort(startPort) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(startPort, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => {
        // 額外檢查：確認沒有其他服務在此 port 回應（防止 WSL2/Docker 偵測不到）
        const req = require('http').get(`http://127.0.0.1:${port}`, () => {
          req.destroy();
          resolve(findFreePort(port + 1)); // 有回應 → 被佔用
        });
        req.on('error', () => resolve(port)); // 連不上 → 真的空閒
        req.setTimeout(300, () => { req.destroy(); resolve(port); });
      });
    });
    server.on('error', () => {
      resolve(findFreePort(startPort + 1));
    });
  });
}

// 取得應用程式資料目錄
function getAppDataPath() {
  if (!app.isPackaged) {
    // 開發階段：將資料存放在 private repo 根目錄下的 data 檔案夾
    const devPath = join(__dirname, '..', 'data');
    if (!fs.existsSync(devPath)) {
      fs.mkdirSync(devPath, { recursive: true });
    }
    return devPath;
  }

  const appData = process.env.APPDATA || (process.platform === 'darwin' ? join(os.homedir(), 'Library', 'Application Support') : join(os.homedir(), '.config'));
  const path = join(appData, 'MediaTranX');
  if (!fs.existsSync(path)) {
    fs.mkdirSync(path, { recursive: true });
  }
  return path;
}

// 將 Electron 內建的資料路徑（如 Cache, LocalStorage）統一導向 MediaTranX 資料夾
// 避免 Electron 依 package.json name 在 Roaming 建立 'mediatranx-electron' 預設目錄
if (app.isPackaged) {
  app.setPath('userData', getAppDataPath());
} else {
  const devDataPath = getAppDataPath();
  app.setPath('userData', join(devDataPath, 'electron_data'));
}

function startViteDevServer() {
  console.log('Starting Vite dev server on port', FRONTEND_DEV_PORT);
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  viteProcess = spawn(npmCmd, ['run', 'dev'], {
    cwd: join(__dirname, '..', 'frontend'),
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: true,
    env: { ...process.env, FORCE_COLOR: '1', VITE_PORT: String(FRONTEND_DEV_PORT), VITE_BACKEND_PORT: String(BACKEND_PORT) }
  });

  viteProcess.stdout.on('data', (data) => console.log(`[Vite] ${data}`));
  viteProcess.stderr.on('data', (data) => console.error(`[Vite] ${data}`));
}

function stopViteDevServer() {
  if (viteProcess) {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', viteProcess.pid, '/f', '/t']);
    } else {
      viteProcess.kill();
    }
    viteProcess = null;
  }
}

function waitForServer(port, maxAttempts = 120) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      http.get(`http://localhost:${port}/`, (res) => {
        res.destroy();
        resolve();
      }).on('error', () => {
        if (attempts >= maxAttempts) reject(new Error(`Server on port ${port} not ready`));
        else setTimeout(check, 1000);
      });
    };
    check();
  });
}

function startPythonBackend() {
  const isDev = !app.isPackaged;

  if (isDev) {
    const projectRoot = join(__dirname, '..', 'backend');
    const devLog = join(getAppDataPath(), 'dev_backend.log');
    const logStream = fs.createWriteStream(devLog, { flags: 'a' });
    logStream.write(`\n--- Dev Backend Start: ${new Date().toISOString()} ---\n`);

    console.log(`Starting Python backend (dev) on port ${BACKEND_PORT} via uv run...`);
    console.log(`Logs will be written to: ${devLog}`);

    pythonProcess = spawn('uv', [
      'run', '--project', projectRoot,
      'python', '-u', '-m', 'app.main',
      '--host', '127.0.0.1',
      '--port', String(BACKEND_PORT),
      '--mode', 'dev'
    ], {
      cwd: projectRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        ...loadEnvFile(join(__dirname, '.env'), __dirname),
        MEDIATRANX_APP_VERSION: app.getVersion(),
      }
    });

    pythonProcess.stdout.pipe(logStream);
    pythonProcess.stderr.pipe(logStream);
  } else {
    // 生產模式：使用隨附的 core_service/core.exe
    const backendExe = join(process.resourcesPath, 'core_service', 'core.exe');

    if (!fs.existsSync(backendExe)) {
      const errorMsg = `找不到核心後端組件：\n${backendExe}`;
      dialog.showErrorBox('啟動失敗', errorMsg);
      app.quit();
      return;
    }

    const appDataPath = getAppDataPath();
    const logsPath = join(appDataPath, 'logs');
    if (!fs.existsSync(logsPath)) fs.mkdirSync(logsPath, { recursive: true });
    const appLog = join(logsPath, 'app.log');
    const errorLog = join(logsPath, 'core_error.log');
    const logStream = fs.createWriteStream(appLog, { flags: 'a' });
    logStream.write(`\n--- App Started: ${new Date().toISOString()} (Port: ${BACKEND_PORT}) ---\n`);
    logStream.write(`Backend path: ${backendExe}\n`);

    // Read user-saved .env overrides (e.g. custom models/temp paths)
    const userEnv = loadEnvFile(join(appDataPath, '.env'), appDataPath);

    pythonProcess = spawn(backendExe, ['--port', String(BACKEND_PORT)], {
      cwd: dirname(backendExe),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        MEDIATRANX_ERROR_LOG: errorLog,
        MEDIATRANX_IS_FROZEN: 'true',
        // bin/.venv/logs computed from ROOT in backend PathSettings
        MEDIATRANX_PATH__ROOT: appDataPath,
        MEDIATRANX_PATH__MODELS: userEnv.MEDIATRANX_PATH__MODELS || join(appDataPath, 'models'),
        MEDIATRANX_PATH__TEMP: userEnv.MEDIATRANX_PATH__TEMP || join(appDataPath, 'temp'),
        MEDIATRANX_DB__DSN: `sqlite:///${join(appDataPath, 'mediatranx.db').replace(/\\/g, '/')}`,
        MEDIATRANX_SERVER__MODE: 'production',
        MEDIATRANX_APP_VERSION: app.getVersion(),
      },
      windowsHide: true
    });

    // Electron 統一 pipe Python stdout/stderr → app.log，Python 同時直寫 WARNING+ 到 core_error.log
    pythonProcess.stdout.pipe(logStream);
    pythonProcess.stderr.pipe(logStream);

    pythonProcess.on('error', (err) => {
      logStream.write(`Spawn Error: ${err.message}\n`);
    });
  }

  pythonProcess.stdout.on('data', (data) => console.log(`[Python] ${data}`));
  pythonProcess.stderr.on('data', (data) => console.error(`[Python] ${data}`));
}

function stopPythonBackend() {
  if (pythonProcess) {
    if (process.platform === 'win32') {
      try { execSync(`taskkill /f /t /pid ${pythonProcess.pid}`, { stdio: 'ignore' }); } catch (e) { }
    } else {
      pythonProcess.kill();
    }
    pythonProcess = null;
  }
}

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    frame: false,
    show: true,
    backgroundColor: '#2f2b47',
    icon: join(__dirname, 'icon.ico'),
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      devTools: !app.isPackaged,
      additionalArguments: [`--backend-port=${BACKEND_PORT}`, `--app-version=${app.getVersion()}`]
    }
  });

  // 禁用頁面導航（上下頁、滑鼠側鍵）
  mainWindow.webContents.on('will-navigate', (e) => e.preventDefault());

  mainWindow.on('maximize', () => mainWindow.webContents.send('window-maximized', true));
  mainWindow.on('unmaximize', () => mainWindow.webContents.send('window-maximized', false));
  if (!app.isPackaged) mainWindow.webContents.openDevTools();

  // 捕捉前端 console，寫入 log 檔
  // prod → logs/app.log，dev → data/dev_frontend.log
  {
    const levels = ['VERBOSE', 'INFO', 'WARNING', 'ERROR'];
    let uiLogPath;
    if (app.isPackaged) {
      const logsPath = join(getAppDataPath(), 'logs');
      if (!fs.existsSync(logsPath)) fs.mkdirSync(logsPath, { recursive: true });
      uiLogPath = join(logsPath, 'app.log');
    } else {
      uiLogPath = join(getAppDataPath(), 'dev_frontend.log');
    }
    const uiLogStream = fs.createWriteStream(uiLogPath, { flags: 'a' });
    uiLogStream.write(`\n--- UI Log Start: ${new Date().toISOString()} ---\n`);
    mainWindow.webContents.on('console-message', (_, level, message) => {
      uiLogStream.write(`[${new Date().toISOString()}] [${levels[level] ?? level}] [UI] ${message}\n`);
    });
  }

  ipcMain.on('minimize-window', () => mainWindow?.minimize());
  ipcMain.on('maximize-window', () => {
    if (mainWindow?.isMaximized()) mainWindow.restore();
    else mainWindow?.maximize();
  });
  ipcMain.handle('check-maximized', () => mainWindow?.isMaximized());
  ipcMain.on('close-window', () => mainWindow?.close());
  ipcMain.on('restart-app', () => {
    stopViteDevServer();
    stopPythonBackend();
    app.relaunch();
    app.exit(0);
  });

  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'createDirectory'],
      title: '選擇輸出資料夾'
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('get-api-config', () => {
    return { port: BACKEND_PORT };
  });

  ipcMain.handle('save-file-dialog', async (_, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result.canceled ? null : result.filePath;
  });

  ipcMain.handle('read-local-file', async (_, filePath) => {
    return fs.readFileSync(filePath);
  });

  ipcMain.handle('write-local-file', async (_, filePath, data) => {
    const dir = dirname(filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, Buffer.from(data));
  });

  ipcMain.handle('download-to-path', async (_, { url, destPath, srcPath }) => {
    if (srcPath && fs.existsSync(srcPath)) {
      // Local file: direct copy (no HTTP)
      fs.copyFileSync(srcPath, destPath);
    } else {
      // Fallback: HTTP stream download
      const { net } = require('electron');
      const response = await net.fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const fileStream = fs.createWriteStream(destPath);
      const reader = response.body.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          fileStream.write(Buffer.from(value));
        }
      } finally {
        fileStream.end();
        await new Promise(resolve => fileStream.on('finish', resolve));
      }
    }
    return destPath;
  });

  ipcMain.handle('file-exists', async (_, filePath) => {
    try {
      return fs.existsSync(filePath);
    } catch {
      return false;
    }
  });

  ipcMain.on('show-item-in-folder', (_, filePath) => {
    shell.showItemInFolder(filePath);
  });

  ipcMain.handle('open-path', async (_, filePath) => {
    // shell.openPath returns "" on success, error message on failure
    return await shell.openPath(filePath);
  });

  // Save theme/locale to preferences.json (for splash screen)
  ipcMain.on('save-preference', (_, key, value) => {
    const prefsPath = join(getAppDataPath(), 'preferences.json');
    let prefs = {};
    try { prefs = JSON.parse(fs.readFileSync(prefsPath, 'utf-8')); } catch (_) {}
    prefs[key] = value;
    fs.mkdirSync(dirname(prefsPath), { recursive: true });
    fs.writeFileSync(prefsPath, JSON.stringify(prefs, null, 2), 'utf-8');
  });

  // In-app reinstall: run uv sync + re-download binaries, report progress to renderer
  ipcMain.on('reinstall-ai-env', async (event) => {
    const isDev = !app.isPackaged;
    const appData = getAppDataPath();
    const envConfig = isDev ? loadEnvFile(join(__dirname, '.env'), __dirname) : {};
    const projectDir = isDev
      ? (envConfig.MEDIATRANX_PATH__ROOT || join(__dirname, '..', 'backend'))
      : join(process.resourcesPath, 'core_service');
    const dataDir = envConfig.MEDIATRANX_PATH__ROOT || (isDev ? projectDir : appData);
    const uvExe = isDev ? 'uv' : join(process.resourcesPath, 'uv.exe');
    const venvPath = envConfig.MEDIATRANX_PATH__VENV || join(dataDir, '.venv');
    const binDir = envConfig.MEDIATRANX_PATH__BIN || join(dataDir, 'bin');
    const uvDataDir = join(appData, 'uv_data');

    const send = (data) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('reinstall-progress', data);
      }
    };

    try {
      // 1. GPU detect + sources
      send({ stage: 'sync', detail: '', percent: 5 });
      const gpu = detectGPU();
      updatePyprojectSources(join(projectDir, 'pyproject.toml'), gpu.variant);

      // 2. uv sync
      send({ stage: 'sync', detail: 'uv sync...', percent: 10 });
      await runUvSync({ uvExe: String(uvExe), projectDir, venvPath, uvDataDir, onProgress: () => {} });
      send({ stage: 'sync', detail: '', percent: 40 });

      // 3. Re-download binaries (force = true → overwrite existing)
      const noop = () => {};
      const downloads = [
        { fn: downloadFFmpeg, args: [binDir, noop, true], label: 'FFmpeg', pct: 58 },
        { fn: downloadYtDlp, args: [binDir, noop, true], label: 'yt-dlp', pct: 70 },
        { fn: downloadLlamaServer, args: [binDir, gpu, noop, true], label: 'llama-server', pct: 85 },
        { fn: downloadLlamaCudart, args: [binDir, gpu, noop, true], label: 'CUDA Runtime', pct: 95 },
      ];
      for (const dl of downloads) {
        send({ stage: 'download', detail: dl.label, percent: dl.pct });
        try { await dl.fn(...dl.args); } catch (err) {
          console.warn(`[reinstall] ${dl.label} failed: ${err.message}`);
        }
      }

      send({ stage: 'done', detail: '', percent: 100 });
    } catch (err) {
      send({ stage: 'error', detail: err.message, percent: 0 });
    }
  });
}

async function setupEnvironment(window) {
  const isDev = !app.isPackaged;
  const appData = getAppDataPath();

  // Dev: 從 electron/.env 讀取路徑設定；Prod: 用 getAppDataPath() 預設值
  const envConfig = isDev ? loadEnvFile(join(__dirname, '.env'), __dirname) : {};

  const projectDir = isDev
    ? (envConfig.MEDIATRANX_PATH__ROOT || join(__dirname, '..', 'backend'))
    : join(process.resourcesPath, 'core_service');
  const dataDir = envConfig.MEDIATRANX_PATH__ROOT || (isDev ? projectDir : appData);
  const uvExe = isDev ? 'uv' : join(process.resourcesPath, 'uv.exe');
  const venvPath = envConfig.MEDIATRANX_PATH__VENV || join(dataDir, '.venv');
  const binDir = envConfig.MEDIATRANX_PATH__BIN || join(dataDir, 'bin');
  const uvDataDir = join(appData, 'uv_data');

  const sendProgress = (percent, stage, detail) => {
    if (window && !window.isDestroyed()) {
      const esc = (v) => String(v ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n');
      const js = `
        (function() {
          ${percent != null ? `var p = document.getElementById('percent'); if(p) p.textContent = '${Math.round(percent)}%';` : ''}
          ${stage != null ? `var s = document.getElementById('stage'); if(s) s.textContent = '${esc(stage)}';` : ''}
          ${detail != null ? `var d = document.getElementById('detail'); if(d) d.textContent = '${esc(detail)}';` : ''}
        })();
      `;
      window.webContents.executeJavaScript(js).catch(() => {});
    }
  };

  // i18n for splash text
  const prefsPath = join(appData, 'preferences.json');
  let splashLocale = 'zh-TW';
  try { splashLocale = JSON.parse(fs.readFileSync(prefsPath, 'utf-8')).locale || 'zh-TW'; } catch (_) {}
  const t = splashLocale.startsWith('zh') ? {
    detect: '偵測硬體環境...', detected: '偵測完成', sources: '設定 AI 套件來源...',
    sync: '同步 AI 套件...', checking: '檢查套件依賴...', synced: '套件同步完成',
    download: '下載', downloading: '下載', ready: '就緒',
    downloadFailed: '下載失敗（可稍後重試）', starting: '啟動中...',
    resolving: '解析套件依賴...', building: '建置', installing: '安裝',
  } : {
    detect: 'Detecting hardware...', detected: 'Detection complete', sources: 'Configuring AI sources...',
    sync: 'Syncing AI packages...', checking: 'Checking dependencies...', synced: 'Packages synced',
    download: 'Download', downloading: 'Downloading', ready: 'Ready',
    downloadFailed: 'Download failed (retry later)', starting: 'Starting...',
    resolving: 'Resolving dependencies...', building: 'Building', installing: 'Installing',
  };

  // 1. GPU detection
  sendProgress(1, t.detect, '');
  const gpu = detectGPU();
  sendProgress(2, t.detected, '');

  // 2. Update pyproject.toml sources
  sendProgress(3, t.sources, '');
  const pyprojectPath = join(projectDir, 'pyproject.toml');
  updatePyprojectSources(pyprojectPath, gpu.variant);

  // 3. uv sync
  sendProgress(5, t.sync, t.checking);
  let uvProgress = 5;
  await runUvSync({
    uvExe: String(uvExe),
    projectDir,
    venvPath,
    uvDataDir,
    onProgress: (info) => {
      uvProgress = Math.min(uvProgress + 0.3, 49);
      if (info.type === 'download') {
        sendProgress(uvProgress, t.sync, `${t.downloading} ${info.name} ${info.size}`);
      } else if (info.type === 'install') {
        sendProgress(uvProgress, t.sync, `${t.installing} ${info.name}`);
      } else if (info.type === 'resolve') {
        sendProgress(uvProgress, t.sync, t.resolving);
      } else if (info.type === 'build') {
        sendProgress(uvProgress, t.sync, `${t.building} ${info.name}`);
      }
    },
  });
  sendProgress(50, t.synced, '');

  // 4. Download binaries (non-fatal — dev mode may already have them in bin/)
  const downloads = [
    { fn: downloadFFmpeg, args: [binDir], start: 50, weight: 12, label: 'FFmpeg' },
    { fn: downloadYtDlp, args: [binDir], start: 62, weight: 10, label: 'yt-dlp' },
    { fn: downloadLlamaServer, args: [binDir, gpu], start: 72, weight: 18, label: 'llama-server' },
    { fn: downloadLlamaCudart, args: [binDir, gpu], start: 90, weight: 9, label: 'CUDA Runtime' },
  ];
  let maxPercent = 50;
  for (const dl of downloads) {
    try {
      maxPercent = Math.max(maxPercent, dl.start);
      sendProgress(maxPercent, `${t.downloading} ${dl.label}...`, '');
      await dl.fn(...dl.args, (arg1, arg2, arg3) => {
        if (typeof arg1 === 'string' && typeof arg2 === 'number' && arg2 > 0) {
          const downloaded = arg2, total = arg3 || 0;
          if (total > 0) {
            const dlMB = Math.floor(downloaded / 1024 / 1024);
            const totalMB = Math.floor(total / 1024 / 1024);
            const pct = downloaded / total;
            const newPercent = dl.start + Math.round(pct * dl.weight);
            maxPercent = Math.max(maxPercent, newPercent);
            sendProgress(maxPercent, `${t.downloading} ${dl.label}...`, `${dlMB} MB / ${totalMB} MB`);
          }
        } else if (typeof arg1 === 'string') {
          sendProgress(maxPercent, null, arg1);
        }
      });
      maxPercent = Math.max(maxPercent, dl.start + dl.weight);
      sendProgress(maxPercent, `${dl.label} ${t.ready}`, '');
    } catch (err) {
      console.warn(`[setup] ${dl.label} download failed: ${err.message}`);
      maxPercent = Math.max(maxPercent, dl.start + dl.weight);
      sendProgress(maxPercent, `${dl.label} ${t.downloadFailed}`, '');
    }
  }
  sendProgress(99, t.starting, '');
}

app.whenReady().then(async () => {
  try {
    BACKEND_PORT = await findFreePort(8001);
    console.log(`Using port ${BACKEND_PORT} for backend.`);

    createWindow();
    await mainWindow.loadFile(join(__dirname, 'splash.html'));

    // Inject saved theme + locale into splash
    const prefsPath = join(getAppDataPath(), 'preferences.json');
    let prefs = {};
    try { prefs = JSON.parse(fs.readFileSync(prefsPath, 'utf-8')); } catch (_) {}
    const theme = prefs.theme || 'dark';
    const locale = prefs.locale || 'zh-TW';
    const initText = locale.startsWith('zh') ? '正在初始化...' : 'Initializing...';
    await mainWindow.webContents.executeJavaScript(`
      document.documentElement.setAttribute('data-theme', '${theme}');
      document.documentElement.setAttribute('lang', '${locale}');
      var s = document.getElementById('stage'); if(s) s.textContent = '${initText}';
    `).catch(() => {});

    // Setup environment (runs every startup)
    try {
      await setupEnvironment(mainWindow);
    } catch (err) {
      console.error('Setup failed:', err);
      dialog.showErrorBox('環境設定失敗', `${err.message}\n\n請檢查網路連線後重新啟動應用程式。`);
      app.quit();
      return;
    }

    const isDev = !app.isPackaged;
    if (isDev) {
      startViteDevServer();
    }

    startPythonBackend();

    if (isDev) {
      await Promise.all([
        waitForServer(FRONTEND_DEV_PORT),
        waitForServer(BACKEND_PORT),
      ]);
      mainWindow.webContents.executeJavaScript(
        "var p=document.getElementById('percent'); if(p) p.textContent='100%';"
      ).catch(() => {});
      mainWindow.loadURL(`http://localhost:${FRONTEND_DEV_PORT}/`);
    } else {
      await waitForServer(BACKEND_PORT);
      mainWindow.webContents.executeJavaScript(
        "var p=document.getElementById('percent'); if(p) p.textContent='100%';"
      ).catch(() => {});
      let frontendPath = join(process.resourcesPath, 'frontend_dist', 'index.html');
      if (!fs.existsSync(frontendPath)) {
        const appDir = dirname(app.getAppPath());
        const fallbackPath = join(appDir, 'frontend_dist', 'index.html');
        if (fs.existsSync(fallbackPath)) frontendPath = fallbackPath;
      }
      if (fs.existsSync(frontendPath)) {
        mainWindow.loadFile(frontendPath);
      } else {
        mainWindow.loadURL(`http://localhost:${BACKEND_PORT}/`);
      }
    }
  } catch (err) {
    console.error('Initialization failed:', err);
    dialog.showErrorBox('啟動失敗', `應用程式初始化過程中發生錯誤：\n${err.message}`);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

let isQuitting = false;
app.on('before-quit', (event) => {
  if (isQuitting) return;
  isQuitting = true;
  event.preventDefault();

  stopViteDevServer();
  stopPythonBackend();
  app.exit(0);
});
