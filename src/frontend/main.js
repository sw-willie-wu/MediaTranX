// electron/main.js
import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn, execSync } from 'child_process';
import http from 'http';
import fs from 'fs';
import os from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 子進程
let pythonProcess = null;
let viteProcess = null;

// 後端 API port（與前端 Vite dev server 分開）
const BACKEND_PORT = 8001;
const FRONTEND_DEV_PORT = 8000;

// 取得應用程式資料目錄
function getAppDataPath() {
  const appData = process.env.APPDATA || (process.platform === 'darwin' ? join(os.homedir(), 'Library', 'Application Support') : join(os.homedir(), '.config'));
  const path = join(appData, 'MediaTranX');
  if (!fs.existsSync(path)) {
    fs.mkdirSync(path, { recursive: true });
  }
  return path;
}

// 檢查並確保環境目錄存在 (BUILD_STRATEGY.md)
async function ensureVenv(window) {
  if (!app.isPackaged) return;

  const appDataPath = getAppDataPath();
  const venvPath = join(appDataPath, '.venv');
  
  // 基礎依賴已在 core.exe (Nuitka) 中
  // 這裡只確保目錄存在，未來 uv sync --extra ai 會用到
  if (!fs.existsSync(venvPath)) {
    console.log('Creating initial data directory...');
    fs.mkdirSync(venvPath, { recursive: true });
  }
}

function startViteDevServer() {
  console.log('Starting Vite dev server on port', FRONTEND_DEV_PORT);
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  viteProcess = spawn(npmCmd, ['run', 'dev'], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: true,
    env: { ...process.env, FORCE_COLOR: '1' }
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
    console.log('Starting Python backend (dev) via uv run...');

    pythonProcess = spawn('uv', [
      'run', '--project', projectRoot,
      'python', '-m', 'uvicorn', 'backend.main:app',
      '--host', '127.0.0.1',
      '--port', String(BACKEND_PORT)
    ], {
      cwd: join(projectRoot, 'src'),
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true
    });
  } else {
    // 生產模式：實作資源路徑探測 (配合 Nuitka Standalone 模式)
    const possiblePaths = [
      join(process.resourcesPath, 'core_engine', 'main.dist', 'core.exe'),
      join(process.resourcesPath, 'core.exe'),
      join(dirname(app.getPath('exe')), 'resources', 'core_engine', 'main.dist', 'core.exe')
    ];

    let backendExe = null;
    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        backendExe = p;
        break;
      }
    }

    if (!backendExe) {
      const errorMsg = `找不到核心後端組件。\n已嘗試路徑：\n${possiblePaths.join('\n')}`;
      dialog.showErrorBox('啟動失敗', errorMsg);
      app.quit();
      return;
    }

    const appDataPath = getAppDataPath();
    const backendLog = join(appDataPath, 'core_debug.log');
    const logStream = fs.createWriteStream(backendLog, { flags: 'a' });
    logStream.write(`\n--- Core Engine Start Attempt: ${new Date().toISOString()} ---\n`);
    logStream.write(`Path: ${backendExe}\n`);

    pythonProcess = spawn(backendExe, [], {
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
      try { execSync(`taskkill /f /t /pid ${pythonProcess.pid}`, { stdio: 'ignore' }); } catch (e) {}
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
    icon: join(__dirname, 'src', 'assets', 'icon.ico'),
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
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
}

app.whenReady().then(async () => {
  createWindow();
  mainWindow.loadFile(join(__dirname, 'splash.html'));

  try {
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
      mainWindow.loadURL(`http://localhost:${BACKEND_PORT}/`);
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
