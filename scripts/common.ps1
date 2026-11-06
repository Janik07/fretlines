# Общие настройки скриптов: всё живёт в папке проекта, в систему ничего не ставится.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$Uv = Join-Path $Tools "uv\uv.exe"
$UvVersion = "0.13.7"

$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "cache"
$env:UV_PYTHON_PREFERENCE = "only-managed"
$env:UV_PYTHON_INSTALL_BIN = "0"
$env:UV_HTTP_TIMEOUT = "900"

function Step([string]$Text) {
    Write-Host "  - $Text" -ForegroundColor DarkGray
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "  $Text" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Ensure-Uv {
    if (Test-Path $Uv) { return }
    Step "Скачиваю uv — он поставит Python и библиотеки в папку проекта (~15 МБ)"
    $zip = Join-Path $env:TEMP "fretlines-uv.zip"
    $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    } catch {
        Fail "Не получилось скачать uv. Проверь интернет и запусти ещё раз."
    }
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Tools "uv") -Force
    Remove-Item $zip -Force
}
