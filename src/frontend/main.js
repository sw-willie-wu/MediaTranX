// electron/main.js
import { app, BrowserWindow, ipcMain, dialog } from 'electron';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawn, execSync } from 'child_process';
import http from 'http';
import fs from 'fs';

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
  const isDev = !app.isPackaged;

  if (isDev) {
    // 開發模式：使用 venv 的 python
    const projectRoot = join(__dirname, '..', '..');
    const venvPython = join(projectRoot, '.venv', 'Scripts', 'python.exe');

    console.log('Starting Python backend (dev) on port', BACKEND_PORT);

    pythonProcess = spawn(venvPython, [
      '-m', 'uvicorn', 'backend.main:app',
      '--host', '127.0.0.1',
      '--port', String(BACKEND_PORT)
    ], {
      cwd: join(projectRoot, 'src'),
      stdio: ['pipe', 'pipe', 'pipe']
    });
  } else {
    // 生產模式：使用 PyInstaller 打包的 backend.exe
    const backendExe = join(process.resourcesPath, 'backend', 'backend.exe');

    console.log('Starting backend (production):', backendExe);

    pythonProcess = spawn(backendExe, [], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env }
    });
  }

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
    if (process.platform === 'win32') {
      // 使用 taskkill /t 確保子進程也被終止
      try {
        execSync(`taskkill /f /t /pid ${pythonProcess.pid}`, { stdio: 'ignore' });
      } catch (e) {
        // 進程可能已經退出
      }
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
    show: true, // 立即顯示（背景色），減少啟動感知延遲
    backgroundColor: '#1f1c2c',
    icon: join(__dirname, 'src', 'assets', 'icon.ico'),
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false  // 需要關閉 sandbox 才能使用 File.path 取得檔案路徑
    }
  });

  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window-maximized', true);
  });

  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window-maximized', false);
  });

  // 開發模式下開啟 DevTools
  if (!app.isPackaged) {
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

  // 重新啟動應用程式（CUDA 安裝後使用）
  ipcMain.on('restart-app', () => {
    stopViteDevServer();
    stopPythonBackend();
    app.relaunch();
    app.exit(0);
  });

  // 下載後端檔案到本機路徑
  ipcMain.handle('download-to-path', async (event, { url, destPath }) => {
    return new Promise((resolve, reject) => {
      const parsedUrl = new URL(url);
      const req = http.get({ host: parsedUrl.hostname, port: parsedUrl.port, path: parsedUrl.pathname + parsedUrl.search }, (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        const file = fs.createWriteStream(destPath);
        res.pipe(file);
        file.on('finish', () => { file.close(); resolve(true); });
        file.on('error', (err) => { fs.unlink(destPath, () => {}); reject(err); });
      });
      req.on('error', reject);
    });
  });

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
    // 開發模式：先顯示 splash 畫面，等前後端都就緒後載入頁面
    console.log('Development mode - starting Vite and Python backend...');
    startViteDevServer();
    startPythonBackend();
    createWindow();
    mainWindow.loadFile(join(__dirname, 'splash.html'));
    try {
      await Promise.all([
        waitForServer(FRONTEND_DEV_PORT),
        waitForServer(BACKEND_PORT),
      ]);
      mainWindow.loadURL(`http://localhost:${FRONTEND_DEV_PORT}/`);
    } catch (err) {
      console.error('Failed to start dev servers:', err);
    }
  } else {
    // 生產模式：啟動 backend.exe，等就緒後載入前端（由後端 serve）
    console.log('Production mode - starting backend...');
    startPythonBackend();
    createWindow();
    mainWindow.loadFile(join(__dirname, 'splash.html'));
    try {
      await waitForServer(BACKEND_PORT);
      mainWindow.loadURL(`http://localhost:${BACKEND_PORT}/`);
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
