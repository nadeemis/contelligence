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
  getAzureStatus(): Promise<{ available: boolean; loggedIn: boolean; error?: string }>;
  getUserIdentity(): Promise<{
    machine: { username: string; fullName: string };
    azure?: { name: string; email: string; tenantId: string };
  }>;
  onBackendRestarted(callback: () => void): () => void;
  getSamplePrompts(): Promise<Array<{ category: string; prompts: string[] }>>;
  openSamplePromptsEditor(): Promise<void>;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
