import { app, BrowserWindow, ipcMain, shell, Menu, dialog, nativeTheme } from 'electron';
import { execFile, ChildProcess, execSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import started from 'electron-squirrel-startup';

// Handle creating/removing shortcuts on Windows when installing/uninstalling.
if (started) {
  app.quit();
}

// ---------------------------------------------------------------------------
// Load .env.local from project root (dev overrides, not committed)
// ---------------------------------------------------------------------------
function loadEnvFile(): void {
  const candidates = [
    path.join(__dirname, '..', '..', '.env.local'),  // dev: contelligence-electron/.env.local
    path.join(process.resourcesPath || '', '.env.local'), // packaged (unlikely but safe)
  ];
  for (const envPath of candidates) {
    if (fs.existsSync(envPath)) {
      const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eqIdx = trimmed.indexOf('=');
        if (eqIdx > 0) {
          const key = trimmed.slice(0, eqIdx).trim();
          const value = trimmed.slice(eqIdx + 1).trim();
          if (!process.env[key]) process.env[key] = value; // don't override shell env
        }
      }
      break;
    }
  }
}
loadEnvFile();

// ---------------------------------------------------------------------------
// Backend lifecycle helpers
// ---------------------------------------------------------------------------

let backendProcess: ChildProcess | null = null;
let backendPort: number | null = null;

/**
 * Dev mode: set CONTELLIGENCE_API_URL to skip backend startup
 * and connect to an already-running API server instead.
 * Set it as a shell env var or in contelligence-electron/.env.local
 */
const externalApiUrl = process.env.CONTELLIGENCE_API_URL || '';

/** Locate the bundled Python backend (PyInstaller or source). */
function getBackendPath(): string {
  const isPackaged = app.isPackaged;

  if (isPackaged) {
    // PyInstaller one-folder bundle placed alongside the app via extraResource
    const resourceDir = process.resourcesPath;
    const binaryName =
      process.platform === 'win32'
        ? 'contelligence-agent.exe'
        : 'contelligence-agent';
    return path.join(resourceDir, 'backend', binaryName);
  }

  // Development — run from source via uvicorn  
  return '';
}

/** Find an available TCP port starting from *preferred*. */
function findAvailablePort(preferred = 8081): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => {
      // Port taken — try the next one
      resolve(findAvailablePort(preferred + 1));
    });
    server.listen(preferred, '127.0.0.1', () => {
      const addr = server.address();
      if (addr && typeof addr !== 'string') {
        const port = addr.port;
        server.close(() => resolve(port));
      } else {
        server.close(() => reject(new Error('Could not determine port')));
      }
    });
  });
}

/** Ensure a default .env exists in the user data directory. */
function ensureDefaultEnvFile(): string {
  const envPath = path.join(app.getPath('userData'), '.env');
  if (!fs.existsSync(envPath)) {
    const defaults = [
      '# Contelligence local-mode configuration',
      '# Generated on first launch — edit as needed',
      '',
      'STORAGE_MODE=local',
      `LOCAL_DATA_DIR=${app.getPath('userData')}`,
      '',
      '# GitHub Copilot token (required for AI features)',
      '# GITHUB_COPILOT_TOKEN=ghp_...',
      '',
      '# Logging',
      'LOG_LEVEL=INFO',
      '',
    ].join('\n');
    fs.mkdirSync(path.dirname(envPath), { recursive: true });
    fs.writeFileSync(envPath, defaults, 'utf-8');
  }
  return envPath;
}

/** Start the Python backend process. */
async function startBackend(): Promise<void> {
  backendPort = await findAvailablePort(8081);
  const envFile = ensureDefaultEnvFile();

  const backendPath = getBackendPath();

  // Build child env — merge the .env file with current env
  const childEnv: Record<string, string> = { ...process.env } as Record<string, string>;
  childEnv['API_PORT'] = String(backendPort);
  childEnv['API_HOST'] = '127.0.0.1';
  childEnv['STORAGE_MODE'] = 'local';
  childEnv['LOCAL_DATA_DIR'] = app.getPath('userData');

  // Parse .env file into child env (simple KEY=VALUE, skip comments)
  if (fs.existsSync(envFile)) {
    const lines = fs.readFileSync(envFile, 'utf-8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx > 0) {
        const key = trimmed.slice(0, eqIdx).trim();
        const value = trimmed.slice(eqIdx + 1).trim();
        childEnv[key] = value;
      }
    }
  }

  if (backendPath) {
    // Packaged PyInstaller binary
    backendProcess = execFile(backendPath, [], {
      env: childEnv,
      cwd: path.dirname(backendPath),
    });
  } else {
    // Development — run uvicorn from the agent directory
    const agentDir = path.join(__dirname, '..', '..', '..', 'contelligence-agent');
    backendProcess = execFile(
      'uvicorn',
      ['main:app', '--host', '127.0.0.1', '--port', String(backendPort)],
      { env: childEnv, cwd: agentDir },
    );
  }

  backendProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.on('exit', (code) => {
    console.log(`[backend] process exited with code ${code}`);
    backendProcess = null;
  });
}

/** Wait for the backend /api/v1/health endpoint to respond. */
async function waitForBackend(
  timeoutMs = 30_000,
  intervalMs = 500,
): Promise<void> {
  const url = `http://127.0.0.1:${backendPort}/api/v1/health`;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return;
    } catch {
      // Not ready yet
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`Backend did not start within ${timeoutMs}ms`);
}

/** Gracefully stop the backend. */
function stopBackend(): void {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill('SIGTERM');
    // Force-kill after 5 seconds if it hasn't stopped
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        backendProcess.kill('SIGKILL');
      }
    }, 5_000);
  }
  backendProcess = null;
}

// ---------------------------------------------------------------------------
// Azure login verification
// ---------------------------------------------------------------------------

interface AzureLoginResult {
  loggedIn: boolean;
  error?: string;
}

/** Check if the user is logged in to Azure CLI (always verified). */
function checkAzureLogin(): AzureLoginResult {
  try {
    execSync('az account show', { stdio: 'pipe', timeout: 10_000 });
    return { loggedIn: true };
  } catch {
    return {
      loggedIn: false,
      error:
        'Not logged in to Azure CLI. Some features may be unavailable.\n' +
        'Run "az login" in a terminal to authenticate.',
    };
  }
}

// ---------------------------------------------------------------------------
// Window + API configuration
// ---------------------------------------------------------------------------

const getApiBaseUrl = () =>
  externalApiUrl || `http://127.0.0.1:${backendPort || 8081}/api/v1`;

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
    mainWindow?.show();
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

  // Always verify Azure login
  const azureStatus = checkAzureLogin();
  if (!azureStatus.loggedIn) {
    dialog.showMessageBoxSync({
      type: 'warning',
      title: 'Azure CLI Not Authenticated',
      message: azureStatus.error || 'Azure CLI is not logged in.',
      detail:
        'Some features that require Azure services may be unavailable.\n' +
        'Run "az login" in a terminal and restart the app.',
      buttons: ['Continue Anyway'],
    });
  }

  // Start the Python backend (skipped when CONTELLIGENCE_API_URL is set)
  if (externalApiUrl) {
    console.log(`[main] Dev mode: using external API at ${externalApiUrl}`);
  } else {
    try {
      await startBackend();
      await waitForBackend();
      console.log(`[main] Backend ready on port ${backendPort}`);
    } catch (err) {
      dialog.showErrorBox(
        'Backend Startup Failed',
        `Could not start the Contelligence backend.\n\n${err}`,
      );
      app.quit();
      return;
    }
  }

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
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
// code. You can also put them in separate files and import them here.
