/**
 * Type declarations for the Electron IPC bridge exposed via preload.
 * Available at `window.electronAPI` in the renderer process.
 */
export interface ElectronAPI {
  getApiBaseUrl(): Promise<string>;
  getAppInfo(): Promise<{
    version: string;
    name: string;
    platform: string;
    arch: string;
    electron: string;
    chrome: string;
    node: string;
  }>;
  windowMinimize(): Promise<void>;
  windowMaximize(): Promise<void>;
  windowClose(): Promise<void>;
  windowIsMaximized(): Promise<boolean>;
  showOpenDialog(options: Electron.OpenDialogOptions): Promise<Electron.OpenDialogReturnValue>;
  showSaveDialog(options: Electron.SaveDialogOptions): Promise<Electron.SaveDialogReturnValue>;
  getNativeTheme(): Promise<boolean>;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
