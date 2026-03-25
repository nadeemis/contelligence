import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload script — exposes a safe, typed API from the main process
 * to the renderer via contextBridge. No Node.js APIs leak into the
 * renderer; only explicitly allowed IPC channels are accessible.
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // API base URL (resolved from main process — dynamic port)
  getApiBaseUrl: (): Promise<string> => ipcRenderer.invoke('get-api-base-url'),

  // App information
  getAppInfo: (): Promise<{
    version: string;
    name: string;
    platform: string;
    arch: string;
    electron: string;
    chrome: string;
    node: string;
  }> => ipcRenderer.invoke('get-app-info'),

  // Window controls (for custom titlebar on Windows/Linux)
  windowMinimize: (): Promise<void> => ipcRenderer.invoke('window-minimize'),
  windowMaximize: (): Promise<void> => ipcRenderer.invoke('window-maximize'),
  windowClose: (): Promise<void> => ipcRenderer.invoke('window-close'),
  windowIsMaximized: (): Promise<boolean> => ipcRenderer.invoke('window-is-maximized'),

  // File dialogs
  showOpenDialog: (options: Electron.OpenDialogOptions): Promise<Electron.OpenDialogReturnValue> =>
    ipcRenderer.invoke('show-open-dialog', options),
  showSaveDialog: (options: Electron.SaveDialogOptions): Promise<Electron.SaveDialogReturnValue> =>
    ipcRenderer.invoke('show-save-dialog', options),

  // Theme
  getNativeTheme: (): Promise<boolean> => ipcRenderer.invoke('get-native-theme'),

  // Azure CLI status
  getAzureStatus: (): Promise<{ available: boolean; loggedIn: boolean; error?: string }> =>
    ipcRenderer.invoke('get-azure-status'),

  // User identity (machine + optional Azure)
  getUserIdentity: (): Promise<{
    machine: { username: string; fullName: string };
    azure?: { name: string; email: string; tenantId: string };
  }> => ipcRenderer.invoke('get-user-identity'),

  // Backend lifecycle events (sleep/wake resilience)
  onBackendRestarted: (callback: () => void): (() => void) => {
    const handler = () => callback();
    ipcRenderer.on('backend-restarted', handler);
    return () => ipcRenderer.removeListener('backend-restarted', handler);
  },
});
