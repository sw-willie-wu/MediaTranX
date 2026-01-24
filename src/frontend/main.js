// electron/main.js
import { app, BrowserWindow, ipcMain } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Python 後端進程
let pythonProcess = null;

// 後端 API port（與前端 Vite dev server 分開）
const BACKEND_PORT = 8001;
const FRONTEND_DEV_PORT = 8000;

function startPythonBackend() {
  const projectRoot = join(__dirname, '..', '..');
  const venvPython = join(projectRoot, 'Scripts', 'python.exe');

  console.log('Starting Python backend on port', BACKEND_PORT);

  pythonProcess = spawn(venvPython, [
    '-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT)
  ], {
    cwd: join(projectRoot, 'src'),
    stdio: ['pipe', 'pipe', 'pipe']
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python] ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python backend exited with code ${code}`);
  });

  pythonProcess.on('error', (err) => {
    console.error('Failed to start Python backend:', err);
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    console.log('Stopping Python backend...');
    pythonProcess.kill();
    pythonProcess = null;
  }
}

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    frame: false,
    show: false, // 先隱藏，等載入完成再顯示
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // 載入前端頁面
  const isDev = !app.isPackaged;
  if (isDev) {
    // 開發模式：從 Vite dev server 載入
    mainWindow.loadURL(`http://localhost:${FRONTEND_DEV_PORT}/`);
  } else {
    // 生產模式：從 Python 後端載入靜態檔案
    mainWindow.loadURL(`http://localhost:${BACKEND_PORT}/static/`);
  }

  // 視窗準備好後顯示（有動畫效果）
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window-maximized', true);
  });

  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window-maximized', false);
  });

  // 開發模式下開啟 DevTools
  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  ipcMain.on('minimize-window', () => {
    if (mainWindow) {
      mainWindow.minimize();
    }
  })
  
  // 監聽最大化/還原事件
  ipcMain.on('maximize-window', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.restore();  // 還原
      } else {
        mainWindow.maximize();  // 最大化
      }
    }
  })

  ipcMain.handle('check-maximized', () => {
    return mainWindow.isMaximized();
  })
  
  // 監聽關閉事件
  ipcMain.on('close-window', () => {
    if (mainWindow) {
      mainWindow.close();
    }
  })
}

// 應用程式初始化完成後
app.whenReady().then(() => {
  const isDev = !app.isPackaged;

  if (isDev) {
    // 開發模式：直接創建視窗（需手動啟動 Vite 和 Python 後端）
    console.log('Development mode - please ensure Vite dev server is running on port', FRONTEND_DEV_PORT);
    startPythonBackend(); // 啟動後端 API
    setTimeout(() => {
      createWindow();
    }, 1500);
  } else {
    // 生產模式：先啟動 Python 後端
    startPythonBackend();
    setTimeout(() => {
      createWindow();
    }, 2000);
  }

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// 所有視窗關閉時
app.on('window-all-closed', function () {
  stopPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});

// 應用程式退出前
app.on('before-quit', () => {
  stopPythonBackend();
});