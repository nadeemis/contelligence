# AGENTS.md — contelligence-cowork

Electron desktop application that bundles the Contelligence Python backend into a native macOS, Windows, and Linux app. Provides a self-contained local experience without requiring cloud deployment.

## Tech stack

- Electron 40 (Chromium + V8 + Node.js)
- React 18, TypeScript 5, Vite (renderer process)
- Tailwind CSS 3 + Radix UI components
- Electron Forge (build, package, distribute)
- PyInstaller (bundles the Python backend as a standalone binary)

## Project structure

```
src/
├── main.ts              — Electron main process (backend lifecycle, window management)
├── preload.ts           — IPC bridge (safe API exposed to renderer)
├── renderer.tsx         — React entry point (renderer process)
├── splash.ts            — Splash screen while backend starts
├── backend.ts           — Python backend process manager (start, stop, health check)
├── cli-detection.ts     — Azure CLI / Copilot CLI availability detection
├── env.ts               — Environment variable resolution
├── logging.ts           — File-based logging for main process
├── shell-env.ts         — Shell environment resolution (macOS PATH fixes)
└── renderer/            — React components for the desktop UI
public/                  — Static assets
resources/
└── backend/             — PyInstaller binary output (populated by build script)
```

## Architecture

### Main process (`main.ts`)

1. Shows splash screen
2. Starts the bundled Python backend (PyInstaller binary in `resources/backend/`)
3. Detects Azure CLI and Copilot CLI availability
4. Resolves user identity (machine ID + Azure identity)
5. Creates the main BrowserWindow pointing to the renderer
6. Sets up app data directory at `~/.contelligence/`

### Preload bridge (`preload.ts`)

Exposes a safe IPC API to the renderer via `contextBridge`:

- `getApiBaseUrl()` — local backend URL
- `getAzureStatus()` — Azure CLI availability
- `getUserIdentity()` — current user info
- Window controls (minimize, maximize, close)
- File dialogs (open, save)

### Renderer (`renderer.tsx`)

React SPA that mirrors the `contelligence-web` frontend, adapted for the desktop context. Points API calls at the local backend.

## Setup commands

```bash
# Install dependencies
npm install

# Start dev server (Vite + Electron, requires backend running separately)
npm start

# Build distributable package
npm run make

# Package without distributable (for testing)
npm run package
```

## Build workflow

The desktop app requires the Python backend compiled as a standalone binary:

```bash
# Full build (backend + desktop)
./scripts/build-cowork.sh

# Backend binary only (PyInstaller)
./scripts/build-cowork.sh backend

# Desktop package only (assumes backend already built)
./scripts/build-cowork.sh cowork
```

**Build steps:**
1. PyInstaller compiles `contelligence-agent` → standalone binary in `contelligence-agent/dist/`
2. Binary is copied to `contelligence-cowork/resources/backend/`
3. Electron Forge packages everything into a distributable app

## Key conventions

- The renderer process must never access Node.js APIs directly — all system access goes through the preload bridge
- The Python backend runs as a child process managed by `backend.ts`
- App data (config, logs, MCP config) lives in `~/.contelligence/`
- Bundle ID: `com.contelligence.desktop`
- Security fuses: ASAR integrity validation enabled, cookie encryption enabled

## Configuration

| File | Purpose |
|------|---------|
| `forge.config.ts` | Electron Forge config (packager, makers, Vite plugins) |
| `vite.main.config.ts` | Vite config for main process |
| `vite.preload.config.ts` | Vite config for preload script |
| `vite.renderer.config.ts` | Vite config for renderer process |
| `tsconfig.json` | TypeScript config |

## Patterns to avoid

- Direct `require()` or Node.js API usage in renderer code — use the preload bridge
- Hardcoded paths to the Python binary — use the resource path resolution in `backend.ts`
- Blocking the main process with synchronous operations
