// electron/main.js
const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { join, dirname } = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const os = require('os');
const net = require('net');

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
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      resolve(findFreePort(startPort + 1));
    });
  });
}

// 取得應用程式資料目錄
function getAppDataPath() {
  if (!app.isPackaged) {
    // 開發階段：將資料存放在專案根目錄下的 data 檔案夾
    const devPath = join(__dirname, '..', '..', 'data');
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

// 在開發階段，將 Electron 內建的資料路徑（如 Cache, LocalStorage）也導向專案內部
if (!app.isPackaged) {
  const devDataPath = getAppDataPath();
  app.setPath('userData', join(devDataPath, 'electron_data'));
}

// 檢查並確保環境目錄存在 (BUILD_STRATEGY.md)
async function ensureVenv(window) {
  if (!app.isPackaged) return;

  const appDataPath = getAppDataPath();
  const venvPath = join(appDataPath, '.venv');

  if (!fs.existsSync(venvPath)) {
    console.log('Creating initial data directory...');
    fs.mkdirSync(venvPath, { recursive: true });
  }
}

function startViteDevServer() {
  console.log('Starting Vite dev server on port', FRONTEND_DEV_PORT);
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  viteProcess = spawn(npmCmd, ['run', 'dev'], {
    cwd: join(__dirname, '..', 'frontend'),
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: true,
    env: { ...process.env, FORCE_COLOR: '1', VITE_BACKEND_PORT: String(BACKEND_PORT) }
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

function waitForServer(port, maxAttempts = 60) {
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
    const projectRoot = join(__dirname, '..', '..');
    const devLog = join(projectRoot, 'data', 'dev_backend.log');
    const logStream = fs.createWriteStream(devLog, { flags: 'a' });
    logStream.write(`\n--- Dev Backend Start: ${new Date().toISOString()} ---\n`);

    console.log(`Starting Python backend (dev) on port ${BACKEND_PORT} via uv run...`);
    console.log(`Logs will be written to: ${devLog}`);

    pythonProcess = spawn('uv', [
      'run', '--project', projectRoot,
      'python', '-u', '-m', 'backend.main',
      '--host', '127.0.0.1',
      '--port', String(BACKEND_PORT)
    ], {
      cwd: join(projectRoot, 'src'),
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
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
    const backendLog = join(appDataPath, 'core_debug.log');
    const logStream = fs.createWriteStream(backendLog, { flags: 'a' });
    logStream.write(`\n--- Core Engine Start Attempt: ${new Date().toISOString()} ---\n`);
    logStream.write(`Path: ${backendExe} (Port: ${BACKEND_PORT})\n`);

    pythonProcess = spawn(backendExe, ['--port', String(BACKEND_PORT)], {
      cwd: dirname(backendExe),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env },
      windowsHide: true
    });

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
    backgroundColor: '#1f1c2c',
    icon: join(__dirname, 'icon.ico'),
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      additionalArguments: [`--backend-port=${BACKEND_PORT}`]
    }
  });

  mainWindow.on('maximize', () => mainWindow.webContents.send('window-maximized', true));
  mainWindow.on('unmaximize', () => mainWindow.webContents.send('window-maximized', false));
  if (!app.isPackaged) mainWindow.webContents.openDevTools();

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
}

app.whenReady().then(async () => {
  try {
    BACKEND_PORT = await findFreePort(8001);
    console.log(`Using port ${BACKEND_PORT} for backend.`);

    createWindow();
    mainWindow.loadFile(join(__dirname, 'splash.html'));

    const isDev = !app.isPackaged;
    if (isDev) {
      startViteDevServer();
      startPythonBackend();
      await Promise.all([
        waitForServer(FRONTEND_DEV_PORT),
        waitForServer(BACKEND_PORT),
      ]);
      mainWindow.loadURL(`http://localhost:${FRONTEND_DEV_PORT}/`);
    } else {
      await ensureVenv(mainWindow);
      startPythonBackend();
      await waitForServer(BACKEND_PORT);

      // 優先載入本地靜態檔
      let frontendPath = join(process.resourcesPath, 'frontend_dist', 'index.html');

      const appDataPath = getAppDataPath();
      const backendLog = join(appDataPath, 'core_debug.log');
      fs.appendFileSync(backendLog, `\n--- Frontend Load Attempt: ${new Date().toISOString()} ---\n`);
      fs.appendFileSync(backendLog, `Resources Path: ${process.resourcesPath}\n`);
      fs.appendFileSync(backendLog, `Checking primary path: ${frontendPath}\n`);

      if (!fs.existsSync(frontendPath)) {
        // Fallback: 嘗試從 appDir 尋找 (處理 unpacked 或結構差異)
        const appDir = dirname(app.getAppPath());
        const fallbackPath = join(appDir, 'frontend_dist', 'index.html');
        fs.appendFileSync(backendLog, `Primary path not found. Checking fallback: ${fallbackPath}\n`);
        if (fs.existsSync(fallbackPath)) {
          frontendPath = fallbackPath;
        }
      }

      if (fs.existsSync(frontendPath)) {
        fs.appendFileSync(backendLog, `Found! Loading via loadFile: ${frontendPath}\n`);
        mainWindow.loadFile(frontendPath);
      } else {
        fs.appendFileSync(backendLog, `Failed! frontendPath not found, using loadURL (Backend Fallback)\n`);
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
  stopViteDevServer();
  stopPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopViteDevServer();
  stopPythonBackend();
});
