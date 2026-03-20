import { app, BrowserWindow, ipcMain, shell, Menu, dialog, nativeTheme } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import started from 'electron-squirrel-startup';

import { initLogFile, fileLog, closeLogFile } from './logging';
import { loadEnvFile } from './env';
import { createSplashWindow, splashProgress, splashLog, closeSplash } from './splash';
import { startBackend, waitForBackend, stopBackend, getBackendPort, getContelligenceHome } from './backend';
import { checkCopilotCli, checkAzureLogin } from './cli-detection';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

// Load dev overrides before anything else
loadEnvFile();

// Ensure ~/.contelligence/ exists for app config, data, and logs.
// Electron's default userData path is left untouched so Chromium internals
// (GPU cache, session storage, etc.) stay in the platform-standard location
// (~/Library/Application Support/, %APPDATA%\, ~/.config/).
const contelligenceHome = path.join(app.getPath('home'), '.contelligence');
fs.mkdirSync(contelligenceHome, { recursive: true });

// Start file logging early so we capture everything
initLogFile();

// Set app name early so taskbar/dock shows correct name immediately
app.setName('Contelligence');

// Dev mode: set CONTELLIGENCE_API_URL to skip backend startup
// and connect to an already-running API server instead.
const externalApiUrl = process.env.CONTELLIGENCE_API_URL || '';

// ---------------------------------------------------------------------------
// Window + API configuration
// ---------------------------------------------------------------------------

const getApiBaseUrl = () =>
  externalApiUrl || `http://127.0.0.1:${getBackendPort() || 8081}/api/v1`;

let mainWindow: BrowserWindow | null = null;

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    title: 'Contelligence',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#111318',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Show window once ready to avoid white flash
  mainWindow.once('ready-to-show', () => {
    splashProgress(100, 'Ready');
    // Brief delay so the user sees "Ready" before the splash disappears
    setTimeout(() => {
      closeSplash();
      mainWindow?.show();
    }, 300);
  });

  // Open external links in the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(
      path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`),
    );
  }

  // Open DevTools in development
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    mainWindow.webContents.openDevTools();
  }
};

// ─── IPC Handlers ───────────────────────────────────────────────────────────

// Return the API base URL to the renderer (dynamic port)
ipcMain.handle('get-api-base-url', () => getApiBaseUrl());

// Get app version info
ipcMain.handle('get-app-info', () => ({
  version: app.getVersion(),
  name: app.getName(),
  platform: process.platform,
  arch: process.arch,
  electron: process.versions.electron,
  chrome: process.versions.chrome,
  node: process.versions.node,
}));

// Window controls
ipcMain.handle('window-minimize', () => mainWindow?.minimize());
ipcMain.handle('window-maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
ipcMain.handle('window-close', () => mainWindow?.close());
ipcMain.handle('window-is-maximized', () => mainWindow?.isMaximized());

// Show open file dialog
ipcMain.handle('show-open-dialog', async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return dialog.showOpenDialog(mainWindow, options);
});

// Show save dialog
ipcMain.handle('show-save-dialog', async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePath: undefined };
  return dialog.showSaveDialog(mainWindow, options);
});

// Dark mode
ipcMain.handle('get-native-theme', () => nativeTheme.shouldUseDarkColors);

// ─── Application Menu ───────────────────────────────────────────────────────

const isMac = process.platform === 'darwin';

const menuTemplate: Electron.MenuItemConstructorOptions[] = [
  ...(isMac
    ? [
        {
          label: app.name,
          submenu: [
            { role: 'about' as const },
            { type: 'separator' as const },
            { role: 'services' as const },
            { type: 'separator' as const },
            { role: 'hide' as const },
            { role: 'hideOthers' as const },
            { role: 'unhide' as const },
            { type: 'separator' as const },
            { role: 'quit' as const },
          ],
        },
      ]
    : []),
  {
    label: 'Edit',
    submenu: [
      { role: 'undo' },
      { role: 'redo' },
      { type: 'separator' },
      { role: 'cut' },
      { role: 'copy' },
      { role: 'paste' },
      { role: 'selectAll' },
    ],
  },
  {
    label: 'View',
    submenu: [
      { role: 'reload' },
      { role: 'forceReload' },
      { role: 'toggleDevTools' },
      { type: 'separator' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { type: 'separator' },
      { role: 'togglefullscreen' },
    ],
  },
  {
    label: 'Window',
    submenu: [
      { role: 'minimize' },
      { role: 'zoom' },
      ...(isMac
        ? [{ type: 'separator' as const }, { role: 'front' as const }]
        : [{ role: 'close' as const }]),
    ],
  },
];

// ─── App Lifecycle ──────────────────────────────────────────────────────────

app.on('ready', async () => {
  const menu = Menu.buildFromTemplate(menuTemplate);
  Menu.setApplicationMenu(menu);

  // Show splash window immediately
  createSplashWindow();
  splashProgress(5, 'Initializing\u2026');

  // ── Step 1: Copilot CLI check ──
  splashProgress(10, 'Checking GitHub Copilot CLI\u2026');
  let copilotCliPath = '';
  const copilotStatus = checkCopilotCli();
  if (copilotStatus.found) {
    copilotCliPath = copilotStatus.path;
    console.log(`[main] Copilot CLI found at ${copilotCliPath}`);
    fileLog('INFO', `Copilot CLI found at ${copilotCliPath}`);
    splashLog('\u2713 Copilot CLI found');
  } else {
    console.warn('[main] Copilot CLI not found');
    fileLog('WARN', 'Copilot CLI not found');
    splashLog('\u26A0 Copilot CLI not found \u2014 AI features unavailable', true);
  }

  // ── Step 2: Azure CLI check ──
  splashProgress(20, 'Checking Azure CLI\u2026');
  const azureStatus = checkAzureLogin();
  if (azureStatus.loggedIn) {
    splashLog('\u2713 Azure CLI authenticated');
  } else {
    fileLog('WARN', 'Azure CLI not authenticated');
    splashLog('\u26A0 Azure CLI not logged in \u2014 some features unavailable', true);
  }

  // ── Step 3: Start backend ──
  if (externalApiUrl) {
    splashProgress(80, 'Connecting to external API\u2026');
    console.log(`[main] Dev mode: using external API at ${externalApiUrl}`);
    fileLog('INFO', `Dev mode: using external API at ${externalApiUrl}`);
    splashLog('\u2713 Using external API');
  } else {
    try {
      splashProgress(30, 'Starting backend service\u2026');
      fileLog('INFO', 'Starting backend...');
      await startBackend(copilotCliPath);
      splashLog('\u2713 Backend process started');

      splashProgress(45, 'Waiting for backend to be ready\u2026');
      fileLog('INFO', `Backend process started, waiting for health check on port ${getBackendPort()}...`);

      await waitForBackend(30_000, 500, (elapsed, total) => {
        const pct = 45 + Math.round((elapsed / total) * 45);
        splashProgress(Math.min(pct, 89), 'Waiting for backend to be ready\u2026');
      });

      console.log(`[main] Backend ready on port ${getBackendPort()}`);
      fileLog('INFO', `Backend ready on port ${getBackendPort()}`);
      splashLog('\u2713 Backend ready');
    } catch (err) {
      const errMsg = `Backend startup failed: ${err}`;
      fileLog('ERROR', errMsg);
      closeSplash();
      dialog.showErrorBox(
        'Backend Startup Failed',
        `Could not start the Contelligence backend.\n\nCheck logs at:\n${path.join(getContelligenceHome(), 'logs')}\n\n${err}`,
      );
      app.quit();
      return;
    }
  }

  // ── Step 4: Open main window ──
  splashProgress(95, 'Loading interface\u2026');
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (!externalApiUrl) stopBackend();
    app.quit();
  }
});

app.on('before-quit', () => {
  if (!externalApiUrl) stopBackend();
  fileLog('INFO', 'App quitting');
  closeLogFile();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
// code. You can also put them in separate files and import them here.
