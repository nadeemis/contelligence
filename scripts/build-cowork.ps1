# Build the Contelligence backend into a standalone binary with PyInstaller,
# then package the Cowork app with the backend bundled inside.
#
# Usage:
#   .\scripts\build-cowork.ps1            # build both backend + cowork
#   .\scripts\build-cowork.ps1 -Target backend  # build backend only
#   .\scripts\build-cowork.ps1 -Target cowork   # build cowork only (expects backend already built)

param(
    [ValidateSet("all", "backend", "cowork")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

if ($PSScriptRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
} else {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$AgentDir = Join-Path $RepoRoot "contelligence-agent"
$CoworkDir = Join-Path $RepoRoot "contelligence-cowork"
$BackendDist = Join-Path $AgentDir "dist\contelligence-agent"

function Package-Backend {
    Write-Host "==> Building Python backend with PyInstaller..."
    Push-Location $AgentDir

    try {
        # Ensure PyInstaller is available
        if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
            Write-Host "    Installing PyInstaller..."
            pip install pyinstaller
        }

        pyinstaller contelligence-agent.spec --noconfirm --clean
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

        Write-Host "==> Backend built: $BackendDist"
    }
    finally {
        Pop-Location
    }
}

function Package-Cowork {
    Write-Host "==> Packaging Cowork app..."
    Push-Location $CoworkDir

    try {
        # Copy built backend into cowork resources
        $TargetDir = Join-Path $CoworkDir "resources\backend"
        if (Test-Path $TargetDir) {
            Remove-Item -Recurse -Force $TargetDir
        }

        if (Test-Path $BackendDist) {
            Write-Host "    Copying backend into cowork resources..."
            New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
            Copy-Item -Recurse -Force (Join-Path $BackendDist "*") $TargetDir
        }
        else {
            Write-Error "Backend dist not found at $BackendDist. Run '.\scripts\build-cowork.ps1 -Target backend' first."
            return
        }

        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed." }

        npm run make
        if ($LASTEXITCODE -ne 0) { throw "npm run make failed." }

        Write-Host "==> Cowork app packaged -- check $(Join-Path $CoworkDir 'out')"
    }
    finally {
        Pop-Location
    }
}

switch ($Target) {
    "backend" { Package-Backend }
    "cowork"  { Package-Cowork }
    "all"     { Package-Backend; Package-Cowork }
}