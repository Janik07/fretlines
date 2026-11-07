# Публикация в Hugging Face Space: ветка main + README с настройками Space (deploy/huggingface).
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\deploy-hf.ps1
# Нужен remote «hf», например: git remote add hf https://huggingface.co/spaces/<логин>/fretlines
param([string]$Remote = "hf", [string]$Branch = "main")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& git remote get-url $Remote *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Нет remote «$Remote». Добавь: git remote add $Remote https://huggingface.co/spaces/<логин>/fretlines" -ForegroundColor Red
    exit 1
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("fretlines-hf-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
& git worktree add --detach $tmp $Branch
if ($LASTEXITCODE -ne 0) { exit 1 }
try {
    Copy-Item (Join-Path $root "deploy\huggingface\README.md") (Join-Path $tmp "README.md") -Force
    & git -C $tmp add README.md
    & git -C $tmp commit -q -m "Hugging Face Space: настройки и описание"
    Write-Host "  - Отправляю в $Remote (Space пересоберётся сам, это ~10 минут)" -ForegroundColor DarkGray
    & git -C $tmp push $Remote HEAD:main --force
    if ($LASTEXITCODE -ne 0) { throw "push не удался" }
} finally {
    & git worktree remove $tmp --force
}
Write-Host "  Готово." -ForegroundColor Green
