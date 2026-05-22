#Requires -Version 5.1
[CmdletBinding()]
param(
  [switch]$NoLaunch,
  [switch]$IncludePrerelease
)
$ErrorActionPreference = 'Stop'
$Repo = 'nadeemis/contelligence'
$Api  = if ($IncludePrerelease) {
  "https://api.github.com/repos/$Repo/releases"
} else {
  "https://api.github.com/repos/$Repo/releases/latest"
}

Write-Host "→ Fetching latest Contelligence release…"
$headers = @{ 'Accept' = 'application/vnd.github+json'; 'User-Agent' = 'Contelligence-Installer' }
$release = Invoke-RestMethod -Uri $Api -Headers $headers
if ($IncludePrerelease) { $release = $release | Where-Object { -not $_.draft } | Select-Object -First 1 }

$version = $release.tag_name
$asset = $release.assets | Where-Object { $_.name -match 'Contelligence-win32-x64-.*\.Setup\.exe$' } | Select-Object -First 1
if (-not $asset) { throw "No Windows installer found in release $version" }

$tmp = Join-Path $env:TEMP "contelligence-$version"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$installer = Join-Path $tmp $asset.name

Write-Host "→ Downloading $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installer -UseBasicParsing

# Optional checksum
$checksums = $release.assets | Where-Object { $_.name -eq 'checksums.txt' } | Select-Object -First 1
if ($checksums) {
  Write-Host "→ Verifying SHA-256"
  $sumsFile = Join-Path $tmp 'checksums.txt'
  Invoke-WebRequest -Uri $checksums.browser_download_url -OutFile $sumsFile -UseBasicParsing
  $expected = (Get-Content $sumsFile | Where-Object { $_ -match [regex]::Escape($asset.name) }) -split '\s+' | Select-Object -First 1
  $actual   = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
  if ($expected -and $expected.ToLower() -ne $actual) { throw "Checksum mismatch for $($asset.name)" }
}

Write-Host "→ Installing Contelligence $version (silent)"
Start-Process -FilePath $installer -ArgumentList '--silent' -Wait

Write-Host "✓ Installed Contelligence $version"
if (-not $NoLaunch) {
  $exe = Join-Path $env:LocalAppData 'Contelligence\Contelligence.exe'
  if (Test-Path $exe) { Start-Process $exe }
}