/// <reference types="@electron-forge/plugin-vite/forge-vite-env" />
/// <reference types="vite/client" />

// Electron Forge Vite plugin globals (injected at build time)
declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

// Augment Window with the electron API bridge
interface Window {
  electronAPI: import('./src/renderer/types/electron.d').ElectronAPI;
}
