# Forge installer for Windows 10/11 (PowerShell).
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1  [-Venv C:\path\to\venv]
param([string]$Venv = "$env:USERPROFILE\ai-env")
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = "python"; if (Get-Command py -ErrorAction SilentlyContinue) { $Py = "py" }
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & $Py -m venv $Venv }
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install -r "$Dir\requirements.txt"
foreach ($d in "memory","backups","tests") { New-Item -ItemType Directory -Force "$env:USERPROFILE\Forge\$d" | Out-Null }

# Allow the PowerShell profile to load
$pol = Get-ExecutionPolicy -Scope CurrentUser
if ($pol -in @("Undefined","Restricted","AllSigned")) { Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force }

# forge function in $PROFILE
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Force $PROFILE | Out-Null }
$line = "function forge { & `"$Venv\Scripts\python.exe`" `"$Dir\forge.py`" @args }"
if (-not (Select-String -Path $PROFILE -Pattern "function forge " -Quiet)) { Add-Content $PROFILE "`n# Forge AI assistant`n$line"; Write-Host "Added 'forge' to $PROFILE" }
else { Write-Host "'forge' already in $PROFILE, left it alone." }

# forge.cmd fallback on the user PATH (works in cmd.exe too)
$bin = "$env:USERPROFILE\.forge\bin"
New-Item -ItemType Directory -Force $bin | Out-Null
Set-Content "$bin\forge.cmd" "@echo off`r`nchcp 65001 >nul`r`n`"$Venv\Scripts\python.exe`" `"$Dir\forge.py`" %*" -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $bin) { [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $bin).TrimStart(";"), "User") }

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Host "Install Ollama from https://ollama.com/download, then: ollama pull qwen3:4b" }
Write-Host "Done! Open a new Terminal tab and type: forge   (inside Forge, try /model suggest)"
