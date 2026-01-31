// electron/main.js
import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import http from 'http';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 子進程
let pythonProcess = null;
let viteProcess = null;

// 後端 API port（與前端 Vite dev server 分開）
const BACKEND_PORT = 8001;
const FRONTEND_DEV_PORT = 8000;

function startViteDevServer() {
  console.log('Starting Vite dev server on port', FRONTEND_DEV_PORT);

  // Windows 上使用 npm.cmd
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';

  viteProcess = spawn(npmCmd, ['run', 'dev'], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: true,
    env: { ...process.env, FORCE_COLOR: '1' }
  });

  viteProcess.stdout.on('data', (data) => {
    console.log(`[Vite] ${data}`);
  });

  viteProcess.stderr.on('data', (data) => {
    console.error(`[Vite] ${data}`);
  });

  viteProcess.on('close', (code) => {
    console.log(`Vite dev server exited with code ${code}`);
  });

  viteProcess.on('error', (err) => {
    console.error('Failed to start Vite dev server:', err);
  });
}

function stopViteDevServer() {
  if (viteProcess) {
    console.log('Stopping Vite dev server...');
    // Windows 上需要 kill 整個進程樹
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', viteProcess.pid, '/f', '/t']);
    } else {
      viteProcess.kill();
    }
    viteProcess = null;
  }
}

// 等待服務啟動
function waitForServer(port, maxAttempts = 30) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let resolved = false;

    const check = () => {
      if (resolved) return;
      attempts++;
      console.log(`Checking if port ${port} is ready... (attempt ${attempts}/${maxAttempts})`);

      const req = http.get(`http://localhost:${port}/`, (res) => {
        if (!resolved) {
          resolved = true;
          console.log(`Port ${port} is ready!`);
          res.destroy();
          resolve();
        }
      });

      req.on('error', () => {
        if (resolved) return;
        if (attempts >= maxAttempts) {
          resolved = true;
          reject(new Error(`Server on port ${port} not ready after ${maxAttempts} attempts`));
        } else {
          setTimeout(check, 500);
        }
      });

      req.setTimeout(1000, () => {
        req.destroy();
        if (resolved) return;
        if (attempts >= maxAttempts) {
          resolved = true;
          reject(new Error(`Server on port ${port} timeout`));
        } else {
          setTimeout(check, 500);
        }
      });
    };
    check();
  });
}

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
    icon: join(__dirname, 'src', 'assets', 'icon.ico'),
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false  // 需要關閉 sandbox 才能使用 File.path 取得檔案路徑
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

  // 選擇資料夾對話框
  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'createDirectory'],
      title: '選擇輸出資料夾'
    });
    if (result.canceled) {
      return null;
    }
    return result.filePaths[0];
  })

  // 另存新檔對話框
  ipcMain.handle('save-file-dialog', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, {
      title: options.title || '另存新檔',
      defaultPath: options.defaultPath || '',
      filters: options.filters || []
    });
    if (result.canceled) {
      return null;
    }
    return result.filePath;
  })
}

// 應用程式初始化完成後
app.whenReady().then(async () => {
  const isDev = !app.isPackaged;

  if (isDev) {
    // 開發模式：自動啟動 Vite dev server 和 Python 後端
    console.log('Development mode - starting Vite and Python backend...');
    startViteDevServer();
    startPythonBackend();
    // 等待 Vite 準備好再建立視窗
    try {
      await waitForServer(FRONTEND_DEV_PORT);
      createWindow();
    } catch (err) {
      console.error('Failed to start dev servers:', err);
    }
  } else {
    // 生產模式：先啟動 Python 後端
    startPythonBackend();
    try {
      await waitForServer(BACKEND_PORT);
      createWindow();
    } catch (err) {
      console.error('Failed to start backend:', err);
    }
  }

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// 所有視窗關閉時
app.on('window-all-closed', function () {
  stopViteDevServer();
  stopPythonBackend();
  if (process.platform !== 'darwin') app.quit();
});

// 應用程式退出前
app.on('before-quit', () => {
  stopViteDevServer();
  stopPythonBackend();
});